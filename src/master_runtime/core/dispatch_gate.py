"""Dispatch gate for worker scheduler requests."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence


DEFAULT_SINGLE_DISPATCH_CHAR_LIMIT = 500_000
DEFAULT_BATCH_DISPATCH_CHAR_LIMIT = 1_000_000
DEFAULT_DUPLICATE_WINDOW_SECONDS = 30 * 60
DEFAULT_HIGH_COST_RUNTIMES = frozenset({"fable"})
DEFAULT_LEDGER_PATH = Path(".dispatch-gate-ledger.jsonl")
DEFAULT_TICKET_DIR = Path(".mogui") / "dispatch-tickets"


def _default_ledger_path() -> Path:
    value = os.environ.get("DISPATCH_GATE_LEDGER")
    if value:
        return Path(value)
    return DEFAULT_LEDGER_PATH


def _default_ticket_dir() -> Path:
    return Path.home() / DEFAULT_TICKET_DIR


class ReasonCode(str, Enum):
    """Stable gate decision reason codes."""

    OK = "OK"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ROUTING_VIOLATION = "ROUTING_VIOLATION"
    DUPLICATE_CONTRACT = "DUPLICATE_CONTRACT"
    UNVERIFIED_JOB = "UNVERIFIED_JOB"
    INVALID_REQUEST = "INVALID_REQUEST"
    CONTRACT_UNREADABLE = "CONTRACT_UNREADABLE"
    HIGH_COST_RUNTIME = "HIGH_COST_RUNTIME"


@dataclass(frozen=True)
class DispatchRequest:
    """Facts used to decide whether a worker dispatch may proceed."""

    runtime: str
    contract_path: str | Path
    est_input_chars: int
    n_agents: int
    purpose: str = ""


@dataclass(frozen=True)
class GateDecision:
    """Decision returned by the dispatch gate."""

    allow: bool
    reason: ReasonCode
    warnings: tuple[ReasonCode, ...] = ()
    contract_sha: str | None = None
    cost_proxy: int = 0


@dataclass(frozen=True)
class DispatchGateConfig:
    """Configurable dispatch gate thresholds and storage."""

    ledger_path: str | Path = field(default_factory=_default_ledger_path)
    ticket_dir: str | Path = field(default_factory=_default_ticket_dir)
    single_dispatch_char_limit: int = DEFAULT_SINGLE_DISPATCH_CHAR_LIMIT
    batch_dispatch_char_limit: int = DEFAULT_BATCH_DISPATCH_CHAR_LIMIT
    duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS
    high_cost_runtimes: frozenset[str] = DEFAULT_HIGH_COST_RUNTIMES


class DispatchGate:
    """Evaluate dispatch requests and maintain an append-only JSONL ledger."""

    def __init__(
        self,
        config: DispatchGateConfig | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or DispatchGateConfig()
        self._clock = clock or time.time

    def check(self, request: DispatchRequest) -> GateDecision:
        """Return a gate decision and append it to the ledger."""

        validation_error = _validate_request(request)
        if validation_error is not None:
            decision = GateDecision(False, validation_error)
            self._append_decision(request, decision)
            return decision

        try:
            contract_sha = _contract_sha(request.contract_path)
        except FileNotFoundError:
            decision = GateDecision(False, ReasonCode.CONTRACT_UNREADABLE)
            self._append_decision(request, decision)
            return decision
        cost_proxy = request.n_agents * request.est_input_chars

        if (
            request.est_input_chars > self.config.single_dispatch_char_limit
            or cost_proxy > self.config.batch_dispatch_char_limit
        ):
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.BUDGET_EXCEEDED,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        runtime = request.runtime.lower()
        if runtime in self.config.high_cost_runtimes and request.n_agents >= 2:
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.ROUTING_VIOLATION,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        if self._has_recent_contract(contract_sha):
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.DUPLICATE_CONTRACT,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        warnings: tuple[ReasonCode, ...] = ()
        if runtime in self.config.high_cost_runtimes:
            warnings = (ReasonCode.HIGH_COST_RUNTIME,)

        decision = GateDecision(
            allow=True,
            reason=ReasonCode.OK,
            warnings=warnings,
            contract_sha=contract_sha,
            cost_proxy=cost_proxy,
        )
        self._append_decision(request, decision)
        self._issue_dispatch_ticket(request, contract_sha)
        return decision

    def register_job(
        self,
        job_id: str,
        probe_fn: Callable[[str], bool],
    ) -> GateDecision:
        """Register a job only after independent probe verification succeeds."""

        if not job_id or not probe_fn(job_id):
            return GateDecision(False, ReasonCode.UNVERIFIED_JOB)

        pending = self._latest_pending_dispatch()
        if pending is None:
            return GateDecision(False, ReasonCode.UNVERIFIED_JOB)

        decision = GateDecision(
            allow=True,
            reason=ReasonCode.OK,
            contract_sha=_string_or_none(pending.get("contract_sha")),
            cost_proxy=_int_or_zero(pending.get("est_chars")),
        )
        self._append_entry(
            {
                "ts": self._clock(),
                "contract_sha": pending["contract_sha"],
                "runtime": pending["runtime"],
                "n_agents": pending["n_agents"],
                "est_chars": pending["est_chars"],
                "decision": "ALLOW",
                "reason": ReasonCode.OK.value,
                "job_id": job_id,
            }
        )
        return decision

    def ledger_entries(self) -> tuple[Mapping[str, object], ...]:
        """Return parsed ledger entries in append order."""

        return tuple(self._read_entries())

    def _append_decision(
        self,
        request: DispatchRequest,
        decision: GateDecision,
    ) -> None:
        entry: dict[str, object] = {
            "ts": self._clock(),
            "contract_sha": decision.contract_sha,
            "runtime": request.runtime,
            "n_agents": request.n_agents,
            "est_chars": request.est_input_chars,
            "decision": "ALLOW" if decision.allow else "DENY",
            "reason": decision.reason.value,
        }
        self._append_entry(entry)

    def _append_entry(self, entry: Mapping[str, object]) -> None:
        ledger_path = Path(self.config.ledger_path)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(entry, sort_keys=True, separators=(",", ":")))
            ledger.write("\n")

    def _issue_dispatch_ticket(
        self,
        request: DispatchRequest,
        contract_sha: str,
    ) -> None:
        ticket_dir = Path(self.config.ticket_dir)
        ticket_dir.mkdir(parents=True, exist_ok=True)

        runtime = request.runtime.lower()
        ticket_path = ticket_dir / f"{runtime}-{contract_sha[:12]}.json"
        payload = {
            "runtime": runtime,
            "contract_sha": contract_sha,
            "issued_ts": self._clock(),
            "count": request.n_agents,
        }
        with ticket_path.open("w", encoding="utf-8") as ticket:
            ticket.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            ticket.write("\n")

    def _has_recent_contract(self, contract_sha: str) -> bool:
        threshold = self._clock() - self.config.duplicate_window_seconds
        for entry in self._read_entries():
            if (
                entry.get("contract_sha") == contract_sha
                and entry.get("decision") == "ALLOW"
                and _number_or_zero(entry.get("ts")) >= threshold
            ):
                return True
        return False

    def _latest_pending_dispatch(self) -> Mapping[str, object] | None:
        registered_counts: dict[str, int] = {}
        for entry in reversed(self._read_entries()):
            contract_sha = _string_or_none(entry.get("contract_sha"))
            if contract_sha is None:
                continue
            if entry.get("job_id"):
                registered_counts[contract_sha] = (
                    registered_counts.get(contract_sha, 0) + 1
                )
            elif entry.get("decision") == "ALLOW":
                registrations = registered_counts.get(contract_sha, 0)
                if registrations == 0:
                    return entry
                registered_counts[contract_sha] = registrations - 1
        return None

    def _read_entries(self) -> Sequence[Mapping[str, object]]:
        ledger_path = Path(self.config.ledger_path)
        if not ledger_path.exists():
            return ()

        entries: list[Mapping[str, object]] = []
        with ledger_path.open("r", encoding="utf-8") as ledger:
            for line in ledger:
                if line.strip():
                    entries.append(json.loads(line))
        return entries


def _validate_request(request: DispatchRequest) -> ReasonCode | None:
    if not request.runtime:
        return ReasonCode.INVALID_REQUEST
    if request.est_input_chars < 0:
        return ReasonCode.INVALID_REQUEST
    if request.n_agents < 1:
        return ReasonCode.INVALID_REQUEST
    return None


def _contract_sha(contract_path: str | Path) -> str:
    try:
        content = Path(contract_path).read_bytes()
    except OSError as exc:
        raise FileNotFoundError(f"cannot read contract: {contract_path}") from exc
    return hashlib.sha256(content).hexdigest()


def _number_or_zero(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None
