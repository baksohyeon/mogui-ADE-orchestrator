"""Dispatch gate for worker scheduler requests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback keeps tests importable.
    fcntl = None


DEFAULT_SINGLE_DISPATCH_CHAR_LIMIT = 500_000
DEFAULT_BATCH_DISPATCH_CHAR_LIMIT = 1_000_000
DEFAULT_DUPLICATE_WINDOW_SECONDS = 30 * 60
DEFAULT_HIGH_COST_RUNTIMES = frozenset({"fable"})
DEFAULT_LEDGER_PATH = Path(".dispatch-gate-ledger.jsonl")
DEFAULT_TICKET_DIR = Path(".mogui") / "dispatch-tickets"
DEFAULT_KNOWN_ROOTS_PATH = Path(".mogui") / "known-roots.json"
DEFAULT_TIER_POLICY_RELATIVE_PATH = Path("master-ops") / "model-tier-policy.json"
# One day. The fan-out that caused the incident can be spread over sequential
# dispatches, so the cap counts agents inside a window rather than at once.
DEFAULT_TIER_WINDOW_SECONDS = 24 * 60 * 60
UNKNOWN_TIER = "unknown"
DEFAULT_TICKET_TTL_SECONDS = 600
DEFAULT_EXPIRED_TICKET_GC_GRACE_SECONDS = 24 * 60 * 60
RUNTIME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
USERS_ABSOLUTE_PATH_PATTERN = re.compile(r"/Users/[^\s\"'`<>{}\[\](),;:]+")
COMPLETION_CHANNELS = frozenset({"orchestration", "sentinel-log"})


def _default_ledger_path() -> Path:
    value = os.environ.get("DISPATCH_GATE_LEDGER")
    if value:
        return Path(value)
    return DEFAULT_LEDGER_PATH


def _default_ticket_dir() -> Path:
    return Path.home() / DEFAULT_TICKET_DIR


def _default_known_roots_path() -> Path:
    return Path.home() / DEFAULT_KNOWN_ROOTS_PATH


def _default_tier_policy_path() -> Path:
    value = os.environ.get("DISPATCH_TIER_POLICY")
    if value:
        return Path(value)
    return Path(__file__).resolve().parents[3] / DEFAULT_TIER_POLICY_RELATIVE_PATH


class ReasonCode(str, Enum):
    """Stable gate decision reason codes."""

    OK = "OK"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ROUTING_VIOLATION = "ROUTING_VIOLATION"
    DUPLICATE_CONTRACT = "DUPLICATE_CONTRACT"
    UNVERIFIED_JOB = "UNVERIFIED_JOB"
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_COMPLETION_CHANNEL = "NO_COMPLETION_CHANNEL"
    NO_MODEL = "NO_MODEL"
    ORCHESTRATION_UNVERIFIED = "ORCHESTRATION_UNVERIFIED"
    CONTRACT_UNREADABLE = "CONTRACT_UNREADABLE"
    HIGH_COST_RUNTIME = "HIGH_COST_RUNTIME"
    AMBIGUOUS_TICKET = "AMBIGUOUS_TICKET"
    NO_MATCHING_TICKET = "NO_MATCHING_TICKET"
    MCP_TRUST_UNHANDLED = "MCP_TRUST_UNHANDLED"
    PATH_OUTSIDE_KNOWN_ROOTS = "PATH_OUTSIDE_KNOWN_ROOTS"
    WORKTREE_AS_REPO_ROOT = "WORKTREE_AS_REPO_ROOT"
    TIER_POLICY = "TIER_POLICY"
    TIER_POLICY_UNAVAILABLE = "TIER_POLICY_UNAVAILABLE"
    TIER_FANOUT_CAP = "TIER_FANOUT_CAP"
    TIER_UNKNOWN_MODEL = "TIER_UNKNOWN_MODEL"


@dataclass(frozen=True)
class DispatchRequest:
    """Facts used to decide whether a worker dispatch may proceed."""

    runtime: str
    contract_path: str | Path
    est_input_chars: int | None
    n_agents: int
    purpose: str = ""
    completion_channel: str | None = None
    model: str | None = None
    tier_override: str | None = None


@dataclass(frozen=True)
class GateDecision:
    """Decision returned by the dispatch gate."""

    allow: bool
    reason: ReasonCode
    warnings: tuple[ReasonCode, ...] = ()
    contract_sha: str | None = None
    cost_proxy: int = 0
    message: str = ""
    tier_override: str | None = None


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
    ticket_ttl_seconds: int = DEFAULT_TICKET_TTL_SECONDS
    expired_ticket_gc_grace_seconds: int = DEFAULT_EXPIRED_TICKET_GC_GRACE_SECONDS
    tier_policy_path: str | Path = field(default_factory=_default_tier_policy_path)


@dataclass(frozen=True)
class DispatchTicket:
    """Valid on-disk dispatch ticket."""

    path: Path
    runtime: str
    contract_sha: str
    issued_ts: float
    count: int


@dataclass(frozen=True)
class ModelTierPolicy:
    """Validated per-installation worker model policy.

    Model sets are casefolded. Exact-string membership let a case variant of a
    denied tier miss the denied set, fall into the unknown branch, and pass as a
    warning wherever `unknown_model` is `warn`. `digest` identifies the file the
    decision was made against, because the path is caller-supplied.

    Two shapes are supported. Version 1 gates on model identity: a name is
    allowed, denied, or unknown. Version 2 gates on tier and fan-out, because the
    incident this policy exists for was a top tier multiplied by ten workers, not
    a particular identifier. Version 1 keeps its exact behaviour so no
    installation changes verdicts by upgrading the runtime alone.
    """

    unknown_model: str
    digest: str = ""
    version: int = 1
    # v1
    worker_allowed: frozenset[str] = frozenset()
    worker_denied_tiers: frozenset[str] = frozenset()
    # v2
    model_tiers: Mapping[str, str] = field(default_factory=dict)
    fanout_caps: Mapping[str, int] = field(default_factory=dict)
    window_seconds: int = DEFAULT_TIER_WINDOW_SECONDS

    def tier_of(self, model_key: str) -> str:
        """Return the tier for a casefolded model id, or the unknown tier."""

        return self.model_tiers.get(model_key, UNKNOWN_TIER)

    def cap_for(self, tier: str) -> int | None:
        """Agents permitted per window for a tier. None means uncapped."""

        cap = self.fanout_caps.get(tier)
        return cap if isinstance(cap, int) else None


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

        # Per-call, reset before anything can append: entries written before the
        # policy loads must not inherit a digest from an earlier check. One gate
        # instance per process is the assumption here, same as the ticket lock.
        self._tier_policy_digest = ""
        self._tier = ""

        # None is the fail-closed sentinel for an input whose size could not be
        # measured. Handle it before every other validation or budget check so
        # reordering the remaining checks cannot turn an unreadable contract
        # into a zero-cost dispatch.
        est_input_chars = request.est_input_chars
        if est_input_chars is None:
            decision = GateDecision(False, ReasonCode.CONTRACT_UNREADABLE)
            self._append_decision(request, decision)
            return decision

        validation_error = _validate_request(request)
        if validation_error is not None:
            decision = GateDecision(False, validation_error)
            self._append_decision(request, decision)
            return decision

        try:
            tier_policy = _load_tier_policy(Path(self.config.tier_policy_path))
        except (OSError, ValueError, json.JSONDecodeError):
            decision = GateDecision(
                False,
                ReasonCode.TIER_POLICY_UNAVAILABLE,
                message=f"tier_policy={self.config.tier_policy_path}",
            )
            self._append_decision(request, decision)
            return decision

        self._tier_policy_digest = tier_policy.digest
        tier_warning: ReasonCode | None = None
        tier_override: str | None = None
        model = request.model.strip() if request.model is not None else ""
        # Casefolded: a denied tier spelled in another case is the same tier.
        model_key = model.casefold()

        if tier_policy.version >= 2:
            tier = tier_policy.tier_of(model_key)
            self._tier = tier
            cap = tier_policy.cap_for(tier)
            if cap is not None:
                used = self._tier_window_agents(tier, tier_policy)
                if used + request.n_agents > cap:
                    if request.tier_override is None:
                        decision = GateDecision(
                            False,
                            ReasonCode.TIER_FANOUT_CAP,
                            message=(
                                f"tier={tier} agents={request.n_agents} "
                                f"used={used} cap={cap} "
                                f"window_seconds={tier_policy.window_seconds}"
                            ),
                        )
                        self._append_decision(request, decision)
                        return decision
                    tier_override = request.tier_override.strip()
            # An unlisted model is allowed under the unknown cap rather than
            # blocked outright, so a newer or cheaper model is usable before
            # anyone edits the policy. It never passes silently: the tier lands
            # in the ledger and the warning surfaces it in the rollup.
            if tier == UNKNOWN_TIER:
                tier_warning = ReasonCode.TIER_UNKNOWN_MODEL

        elif model_key not in tier_policy.worker_allowed:
            policy_denies = (
                model_key in tier_policy.worker_denied_tiers
                or tier_policy.unknown_model == "deny"
            )
            if policy_denies:
                if request.tier_override is None:
                    decision = GateDecision(
                        False,
                        ReasonCode.TIER_POLICY,
                        message=f"model={model}",
                    )
                    self._append_decision(request, decision)
                    return decision
                tier_override = request.tier_override.strip()
            else:
                tier_warning = ReasonCode.TIER_POLICY

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
        if tier_warning is not None:
            lint_warnings = (*lint_warnings, tier_warning)
        cost_proxy = request.n_agents * est_input_chars
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
            est_input_chars > self.config.single_dispatch_char_limit
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
            self._refresh_dispatch_ticket(request, contract_sha)
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
            tier_override=tier_override,
        )
        self._append_decision(request, decision)
        self._issue_dispatch_ticket(request, decision)
        return decision

    def register_job(
        self,
        job_id: str,
        probe_fn: Callable[[str], bool],
        contract_sha: str | None = None,
        runtime: str | None = None,
        orchestration_task: str | None = None,
    ) -> GateDecision:
        """Register a job only after independent probe verification succeeds."""

        if not job_id or not probe_fn(job_id):
            return GateDecision(False, ReasonCode.UNVERIFIED_JOB)

        runtime_filter = _normalize_runtime_filter(runtime)
        if runtime is not None and runtime_filter is None:
            return GateDecision(False, ReasonCode.INVALID_REQUEST)

        with _ticket_lock(Path(self.config.ticket_dir)):
            tickets = self._valid_dispatch_tickets(runtime_filter=runtime_filter)
            if contract_sha is not None:
                contract_sha_filter = _normalize_contract_sha_filter(contract_sha)
                if contract_sha_filter is None:
                    return GateDecision(False, ReasonCode.INVALID_REQUEST)
                all_tickets = self._dispatch_tickets(
                    runtime_filter=runtime_filter,
                    include_expired=True,
                )
                matching_tickets = tuple(
                    ticket
                    for ticket in all_tickets
                    if ticket.contract_sha.lower().startswith(contract_sha_filter)
                )
                if len(matching_tickets) > 1:
                    return GateDecision(
                        False,
                        ReasonCode.AMBIGUOUS_TICKET,
                        message=_candidate_sha_message(matching_tickets),
                    )
                selected_ticket = matching_tickets[0] if matching_tickets else None
                pending_dispatches = self._pending_dispatches()
                if selected_ticket is not None:
                    matching_pending = tuple(
                        entry
                        for entry in pending_dispatches
                        if entry.get("contract_sha") == selected_ticket.contract_sha
                        and entry.get("runtime") == selected_ticket.runtime
                    )
                else:
                    if all_tickets:
                        return GateDecision(
                            False,
                            ReasonCode.NO_MATCHING_TICKET,
                            message=_candidate_sha_message(all_tickets),
                        )
                    matching_pending = tuple(
                        entry
                        for entry in pending_dispatches
                        if _contract_sha_matches(entry.get("contract_sha"), contract_sha_filter)
                        and (
                            runtime_filter is None
                            or _string_or_none(entry.get("runtime")) == runtime_filter
                        )
                    )
                    if len(matching_pending) > 1:
                        return GateDecision(
                            False,
                            ReasonCode.AMBIGUOUS_TICKET,
                            message=_candidate_sha_message_from_entries(matching_pending),
                        )
                    if not matching_pending:
                        return GateDecision(
                            False,
                            ReasonCode.NO_MATCHING_TICKET,
                            message=_candidate_sha_message(all_tickets),
                        )
            else:
                if not tickets:
                    return GateDecision(
                        False,
                        ReasonCode.NO_MATCHING_TICKET,
                        message=_candidate_sha_message(tickets),
                    )
                if len(tickets) > 1:
                    return GateDecision(
                        False,
                        ReasonCode.AMBIGUOUS_TICKET,
                        message=_candidate_sha_message(tickets),
                    )
                selected_ticket = tickets[0]
                matching_pending = tuple(
                    entry
                    for entry in self._pending_dispatches()
                    if entry.get("contract_sha") == selected_ticket.contract_sha
                    and entry.get("runtime") == selected_ticket.runtime
                )
                if not matching_pending:
                    return GateDecision(
                        False,
                        ReasonCode.NO_MATCHING_TICKET,
                        message=_candidate_sha_message(tickets),
                    )
            pending = matching_pending[0]

            if contract_sha is not None and selected_ticket is not None:
                try:
                    selected_ticket.path.unlink()
                except FileNotFoundError:
                    pass

            decision = GateDecision(
                allow=True,
                reason=ReasonCode.OK,
                contract_sha=_string_or_none(pending.get("contract_sha")),
                cost_proxy=_int_or_zero(pending.get("est_chars")),
                message=(
                    "ticket_absent"
                    if contract_sha is not None and selected_ticket is None
                    else ""
                ),
            )
            entry: dict[str, object] = {
                "ts": self._clock(),
                "contract_sha": pending["contract_sha"],
                "runtime": pending["runtime"],
                "n_agents": pending["n_agents"],
                "est_chars": pending["est_chars"],
                "decision": "ALLOW",
                "reason": ReasonCode.OK.value,
                "job_id": job_id,
            }
            if orchestration_task is not None:
                entry["orchestration_task"] = orchestration_task
            self._append_entry(entry)
        return decision

    def ledger_entries(self) -> tuple[Mapping[str, object], ...]:
        """Return parsed ledger entries in append order."""

        return tuple(self._read_entries())

    def _tier_window_agents(self, tier: str, policy: ModelTierPolicy) -> int:
        """Agents already dispatched in this tier inside the policy window.

        Counts allowed dispatches, including ones an override let through: an
        override bypasses the block for one request, it does not refund the cost
        the window is measuring. Ten sequential single-agent dispatches therefore
        reach the same cap as one fan-out of ten, which is the point, because the
        incident's cost does not care whether the workers started together.

        Entries written before the tier field existed are resolved through the
        current policy, so history counts from the moment a policy names it. A
        policy edit relabels past entries; that is the intended reading, since
        the question being asked is what the policy in force now would have said.
        """

        threshold = self._clock() - policy.window_seconds
        total = 0
        for entry in self._read_entries():
            if not isinstance(entry, Mapping) or entry.get("decision") != "ALLOW":
                continue
            timestamp = entry.get("ts")
            if (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
                or timestamp < threshold
            ):
                continue
            entry_tier = entry.get("tier")
            if not isinstance(entry_tier, str) or not entry_tier:
                model = entry.get("model")
                entry_tier = (
                    policy.tier_of(model.strip().casefold())
                    if isinstance(model, str)
                    else UNKNOWN_TIER
                )
            if entry_tier != tier:
                continue
            agents = entry.get("n_agents")
            if isinstance(agents, bool) or not isinstance(agents, int) or agents < 1:
                continue
            total += agents
        return total

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
            "cost_proxy": decision.cost_proxy,
            "completion_channel": request.completion_channel,
            "model": request.model,
        }
        if decision.warnings:
            entry["warnings"] = [warning.value for warning in decision.warnings]
        if decision.tier_override is not None:
            entry["tier_override"] = decision.tier_override
        # Which policy decided. The path is caller-supplied through --tier-policy
        # or DISPATCH_TIER_POLICY, so an ALLOW that names neither path nor digest
        # cannot be told apart from one a substituted policy allowed.
        if getattr(self, "_tier", ""):
            entry["tier"] = self._tier
        entry["tier_policy_path"] = str(self.config.tier_policy_path)
        if getattr(self, "_tier_policy_digest", ""):
            entry["tier_policy_sha256"] = self._tier_policy_digest
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

        self._write_dispatch_ticket(request, decision.contract_sha, request.n_agents)

    def _refresh_dispatch_ticket(
        self,
        request: DispatchRequest,
        contract_sha: str,
    ) -> None:
        runtime = request.runtime.lower()
        if _dispatch_ticket_path(Path(self.config.ticket_dir), runtime, contract_sha) is None:
            return

        with _ticket_lock(Path(self.config.ticket_dir)):
            existing = self._read_dispatch_ticket(runtime, contract_sha)
            count = existing.count if existing is not None else request.n_agents
            self._write_dispatch_ticket_unlocked(request, contract_sha, count)

    def _write_dispatch_ticket(
        self,
        request: DispatchRequest,
        contract_sha: str,
        count: int,
    ) -> None:
        with _ticket_lock(Path(self.config.ticket_dir)):
            self._gc_expired_dispatch_tickets()
            self._write_dispatch_ticket_unlocked(request, contract_sha, count)

    def _write_dispatch_ticket_unlocked(
        self,
        request: DispatchRequest,
        contract_sha: str,
        count: int,
    ) -> None:
        ticket_dir = Path(self.config.ticket_dir)
        ticket_dir.mkdir(parents=True, exist_ok=True)

        runtime = request.runtime.lower()
        ticket_path = _dispatch_ticket_path(ticket_dir, runtime, contract_sha)
        if ticket_path is None:
            return

        payload = {
            "runtime": runtime,
            "contract_sha": contract_sha,
            "issued_ts": self._clock(),
            "count": max(1, count),
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

    def _valid_dispatch_tickets(
        self,
        runtime_filter: str | None = None,
    ) -> tuple[DispatchTicket, ...]:
        return self._dispatch_tickets(runtime_filter=runtime_filter, include_expired=False)

    def _dispatch_tickets(
        self,
        runtime_filter: str | None = None,
        *,
        include_expired: bool = False,
    ) -> tuple[DispatchTicket, ...]:
        self._gc_expired_dispatch_tickets()
        ticket_dir = Path(self.config.ticket_dir)
        if not ticket_dir.exists():
            return ()

        tickets: list[DispatchTicket] = []
        for path in sorted(ticket_dir.glob("*.json")):
            ticket = _decode_dispatch_ticket(path)
            if ticket is None:
                continue
            if runtime_filter is not None and ticket.runtime != runtime_filter:
                continue
            if not include_expired and self._ticket_is_expired(ticket):
                continue
            tickets.append(ticket)
        return tuple(tickets)

    def _gc_expired_dispatch_tickets(self) -> None:
        ticket_dir = Path(self.config.ticket_dir)
        if not ticket_dir.exists():
            return
        expires_before = self._clock() - (
            self.config.ticket_ttl_seconds + self.config.expired_ticket_gc_grace_seconds
        )
        for path in ticket_dir.glob("*.json"):
            ticket = _decode_dispatch_ticket(path)
            if ticket is None:
                continue
            if ticket.issued_ts < expires_before:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def _ticket_is_expired(self, ticket: DispatchTicket) -> bool:
        expires_before = self._clock() - self.config.ticket_ttl_seconds
        return ticket.issued_ts < expires_before

    def _read_dispatch_ticket(
        self,
        runtime: str,
        contract_sha: str,
    ) -> DispatchTicket | None:
        ticket_path = _dispatch_ticket_path(Path(self.config.ticket_dir), runtime, contract_sha)
        if ticket_path is None or not ticket_path.exists():
            return None
        return _decode_dispatch_ticket(ticket_path)


def _validate_request(request: DispatchRequest) -> ReasonCode | None:
    if (
        not isinstance(request.completion_channel, str)
        or request.completion_channel not in COMPLETION_CHANNELS
    ):
        return ReasonCode.NO_COMPLETION_CHANNEL
    if not isinstance(request.model, str) or not request.model.strip():
        return ReasonCode.NO_MODEL
    if request.model != request.model.strip():
        return ReasonCode.INVALID_REQUEST
    if request.tier_override is not None and (
        not isinstance(request.tier_override, str)
        or not request.tier_override.strip()
    ):
        return ReasonCode.INVALID_REQUEST
    if not request.runtime:
        return ReasonCode.INVALID_REQUEST
    if RUNTIME_PATTERN.fullmatch(request.runtime) is None:
        return ReasonCode.INVALID_REQUEST
    if request.est_input_chars is not None and request.est_input_chars < 0:
        return ReasonCode.INVALID_REQUEST
    if request.n_agents < 1:
        return ReasonCode.INVALID_REQUEST
    return None


def _load_tier_policy(path: Path) -> ModelTierPolicy:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(payload, dict) or isinstance(payload.get("version"), bool):
        raise ValueError("tier policy must be an object with a version")
    if payload.get("version") == 2:
        return _load_tier_policy_v2(payload, digest)
    if payload.get("version") != 1:
        raise ValueError("tier policy version must be 1 or 2")

    worker_allowed = _model_list(payload.get("worker_allowed"))
    worker_denied_tiers = _model_list(payload.get("worker_denied_tiers"))
    unknown_model = payload.get("unknown_model")
    if not isinstance(unknown_model, str) or unknown_model not in {"deny", "warn"}:
        raise ValueError("unknown_model must be deny or warn")
    if worker_allowed & worker_denied_tiers:
        raise ValueError("tier policy model sets must not overlap")
    return ModelTierPolicy(
        worker_allowed=worker_allowed,
        worker_denied_tiers=worker_denied_tiers,
        unknown_model=unknown_model,
        digest=digest,
    )


def _load_tier_policy_v2(payload: Mapping[str, object], digest: str) -> ModelTierPolicy:
    """Parse a version 2 policy: tiers plus a per-window agent cap for each.

    A model absent from every tier is `unknown`, which is a tier like any other
    and therefore capped like any other. That is the difference from version 1,
    where an unrecognised name was denied outright and a new model stayed blocked
    until someone edited this file by hand.
    """

    tiers = payload.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("tiers must be a non-empty object")
    model_tiers: dict[str, str] = {}
    for tier, models in tiers.items():
        if not isinstance(tier, str) or not tier.strip() or tier != tier.strip():
            raise ValueError("tier names must be non-empty and unpadded")
        if tier == UNKNOWN_TIER:
            raise ValueError(f"{UNKNOWN_TIER!r} is reserved for unlisted models")
        for model_key in _model_list(models):
            if model_key in model_tiers:
                raise ValueError("a model may not appear in two tiers")
            model_tiers[model_key] = tier

    caps_payload = payload.get("fanout_caps")
    if not isinstance(caps_payload, dict):
        raise ValueError("fanout_caps must be an object")
    fanout_caps: dict[str, int] = {}
    for tier, cap in caps_payload.items():
        if not isinstance(tier, str) or (tier != UNKNOWN_TIER and tier not in tiers):
            raise ValueError("fanout_caps names a tier that does not exist")
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
            raise ValueError("fanout_caps values must be non-negative integers")
        fanout_caps[tier] = cap
    if UNKNOWN_TIER not in fanout_caps:
        raise ValueError(
            f"fanout_caps must state a cap for {UNKNOWN_TIER!r}; "
            "leaving it unstated is the ambiguity this version removes"
        )

    window_seconds = payload.get("window_seconds", DEFAULT_TIER_WINDOW_SECONDS)
    if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or window_seconds <= 0:
        raise ValueError("window_seconds must be a positive integer")

    return ModelTierPolicy(
        unknown_model="cap",
        digest=digest,
        version=2,
        model_tiers=model_tiers,
        fanout_caps=fanout_caps,
        window_seconds=window_seconds,
    )


def _model_list(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        raise ValueError("model lists must be arrays")
    if any(not isinstance(model, str) or not model.strip() for model in value):
        raise ValueError("model identifiers must be non-empty strings")
    if any(model != model.strip() for model in value):
        raise ValueError("model identifiers must not have surrounding whitespace")
    return frozenset(model.casefold() for model in value)


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


@contextmanager
def _ticket_lock(ticket_dir: Path) -> Iterator[None]:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    lock_path = ticket_dir / ".dispatch-gate.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _decode_dispatch_ticket(path: Path) -> DispatchTicket | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    runtime = _string_or_none(payload.get("runtime"))
    contract_sha = _string_or_none(payload.get("contract_sha"))
    issued_ts = _number_or_none(payload.get("issued_ts"))
    count = _positive_int_or_none(payload.get("count"))
    if runtime is None or RUNTIME_PATTERN.fullmatch(runtime) is None:
        return None
    if contract_sha is None or re.fullmatch(r"[0-9a-f]{64}", contract_sha.lower()) is None:
        return None
    if issued_ts is None or count is None:
        return None

    expected_path = _dispatch_ticket_path(path.parent, runtime, contract_sha.lower())
    if expected_path is None or expected_path.name != path.name:
        return None
    return DispatchTicket(
        path=path,
        runtime=runtime,
        contract_sha=contract_sha.lower(),
        issued_ts=issued_ts,
        count=count,
    )


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _positive_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    return None


def _normalize_runtime_filter(runtime: str | None) -> str | None:
    if runtime is None:
        return None
    runtime_filter = runtime.strip().lower()
    if RUNTIME_PATTERN.fullmatch(runtime_filter) is None:
        return None
    return runtime_filter


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


def _candidate_sha_message(tickets: Sequence[DispatchTicket]) -> str:
    shas = sorted({ticket.contract_sha for ticket in tickets})
    if not shas:
        return "candidate_contract_shas=<none>"
    return "candidate_contract_shas=" + ",".join(shas)


def _candidate_sha_message_from_entries(entries: Sequence[Mapping[str, object]]) -> str:
    shas = sorted(
        {
            contract_sha
            for contract_sha in (_string_or_none(entry.get("contract_sha")) for entry in entries)
            if contract_sha is not None
        }
    )
    if not shas:
        return "candidate_contract_shas=<none>"
    return "candidate_contract_shas=" + ",".join(shas)
