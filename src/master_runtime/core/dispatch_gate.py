"""Dispatch gate for worker scheduler requests."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
DEFAULT_KNOWN_ROOTS_PATH = Path(".mogui") / "known-roots.json"
RUNTIME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
USERS_ABSOLUTE_PATH_PATTERN = re.compile(r"/Users/[^\s\"'`<>{}\[\](),;:]+")


def _default_ledger_path() -> Path:
    value = os.environ.get("DISPATCH_GATE_LEDGER")
    if value:
        return Path(value)
    return DEFAULT_LEDGER_PATH


def _default_ticket_dir() -> Path:
    return Path.home() / DEFAULT_TICKET_DIR


def _default_known_roots_path() -> Path:
    return Path.home() / DEFAULT_KNOWN_ROOTS_PATH


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
    AMBIGUOUS_TICKET = "AMBIGUOUS_TICKET"
    NO_MATCHING_TICKET = "NO_MATCHING_TICKET"
    MCP_TRUST_UNHANDLED = "MCP_TRUST_UNHANDLED"
    PATH_OUTSIDE_KNOWN_ROOTS = "PATH_OUTSIDE_KNOWN_ROOTS"
    WORKTREE_AS_REPO_ROOT = "WORKTREE_AS_REPO_ROOT"


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
    known_roots_path: str | Path = field(default_factory=_default_known_roots_path)
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
            contract_content = _contract_content(request.contract_path)
        except FileNotFoundError:
            decision = GateDecision(False, ReasonCode.CONTRACT_UNREADABLE)
            self._append_decision(request, decision)
            return decision
        contract_sha = _contract_sha_from_content(contract_content)
        lint_warnings = _contract_lint_warnings(
            contract_content.decode("utf-8", errors="replace"),
            Path(self.config.known_roots_path),
        )
        cost_proxy = request.n_agents * request.est_input_chars
        if (
            _dispatch_ticket_path(
                Path(self.config.ticket_dir),
                request.runtime.lower(),
                contract_sha,
            )
            is None
        ):
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.INVALID_REQUEST,
                warnings=lint_warnings,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        if (
            request.est_input_chars > self.config.single_dispatch_char_limit
            or cost_proxy > self.config.batch_dispatch_char_limit
        ):
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.BUDGET_EXCEEDED,
                warnings=lint_warnings,
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
                warnings=lint_warnings,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        if self._has_recent_contract(contract_sha):
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.DUPLICATE_CONTRACT,
                warnings=lint_warnings,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
            )
            self._append_decision(request, decision)
            return decision

        warnings = lint_warnings
        if runtime in self.config.high_cost_runtimes:
            warnings = (*warnings, ReasonCode.HIGH_COST_RUNTIME)

        decision = GateDecision(
            allow=True,
            reason=ReasonCode.OK,
            warnings=warnings,
            contract_sha=contract_sha,
            cost_proxy=cost_proxy,
        )
        self._append_decision(request, decision)
        self._issue_dispatch_ticket(request, decision)
        return decision

    def register_job(
        self,
        job_id: str,
        probe_fn: Callable[[str], bool],
        contract_sha: str | None = None,
    ) -> GateDecision:
        """Register a job only after independent probe verification succeeds."""

        if not job_id or not probe_fn(job_id):
            return GateDecision(False, ReasonCode.UNVERIFIED_JOB)

        pending_dispatches = self._pending_dispatches()
        if contract_sha is not None:
            contract_sha_filter = _normalize_contract_sha_filter(contract_sha)
            if contract_sha_filter is None:
                return GateDecision(False, ReasonCode.INVALID_REQUEST)
            matching_pending = tuple(
                entry
                for entry in pending_dispatches
                if _contract_sha_matches(entry.get("contract_sha"), contract_sha_filter)
            )
            if not matching_pending:
                return GateDecision(False, ReasonCode.NO_MATCHING_TICKET)
            if len(matching_pending) > 1:
                return GateDecision(False, ReasonCode.AMBIGUOUS_TICKET)
            pending = matching_pending[0]
        else:
            if not pending_dispatches:
                return GateDecision(False, ReasonCode.UNVERIFIED_JOB)
            if len(pending_dispatches) > 1:
                return GateDecision(False, ReasonCode.AMBIGUOUS_TICKET)
            pending = pending_dispatches[0]

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
        decision: GateDecision,
    ) -> None:
        if not decision.allow:
            return
        if decision.contract_sha is None:
            return

        ticket_dir = Path(self.config.ticket_dir)
        ticket_dir.mkdir(parents=True, exist_ok=True)

        runtime = request.runtime.lower()
        ticket_path = _dispatch_ticket_path(ticket_dir, runtime, decision.contract_sha)
        if ticket_path is None:
            return

        payload = {
            "runtime": runtime,
            "contract_sha": decision.contract_sha,
            "issued_ts": self._clock(),
            "count": request.n_agents,
        }
        tmp_path = ticket_path.with_name(f".{ticket_path.name}.{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as ticket:
            ticket.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            ticket.write("\n")
        os.replace(tmp_path, ticket_path)

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

    def _pending_dispatches(self) -> tuple[Mapping[str, object], ...]:
        registered_counts: dict[str, int] = {}
        pending: list[Mapping[str, object]] = []
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
                    pending.append(entry)
                else:
                    registered_counts[contract_sha] = registrations - 1
        return tuple(pending)

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
    if RUNTIME_PATTERN.fullmatch(request.runtime) is None:
        return ReasonCode.INVALID_REQUEST
    if request.est_input_chars < 0:
        return ReasonCode.INVALID_REQUEST
    if request.n_agents < 1:
        return ReasonCode.INVALID_REQUEST
    return None


def _dispatch_ticket_path(
    ticket_dir: Path,
    runtime: str,
    contract_sha: str,
) -> Path | None:
    ticket_dir_resolved = ticket_dir.resolve()
    ticket_path = ticket_dir / f"{runtime}-{contract_sha[:12]}.json"
    ticket_path_resolved = ticket_path.resolve()
    if ticket_path_resolved.parent != ticket_dir_resolved:
        return None
    return ticket_path


def _contract_content(contract_path: str | Path) -> bytes:
    try:
        return Path(contract_path).read_bytes()
    except OSError as exc:
        raise FileNotFoundError(f"cannot read contract: {contract_path}") from exc


def _contract_sha(contract_path: str | Path) -> str:
    return _contract_sha_from_content(_contract_content(contract_path))


def _contract_sha_from_content(content: bytes) -> str:
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


def _contract_lint_warnings(
    contract_text: str,
    known_roots_path: Path,
) -> tuple[ReasonCode, ...]:
    warnings: list[ReasonCode] = []
    if _mentions_mcp_without_trust_handling(contract_text):
        warnings.append(ReasonCode.MCP_TRUST_UNHANDLED)
    if _has_path_outside_known_roots(contract_text, known_roots_path):
        warnings.append(ReasonCode.PATH_OUTSIDE_KNOWN_ROOTS)
    if _has_worktree_as_repo_root(contract_text):
        warnings.append(ReasonCode.WORKTREE_AS_REPO_ROOT)
    return tuple(warnings)


def _mentions_mcp_without_trust_handling(contract_text: str) -> bool:
    mentions_mcp = re.search(
        r"\bmcp\b|mcp__|code-review-graph",
        contract_text,
        flags=re.IGNORECASE,
    )
    if mentions_mcp is None:
        return False
    mentions_trust_handling = re.search(
        r"trust|신뢰|다이얼로그",
        contract_text,
        flags=re.IGNORECASE,
    )
    return mentions_trust_handling is None


def _has_path_outside_known_roots(
    contract_text: str,
    known_roots_path: Path,
) -> bool:
    known_roots = _load_known_roots(known_roots_path)
    if not known_roots:
        return False

    for path in _absolute_users_paths(contract_text):
        if not any(_path_is_under(path, root) for root in known_roots):
            return True
    return False


def _load_known_roots(known_roots_path: Path) -> tuple[Path, ...]:
    if not known_roots_path.exists():
        return ()
    try:
        payload = json.loads(known_roots_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(Path(root) for root in payload if isinstance(root, str) and root)


def _absolute_users_paths(contract_text: str) -> tuple[Path, ...]:
    paths: list[Path] = []
    for match in USERS_ABSOLUTE_PATH_PATTERN.finditer(contract_text):
        paths.append(Path(match.group(0).rstrip(".,)]}\"'`")))
    return tuple(paths)


def _path_is_under(path: Path, root: Path) -> bool:
    if not path.is_absolute() or not root.is_absolute():
        return False
    return path == root or path.is_relative_to(root)


def _has_worktree_as_repo_root(contract_text: str) -> bool:
    for line in contract_text.splitlines():
        lower_line = line.lower()
        if "/.orca/worktrees/" not in line:
            continue
        if (
            "repo_root" in lower_line
            or "repo root" in lower_line
            or "repo-root" in lower_line
            or "graph" in lower_line
        ):
            return True
    return False


def _normalize_contract_sha_filter(contract_sha: str) -> str | None:
    contract_sha_filter = contract_sha.strip().lower()
    if len(contract_sha_filter) < 12:
        return None
    if re.fullmatch(r"[0-9a-f]+", contract_sha_filter) is None:
        return None
    return contract_sha_filter


def _contract_sha_matches(value: object, contract_sha_filter: str) -> bool:
    contract_sha = _string_or_none(value)
    if contract_sha is None:
        return False
    return contract_sha.lower().startswith(contract_sha_filter)
