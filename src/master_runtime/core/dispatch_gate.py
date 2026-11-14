"""Dispatch gate for worker scheduler requests."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

from master_runtime.core.dispatch_timeline import (
    default_ledger_path as _dispatch_timeline_default_ledger_path,
    state_dir as _dispatch_timeline_state_dir,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback keeps tests importable.
    fcntl = None


DEFAULT_SINGLE_DISPATCH_CHAR_LIMIT = 500_000
DEFAULT_BATCH_DISPATCH_CHAR_LIMIT = 1_000_000
DEFAULT_DUPLICATE_WINDOW_SECONDS = 30 * 60
DEFAULT_HIGH_COST_RUNTIMES = frozenset({"fable"})
DEFAULT_TIER_POLICY_RELATIVE_PATH = Path("master-ops") / "model-tier-policy.json"
DEFAULT_STANDING_RULES_RELATIVE_PATH = Path("master-ops") / "rules" / "standing-rules.md"
# Named "overlay", not "local": the repository's generic redaction scan
# flags any token shaped like "<word>.local" as a suspected internal
# hostname, and this file name is written into docs, scripts, and tests.
DEFAULT_STANDING_RULES_LOCAL_RELATIVE_PATH = (
    Path("master-ops") / "config" / "standing-rules.overlay.md"
)
# Instance-owned policy written during onboarding (agent-inventory consent).
# Preferred over the template fallback when present.
INSTANCE_TIER_POLICY_RELATIVE_PATH = Path("config") / "model-tier-policy.json"
# One day. The fan-out that caused the incident can be spread over sequential
# dispatches, so the cap counts agents inside a window rather than at once.
DEFAULT_TIER_WINDOW_SECONDS = 24 * 60 * 60
UNKNOWN_TIER = "unknown"
MODEL_NEEDS_MEASUREMENT = "needs measurement"
DEFAULT_TICKET_TTL_SECONDS = 600
DEFAULT_EXPIRED_TICKET_GC_GRACE_SECONDS = 24 * 60 * 60
MODEL_SESSION_ROOTS_ENV = "DISPATCH_MODEL_SESSION_ROOTS"
MODEL_SESSION_MAX_BYTES = 5 * 1024 * 1024
LEDGER_LOCK_FILENAME = "dispatch-ledger.lock"
LEDGER_LOCK_FD_ENV = "DISPATCH_LEDGER_LOCK_FD"
RUNTIME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
USERS_ABSOLUTE_PATH_PATTERN = re.compile(r"/Users/[^\s\"'`<>{}\[\](),;:]+")
COMPLETION_CHANNELS = frozenset({"orchestration", "sentinel-log"})
_MISSING = object()


def ledger_tier_policy_path(path: str | Path) -> str:
    """Render a tier policy path without exposing the user's home directory."""

    raw_path = os.fspath(path)
    if raw_path == "~" or raw_path.startswith(f"~{os.sep}"):
        return raw_path

    path_value = Path(raw_path)
    try:
        relative_path = path_value.relative_to(Path.home())
    except ValueError:
        return raw_path
    if not relative_path.parts:
        return "~"
    return str(Path("~") / relative_path)


def normalize_tier_policy_path(path: str) -> str:
    """Use one comparison key for absolute and home-relative policy paths."""

    return ledger_tier_policy_path(Path(os.path.expanduser(path)))


def _default_ledger_path() -> Path:
    value = os.environ.get("DISPATCH_GATE_LEDGER")
    if value:
        return Path(value)
    return _dispatch_timeline_default_ledger_path()


def _default_ticket_dir() -> Path:
    return _dispatch_timeline_state_dir() / "dispatch-tickets"


def _default_known_roots_path() -> Path:
    return _dispatch_timeline_state_dir() / "known-roots.json"


def _model_session_roots(
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, tuple[Path, ...]]:
    """Return the runtime session roots accepted as model evidence.

    The wrapper's transcript and rollout globs all live below these five
    runtime-owned trees. Tests can replace the complete allowlist with one
    path-list value without changing the production layout.
    """

    env = environ if environ is not None else os.environ
    override = env.get(MODEL_SESSION_ROOTS_ENV, "").strip()
    if override:
        roots = tuple(
            Path(item).expanduser().resolve()
            for item in override.split(os.pathsep)
            if item.strip()
        )
        return {
            runtime: roots
            for runtime in ("codex", "claude", "cursor", "agy", "grok")
        }
    codex_accounts = env.get("CODEX_ACCOUNTS_DIR")
    if not codex_accounts:
        codex_accounts = (
            Path.home() / "Library" / "Application Support" / "orca" / "codex-accounts"
            if sys.platform == "darwin"
            else Path.home() / ".local" / "share" / "orca" / "codex-accounts"
        )
    codex_root = Path(codex_accounts).expanduser()
    try:
        codex_sessions = tuple(
            (account / "home" / "sessions").resolve()
            for account in codex_root.iterdir()
            if account.is_dir() and (account / "home" / "sessions").is_dir()
        )
    except OSError:
        codex_sessions = ()
    cursor_projects = env.get("DISPATCH_CURSOR_SESSION_ROOT")
    agy_brain = env.get("DISPATCH_AGY_SESSION_ROOT")
    return {
        "codex": codex_sessions,
        "claude": ((Path.home() / ".claude" / "projects").resolve(),),
        "cursor": (
            (Path(cursor_projects).expanduser().resolve(),)
            if cursor_projects
            else ((Path.home() / ".cursor" / "projects").resolve(),)
        ),
        "agy": (
            (Path(agy_brain).expanduser().resolve(),)
            if agy_brain
            else (
                (Path.home() / ".gemini" / "antigravity-cli" / "brain").resolve(),
            )
        ),
        "grok": ((Path.home() / ".grok" / "sessions").resolve(),),
    }


def ledger_lock_path(ledger_path: str | Path) -> Path:
    """Return the one lock path shared by wrapper and gate writers."""

    return Path(ledger_path).expanduser().parent / LEDGER_LOCK_FILENAME


def model_session_root(
    runtime: str,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Return the first configured session root for a runtime."""

    roots = _model_session_roots(environ).get(runtime.casefold(), ())
    return roots[0] if roots else None


def _default_tier_policy_path(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the tier policy path with instance-first fallback.

    Order:
      1. DISPATCH_TIER_POLICY environment override
      2. instance file config/model-tier-policy.json when present
      3. template fallback master-ops/model-tier-policy.json

    ``repo_root`` and ``environ`` are injectable for tests; production callers
    leave them unset so the module's repository root and ``os.environ`` apply.
    Explicit ``--tier-policy`` on the CLI sits above this helper (caller sets
    ``DispatchGateConfig.tier_policy_path``).
    """
    env = environ if environ is not None else os.environ
    value = env.get("DISPATCH_TIER_POLICY")
    if value:
        return Path(value)
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    instance_path = root / INSTANCE_TIER_POLICY_RELATIVE_PATH
    if instance_path.is_file():
        return instance_path
    return root / DEFAULT_TIER_POLICY_RELATIVE_PATH


def _default_standing_rules_path(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the template-layer standing-rules file, env override first.

    An install's dispatch wrapper exports `DISPATCH_STANDING_RULES` pointing at
    its own `rules/standing-rules.md` before calling this gate, the same seam
    `DISPATCH_TIER_POLICY` already uses; without it this falls back to the
    template copy this repository ships, which is the file
    `scripts/dispatch-gate` reads when called bare, as the verification
    command does. This file refreshes on every template re-stamp.
    """

    env = environ if environ is not None else os.environ
    value = env.get("DISPATCH_STANDING_RULES")
    if value:
        return Path(value)
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    return root / DEFAULT_STANDING_RULES_RELATIVE_PATH


def _default_standing_rules_local_path(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the instance-owned standing-rules overlay, env override first.

    Lives under `config/`, which `template_common.py` already marks
    instance-owned, so a seat's own blocks here survive a template re-stamp
    that refreshes `rules/standing-rules.md` itself.
    """

    env = environ if environ is not None else os.environ
    value = env.get("DISPATCH_STANDING_RULES_LOCAL")
    if value:
        return Path(value)
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    return root / DEFAULT_STANDING_RULES_LOCAL_RELATIVE_PATH


class ReasonCode(str, Enum):
    """Stable gate decision reason codes."""

    OK = "OK"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ROUTING_VIOLATION = "ROUTING_VIOLATION"
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
    MODEL_TIER_ESCALATION = "MODEL_TIER_ESCALATION"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    MODEL_UNVERIFIED = "MODEL_UNVERIFIED"
    MODEL_PROBE_FAILED = "MODEL_PROBE_FAILED"
    MODEL_EVIDENCE_MISSING = "MODEL_EVIDENCE_MISSING"
    MODEL_EVIDENCE_INVALID = "MODEL_EVIDENCE_INVALID"
    MODEL_EVIDENCE_OUTSIDE_ROOT = "MODEL_EVIDENCE_OUTSIDE_ROOT"
    MODEL_EVIDENCE_STALE = "MODEL_EVIDENCE_STALE"
    MODEL_EVIDENCE_TOO_LARGE = "MODEL_EVIDENCE_TOO_LARGE"
    MODEL_EVIDENCE_UNBOUND = "MODEL_EVIDENCE_UNBOUND"
    MODEL_NOT_PENDING = "MODEL_NOT_PENDING"
    UNKNOWN_RUNTIME = "UNKNOWN_RUNTIME"
    CONTRACT_FRONT_MATTER = "CONTRACT_FRONT_MATTER"
    CONTRACT_FRONT_MATTER_MISSING = "CONTRACT_FRONT_MATTER_MISSING"
    CONTRACT_TIER_MISMATCH = "CONTRACT_TIER_MISMATCH"
    CONTRACT_RUNTIME_MISMATCH = "CONTRACT_RUNTIME_MISMATCH"
    RUNTIME_NOT_ELIGIBLE = "RUNTIME_NOT_ELIGIBLE"
    STANDING_RULE_UNKNOWN = "STANDING_RULE_UNKNOWN"


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
    model_needs_measurement: bool = False


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
    front_matter: Mapping[str, object] | None = None
    model_status: str | None = None


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
    standing_rules_path: str | Path = field(default_factory=_default_standing_rules_path)
    standing_rules_local_path: str | Path = field(
        default_factory=_default_standing_rules_local_path
    )


@dataclass(frozen=True)
class DispatchTicket:
    """Valid on-disk dispatch ticket."""

    path: Path
    runtime: str
    contract_sha: str
    issued_ts: float
    count: int


@dataclass(frozen=True)
class RegistrationCandidate:
    """Pending dispatch selected for registration."""

    pending: Mapping[str, object]
    selected_ticket: DispatchTicket | None


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
    runtimes: frozenset[str] | None = None
    # Named tiers the policy declares, independent of whether any model is
    # currently assigned to one: an empty-model tier is still a valid name a
    # contract's front matter may declare. Empty for a version 1 policy, which
    # has no named-tier concept at all.
    tier_names: frozenset[str] = frozenset()

    def tier_of(self, model_key: str) -> str:
        """Return the tier for a casefolded model id, or the unknown tier."""

        return self.model_tiers.get(model_key, UNKNOWN_TIER)

    def cap_for(self, tier: str) -> int | None:
        """Agents permitted per window for a tier. None means uncapped."""

        cap = self.fanout_caps.get(tier)
        return cap if isinstance(cap, int) else None

    def strictness_of(self, tier: str) -> float:
        """How closely the policy watches a tier, as its per-window cap.

        Smaller is stricter. An uncapped tier is the loosest thing the policy
        knows, so it sorts last. This is deliberately the cap rather than a
        separate ordering field: the policy already says how much it trusts each
        tier, and inventing a second ranking would let the two disagree.
        """

        cap = self.cap_for(tier)
        return float("inf") if cap is None else float(cap)


class DispatchGate:
    """Evaluate dispatch requests and maintain an append-only JSONL ledger."""

    def __init__(
        self,
        config: DispatchGateConfig | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or DispatchGateConfig()
        self._clock = clock or time.time

    def check(self, request: DispatchRequest, *, record: bool = True) -> GateDecision:
        """Return a gate decision, optionally appending it to the ledger."""

        def append_decision(decision: GateDecision) -> None:
            if record:
                self._append_decision(request, decision)

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
            append_decision(decision)
            return decision

        validation_error = _validate_request(request)
        if validation_error is not None:
            decision = GateDecision(False, validation_error)
            append_decision(decision)
            return decision

        try:
            tier_policy = _load_tier_policy(Path(self.config.tier_policy_path))
        except (OSError, ValueError, json.JSONDecodeError):
            decision = GateDecision(
                False,
                ReasonCode.TIER_POLICY_UNAVAILABLE,
                message=f"tier_policy={self.config.tier_policy_path}",
            )
            append_decision(decision)
            return decision

        self._tier_policy_digest = tier_policy.digest
        runtime = request.runtime.casefold()
        if tier_policy.runtimes is not None and runtime not in tier_policy.runtimes:
            # Keep behavior unchanged when policy omits runtimes during rollout.
            decision = GateDecision(
                False,
                ReasonCode.UNKNOWN_RUNTIME,
                message=f"runtime={request.runtime}",
            )
            append_decision(decision)
            return decision

        tier_warning: ReasonCode | None = None
        model_status = (
            MODEL_NEEDS_MEASUREMENT if request.model_needs_measurement else None
        )
        tier_override: str | None = None
        model = request.model.strip() if request.model is not None else ""
        # Casefolded: a denied tier spelled in another case is the same tier.
        model_key = model.casefold()

        if tier_policy.version >= 2:
            tier = tier_policy.tier_of(model_key)
            self._tier = tier
            cap = tier_policy.cap_for(tier)
            if cap is not None and tier != UNKNOWN_TIER:
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
                        append_decision(decision)
                        return decision
                    tier_override = request.tier_override.strip()
            # An unlisted model resolves to the unknown tier rather than being
            # blocked outright, so a newer or cheaper model is usable before
            # anyone edits the policy. An unknown-tier fanout cap is ignored
            # so this observation gap never blocks dispatch. It never passes
            # silently: the tier lands in the ledger and the warning surfaces
            # it in the rollup.
            if tier == UNKNOWN_TIER:
                tier_warning = ReasonCode.TIER_UNKNOWN_MODEL
                model_status = MODEL_NEEDS_MEASUREMENT

        elif model_key not in tier_policy.worker_allowed:
            # An id absent from the policy is an observation gap. The legacy
            # v1 `unknown_model=deny` switch predates the current rule that a
            # newer id must remain dispatchable, so only an explicitly named
            # denied id can still refuse here.
            policy_denies = model_key in tier_policy.worker_denied_tiers
            if policy_denies:
                if request.tier_override is None:
                    decision = GateDecision(
                        False,
                        ReasonCode.TIER_POLICY,
                        message=f"model={model}",
                    )
                    append_decision(decision)
                    return decision
                tier_override = request.tier_override.strip()
            else:
                tier_warning = ReasonCode.TIER_POLICY
                model_status = MODEL_NEEDS_MEASUREMENT

        try:
            contract_content = _contract_content(request.contract_path)
        except FileNotFoundError:
            decision = GateDecision(False, ReasonCode.CONTRACT_UNREADABLE)
            append_decision(decision)
            return decision
        contract_sha = _contract_sha_from_content(contract_content)
        lint_warnings = _contract_lint_warnings(
            contract_content.decode("utf-8", errors="replace"),
            Path(self.config.known_roots_path),
        )
        if tier_warning is not None:
            lint_warnings = (*lint_warnings, tier_warning)

        front_matter_result, front_matter_error = _parse_front_matter(
            contract_content.decode("utf-8", errors="replace")
        )
        if front_matter_error is not None:
            decision = GateDecision(
                False,
                ReasonCode.CONTRACT_FRONT_MATTER,
                warnings=lint_warnings,
                contract_sha=contract_sha,
                message=front_matter_error,
            )
            append_decision(decision)
            return decision
        if front_matter_result is None:
            # Warning release: a missing block does not change the decision.
            lint_warnings = (*lint_warnings, ReasonCode.CONTRACT_FRONT_MATTER_MISSING)
        else:
            normalized, error_reason, error_message = _validate_front_matter(
                front_matter_result,
                request,
                tier_policy,
                self._tier or UNKNOWN_TIER,
                Path(self.config.standing_rules_path),
                Path(self.config.standing_rules_local_path),
            )
            if error_reason is not None:
                # front_matter is exposed only on a decision whose block
                # passed full validation: the raw parsed dict here may hold
                # a value that failed shape-checking (an un-coerced budget
                # entry, for one), and showing it under the same field a
                # caller trusts for the validated form would be misleading.
                decision = GateDecision(
                    False,
                    error_reason,
                    warnings=lint_warnings,
                    contract_sha=contract_sha,
                    message=error_message,
                )
                append_decision(decision)
                return decision
            front_matter_result = normalized

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
                front_matter=front_matter_result,
            )
            append_decision(decision)
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
                front_matter=front_matter_result,
            )
            append_decision(decision)
            return decision

        runtime = request.runtime.lower()
        if runtime in self.config.high_cost_runtimes and request.n_agents >= 2:
            decision = GateDecision(
                allow=False,
                reason=ReasonCode.ROUTING_VIOLATION,
                warnings=lint_warnings,
                contract_sha=contract_sha,
                cost_proxy=cost_proxy,
                front_matter=front_matter_result,
            )
            append_decision(decision)
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
            front_matter=front_matter_result,
            model_status=model_status,
        )
        append_decision(decision)
        if record:
            self._issue_dispatch_ticket(request, decision)
        return decision

    def register_job(
        self,
        job_id: str,
        probe_fn: Callable[[str], bool],
        contract_sha: str | None = None,
        runtime: str | None = None,
        orchestration_task: str | None = None,
        declared_model: str | None = None,
        measured_model: str | None = None,
        model_probe_failed: bool = False,
        expected_completion_channel: str | None = None,
        worker_pid: str | None = None,
        pane: str | None = None,
        card: str | None = None,
        card_reason: str | None = None,
        token_budget: int | None = None,
        tokens_basis: str = "total",
        token_budget_source: str | None = None,
    ) -> GateDecision:
        """Register a job only after independent probe verification succeeds."""

        if not job_id or not probe_fn(job_id):
            return GateDecision(False, ReasonCode.UNVERIFIED_JOB)

        # check gates the model a caller declares; nothing until here compared
        # that declaration with what the worker actually runs. The incident this
        # policy exists for was a worker inheriting a tier nobody asked for, and
        # a compliant declaration does not prevent it.
        model_warning, escalation = self._model_verification(
            declared_model, measured_model, model_probe_failed
        )
        if escalation is not None:
            decision = GateDecision(
                False,
                ReasonCode.MODEL_TIER_ESCALATION,
                message=escalation,
            )
            with _ledger_lock(Path(self.config.ledger_path)):
                self._append_entry(
                    {
                        "ts": self._clock(),
                        "decision": "DENY",
                        "reason": decision.reason.value,
                        "job_id": job_id,
                        "model_declared": declared_model,
                        "model_measured": measured_model,
                        "model_verified": True,
                    }
                )
            return decision

        runtime_filter = _normalize_runtime_filter(runtime)
        if runtime is not None and runtime_filter is None:
            return GateDecision(False, ReasonCode.INVALID_REQUEST)
        if token_budget is not None and (
            isinstance(token_budget, bool) or not isinstance(token_budget, int) or token_budget < 0
        ):
            return GateDecision(
                False,
                ReasonCode.INVALID_REQUEST,
                message="token_budget must be a non-negative integer",
            )
        if not isinstance(tokens_basis, str) or tokens_basis not in {"total", "uncached"}:
            return GateDecision(
                False,
                ReasonCode.INVALID_REQUEST,
                message="tokens_basis must be total or uncached",
            )

        with _ledger_lock(Path(self.config.ledger_path)):
            with _ticket_lock(Path(self.config.ticket_dir)):
                candidate, denial = self._registration_candidate(
                    contract_sha,
                    runtime_filter,
                )
                if denial is not None:
                    return denial
                assert candidate is not None
                pending = candidate.pending
                selected_ticket = candidate.selected_ticket
                completion_channel = _string_or_none(pending.get("completion_channel"))
                pending_model_status = _string_or_none(pending.get("model_status"))

                if (
                    expected_completion_channel is not None
                    and completion_channel != expected_completion_channel
                ):
                    actual_channel = (
                        completion_channel if completion_channel is not None else "<none>"
                    )
                    return GateDecision(
                        False,
                        ReasonCode.INVALID_REQUEST,
                        message=(
                            f"expected_completion_channel={expected_completion_channel} "
                            f"actual_completion_channel={actual_channel}"
                        ),
                    )

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
                    model_status=pending_model_status,
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
                    "completion_channel": completion_channel,
                }
                dispatch_started_ts = _number_or_none(pending.get("ts"))
                if dispatch_started_ts is not None:
                    entry["dispatch_started_ts"] = dispatch_started_ts
                if orchestration_task is not None:
                    entry["orchestration_task"] = orchestration_task
                contract_repo = pending.get("contract_repo")
                if isinstance(contract_repo, str) and contract_repo:
                    entry["contract_repo"] = contract_repo
                # A caller expanding an unset shell variable can pass an empty or
                # whitespace-only value; worker-wait treats any present worker_pid
                # as measured, and an empty one would read as a live-but-not-alive
                # pid, i.e. DEAD, for a worker that was never actually recorded.
                if worker_pid and worker_pid.strip():
                    entry["worker_pid"] = worker_pid.strip()
                if pane and pane.strip():
                    entry["pane"] = pane.strip()
                # The card fields are optional for the Python API so older callers
                # and ledgers remain readable. The supervised wrapper supplies one
                # of them for every new dispatch registration.
                if card is not None or card_reason is not None:
                    entry["card"] = card.strip() if card is not None else ""
                    entry["card_reason"] = card_reason.strip() if card_reason is not None else ""
                # Keep the declared budget beside the measured usage. ``None``
                # is deliberate for a tier with no measured default; it is
                # different from an observed zero.
                entry["token_budget"] = token_budget
                entry["tokens_basis"] = tokens_basis
                if token_budget_source:
                    entry["token_budget_source"] = token_budget_source
                # Say what was verified and how, so a later reader can tell an
                # unverified registration from a verified one instead of assuming.
                entry["model_declared"] = declared_model
                # A model mark comes from a dispatch whose declaration was not
                # independently grounded in the host's policy or offered list.
                # The register-time probe is useful context, but it is not the
                # worker_done evidence pair that is allowed to clear the mark.
                if pending_model_status == MODEL_NEEDS_MEASUREMENT:
                    entry["model_measured"] = None
                    entry["model_verified"] = False
                else:
                    entry["model_measured"] = measured_model
                    entry["model_verified"] = bool(
                        declared_model and measured_model and not model_probe_failed
                    )
                if pending_model_status is not None:
                    entry["model_status"] = pending_model_status
                if model_warning is not None:
                    entry["warnings"] = [
                        *entry.get("warnings", []),
                        model_warning.value,
                    ]
                entry["attempt"] = self._next_attempt(str(pending["contract_sha"]))
                self._append_entry(entry)
        if model_warning is not None:
            decision = GateDecision(
                decision.allow,
                decision.reason,
                warnings=(*decision.warnings, model_warning),
                contract_sha=decision.contract_sha,
                cost_proxy=decision.cost_proxy,
                message=decision.message,
                tier_override=decision.tier_override,
                model_status=decision.model_status,
            )
        return decision

    def settle_usage(
        self,
        dispatch_id: str,
        usage: Mapping[str, object],
    ) -> GateDecision:
        """Attach one measured or explicitly unmeasured usage result.

        Settlement is safe to call from both a worker-done path and a reap
        path.  The first result wins, so a late duplicate observation cannot
        replace the evidence already recorded for the dispatch.
        """

        if not dispatch_id or not isinstance(usage, Mapping):
            return GateDecision(False, ReasonCode.INVALID_REQUEST, message="dispatch_id and usage are required")
        source = usage.get("source")
        if not isinstance(source, str) or not source:
            return GateDecision(False, ReasonCode.INVALID_REQUEST, message="usage.source is required")
        normalized = dict(usage)
        with _ledger_lock(Path(self.config.ledger_path)):
            entries = list(self._read_entries())
            found = False
            changed = False
            replaced_unmeasured = False
            for entry in entries:
                if entry.get("job_id") != dispatch_id:
                    continue
                found = True
                if "token_usage" in entry:
                    existing = entry.get("token_usage")
                    existing_source = (
                        existing.get("source")
                        if isinstance(existing, Mapping)
                        else None
                    )
                    if existing_source == "unmeasured" and source != "unmeasured":
                        entry["token_usage"] = normalized
                        entry["token_usage_settled"] = True
                        changed = True
                        replaced_unmeasured = True
                    break
                entry["token_usage"] = normalized
                entry["token_usage_settled"] = True
                changed = True
                break
            if not found:
                entries.append(
                    {
                        "ts": self._clock(),
                        "job_id": dispatch_id,
                        "token_usage": normalized,
                        "token_usage_settled": True,
                        "settlement_without_registration": True,
                    }
                )
                changed = True
            if changed:
                _replace_ledger_entries(Path(self.config.ledger_path), entries)
        if replaced_unmeasured:
            message = "usage upgraded from unmeasured"
        elif changed:
            message = "usage recorded without registration" if not found else "usage recorded"
        else:
            message = "usage already settled"
        return GateDecision(True, ReasonCode.OK, message=message)

    def completion_channel_for_registration(
        self,
        contract_sha: str | None = None,
        runtime: str | None = None,
    ) -> str | None:
        """Return the check channel for the pending dispatch register would use."""

        runtime_filter = _normalize_runtime_filter(runtime)
        if runtime is not None and runtime_filter is None:
            return None

        with _ledger_lock(Path(self.config.ledger_path)), _ticket_lock(
            Path(self.config.ticket_dir)
        ):
            candidate, denial = self._registration_candidate(
                contract_sha,
                runtime_filter,
            )
        if denial is not None or candidate is None:
            return None
        return _string_or_none(candidate.pending.get("completion_channel"))

    def _registration_candidate(
        self,
        contract_sha: str | None,
        runtime_filter: str | None,
    ) -> tuple[RegistrationCandidate | None, GateDecision | None]:
        tickets = self._valid_dispatch_tickets(runtime_filter=runtime_filter)
        if contract_sha is not None:
            contract_sha_filter = _normalize_contract_sha_filter(contract_sha)
            if contract_sha_filter is None:
                return None, GateDecision(False, ReasonCode.INVALID_REQUEST)
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
                return None, GateDecision(
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
                if not matching_pending:
                    return None, GateDecision(
                        False,
                        ReasonCode.NO_MATCHING_TICKET,
                        message=_candidate_sha_message(matching_tickets),
                    )
            else:
                if all_tickets:
                    return None, GateDecision(
                        False,
                        ReasonCode.NO_MATCHING_TICKET,
                        message=_candidate_sha_message(all_tickets),
                    )
                matching_pending = tuple(
                    entry
                    for entry in pending_dispatches
                    if _contract_sha_matches(
                        entry.get("contract_sha"),
                        contract_sha_filter,
                    )
                    and (
                        runtime_filter is None
                        or _string_or_none(entry.get("runtime")) == runtime_filter
                    )
                )
                if len(matching_pending) > 1:
                    return None, GateDecision(
                        False,
                        ReasonCode.AMBIGUOUS_TICKET,
                        message=_candidate_sha_message_from_entries(matching_pending),
                    )
                if not matching_pending:
                    return None, GateDecision(
                        False,
                        ReasonCode.NO_MATCHING_TICKET,
                        message=_candidate_sha_message(all_tickets),
                    )
        else:
            if not tickets:
                return None, GateDecision(
                    False,
                    ReasonCode.NO_MATCHING_TICKET,
                    message=_candidate_sha_message(tickets),
                )
            if len(tickets) > 1:
                return None, GateDecision(
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
                return None, GateDecision(
                    False,
                    ReasonCode.NO_MATCHING_TICKET,
                    message=_candidate_sha_message(tickets),
                )

        return RegistrationCandidate(matching_pending[0], selected_ticket), None

    def ledger_entries(self) -> tuple[Mapping[str, object], ...]:
        """Return parsed ledger entries in append order."""

        return tuple(self._read_entries())

    def measure_model(
        self,
        dispatch_id: str,
        session_record: str | Path,
        evidence_line: str,
    ) -> GateDecision:
        """Verify a worker-reported session line and clear its model mark.

        The worker's path and line are pointers supplied by the worker. They
        are claims until this method opens the record, finds the exact line,
        and extracts a model id from that line. A missing or malformed line
        leaves ``model_status=needs measurement`` in place.
        """

        if not dispatch_id.strip() or not evidence_line.strip():
            return GateDecision(False, ReasonCode.INVALID_REQUEST)
        with _ledger_lock(Path(self.config.ledger_path)), _ticket_lock(
            Path(self.config.ticket_dir)
        ):
            entries = list(self._read_entries())
            target_index: int | None = None
            for index, entry in enumerate(entries):
                if (
                    isinstance(entry, Mapping)
                    and entry.get("job_id") == dispatch_id
                    and entry.get("decision") == "ALLOW"
                ):
                    target_index = index
            if target_index is None:
                return GateDecision(
                    False,
                    ReasonCode.NO_MATCHING_TICKET,
                    message=f"dispatch_id={dispatch_id}",
                )
            target = dict(entries[target_index])
            if target.get("model_status") != MODEL_NEEDS_MEASUREMENT:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_NOT_PENDING,
                    message=f"dispatch_id={dispatch_id}",
                )

            placement = _dispatch_placement(entries, dispatch_id, target)
            record_path = Path(session_record).expanduser()
            try:
                record_path = record_path.resolve(strict=True)
            except OSError:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_MISSING,
                    message=f"session_record={record_path}",
                )
            runtime = _string_or_none(target.get("runtime"))
            session_roots = _model_session_roots()
            roots = session_roots.get(runtime, ()) if runtime else ()
            if not any(_path_is_under(record_path, root) for root in roots):
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_OUTSIDE_ROOT,
                    message=f"session_record={record_path}",
                )

            dispatch_ts = _number_or_none(target.get("dispatch_started_ts"))
            if dispatch_ts is None:
                dispatch_ts = _number_or_none(target.get("ts"))
            if dispatch_ts is None:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message=f"dispatch_id={dispatch_id} has no timestamp",
                )
            try:
                record_stat = record_path.stat()
            except OSError:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_MISSING,
                    message=f"session_record={record_path}",
                )
            if not stat.S_ISREG(record_stat.st_mode):
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message=f"session_record={record_path} is not a regular file",
                )
            if record_stat.st_mtime < dispatch_ts:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_STALE,
                    message=f"session_record={record_path} predates dispatch",
                )
            if record_stat.st_size > MODEL_SESSION_MAX_BYTES:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_TOO_LARGE,
                    message=(
                        f"session_record={record_path} exceeds "
                        f"{MODEL_SESSION_MAX_BYTES} bytes"
                    ),
                )
            try:
                record_text = record_path.read_bytes().decode("utf-8")
            except (OSError, UnicodeError):
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message=f"session_record={record_path}",
                )
            _, _, session_start = _record_context(record_text, runtime)
            if session_start is not None and session_start < dispatch_ts:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_STALE,
                    message=f"session_record={record_path} session predates dispatch",
                )
            normalized_line = evidence_line.rstrip("\r\n")
            record_lines = record_text.splitlines()
            evidence_line_number = next(
                (
                    index
                    for index, line in enumerate(record_lines, start=1)
                    if line == normalized_line
                ),
                None,
            )
            if evidence_line_number is None:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_MISSING,
                    message="quoted model line is absent from session record",
                )
            try:
                evidence = json.loads(normalized_line)
            except json.JSONDecodeError:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message="quoted model line is not JSON",
                )
            measured_model = _model_from_evidence(evidence, runtime)
            if measured_model is None:
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message="quoted model line has no model field",
                )
            if not isinstance(evidence, Mapping):
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_INVALID,
                    message="quoted model line is not a JSON object",
                )
            if not _record_belongs_to_dispatch(
                target,
                placement,
                record_path,
                record_text,
                session_roots,
            ):
                return GateDecision(
                    False,
                    ReasonCode.MODEL_EVIDENCE_UNBOUND,
                    message=f"session_record={record_path} is not bound to dispatch",
                )

            declared_model = _string_or_none(target.get("model_declared"))
            if declared_model is None:
                declared_model = _string_or_none(target.get("model"))
            record_model_turns_with_keys = _record_model_turns_with_keys(
                record_text, runtime
            )
            record_model_turns = tuple(
                models for _, models in record_model_turns_with_keys
            )
            record_models = tuple(
                model for turn in record_model_turns for model in turn
            )
            if runtime in {"codex", "claude"} and record_model_turns:
                authoritative_models = {
                    model.casefold() for model in record_models
                }
                if measured_model.casefold() not in authoritative_models:
                    return GateDecision(
                        False,
                        ReasonCode.MODEL_EVIDENCE_INVALID,
                        message="quoted model line is not a runtime-authoritative model field",
                    )
            evidence_turn_key = _record_turn_key(evidence, evidence_line_number)
            evidence_model_turns = tuple(
                turn
                for key, turn in record_model_turns_with_keys
                if key == evidence_turn_key
            )
            matches = (
                declared_model is not None
                and _model_matches_declared(
                    measured_model, declared_model, evidence_model_turns
                )
                and all(
                    _model_matches_declared(model, declared_model, record_model_turns)
                    for model in record_models
                )
            )
            target["model_measured"] = measured_model
            target["model_record"] = _relative_model_record_path(
                record_path, roots
            )
            target["model_evidence_line_number"] = evidence_line_number
            target["model_evidence_sha256"] = hashlib.sha256(
                normalized_line.encode("utf-8")
            ).hexdigest()
            target.pop("model_status", None)
            target["model_verified"] = matches
            if matches:
                target.pop("model_mismatch", None)
                warnings = target.get("warnings")
                if isinstance(warnings, list):
                    warning_values = [
                        warning
                        for warning in warnings
                        if warning != ReasonCode.MODEL_MISMATCH.value
                    ]
                    if warning_values:
                        target["warnings"] = warning_values
                    else:
                        target.pop("warnings", None)
            else:
                target["model_mismatch"] = True
                warnings = target.get("warnings")
                warning_values = list(warnings) if isinstance(warnings, list) else []
                if ReasonCode.MODEL_MISMATCH.value not in warning_values:
                    warning_values.append(ReasonCode.MODEL_MISMATCH.value)
                target["warnings"] = warning_values
            entries[target_index] = target
            _replace_ledger_entries(Path(self.config.ledger_path), entries)

        warnings = (ReasonCode.MODEL_MISMATCH,) if not matches else ()
        return GateDecision(
            True,
            ReasonCode.OK,
            warnings=warnings,
            message=("model mismatch" if not matches else "model measured"),
            model_status=("mismatch" if not matches else "measured"),
        )

    def _model_verification(
        self,
        declared_model: str | None,
        measured_model: str | None,
        probe_failed: bool,
    ) -> tuple[ReasonCode | None, str | None]:
        """Compare a declared worker model with a measured one.

        Returns a warning code and, when the measured model sits in a tier the
        policy watches more closely than the declared one, the message for a
        denial. An absent measurement is a warning rather than a denial on
        purpose: a runtime with no way to report its model would otherwise be
        unable to dispatch at all, and a check nobody can satisfy is a check
        nobody enables. What is never allowed to pass quietly is the case where a
        measurement exists and disagrees upward.
        """

        if not declared_model:
            return ReasonCode.MODEL_UNVERIFIED, None
        if probe_failed:
            return ReasonCode.MODEL_PROBE_FAILED, None
        if not measured_model:
            return ReasonCode.MODEL_UNVERIFIED, None
        if measured_model.strip().casefold() == declared_model.strip().casefold():
            return None, None

        try:
            policy = _load_tier_policy(Path(self.config.tier_policy_path))
        except (OSError, ValueError, json.JSONDecodeError):
            # Cannot rank the two without a policy, and a mismatch is still a
            # mismatch worth recording.
            return ReasonCode.MODEL_MISMATCH, None
        if policy.version < 2:
            return ReasonCode.MODEL_MISMATCH, None

        declared_tier = policy.tier_of(declared_model.strip().casefold())
        measured_tier = policy.tier_of(measured_model.strip().casefold())
        if declared_tier == UNKNOWN_TIER:
            return ReasonCode.MODEL_MISMATCH, None
        if policy.strictness_of(measured_tier) < policy.strictness_of(declared_tier):
            return None, (
                f"declared={declared_model} tier={declared_tier} "
                f"measured={measured_model} tier={measured_tier}"
            )
        return ReasonCode.MODEL_MISMATCH, None

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
        model_status = decision.model_status
        if model_status is None and request.model_needs_measurement:
            model_status = MODEL_NEEDS_MEASUREMENT
        if model_status is not None:
            entry["model_status"] = model_status
        if decision.warnings:
            entry["warnings"] = [warning.value for warning in decision.warnings]
        if decision.tier_override is not None:
            entry["tier_override"] = decision.tier_override
        if decision.front_matter is not None:
            # Reject-unknown: serialise only the keys the schema names, so a
            # row never carries a field the schema does not define even if a
            # future bug let one slip past validation above.
            entry["front_matter"] = {
                key: decision.front_matter[key]
                for key in FRONT_MATTER_KNOWN_KEYS
                if key in decision.front_matter
            }
            repo = decision.front_matter.get("repo")
            if isinstance(repo, str) and repo:
                entry["contract_repo"] = repo
        # Which policy decided. The path is caller-supplied through --tier-policy
        # or DISPATCH_TIER_POLICY, so an ALLOW that names neither path nor digest
        # cannot be told apart from one a substituted policy allowed.
        if getattr(self, "_tier", ""):
            entry["tier"] = self._tier
        entry["tier_policy_path"] = ledger_tier_policy_path(
            self.config.tier_policy_path
        )
        if getattr(self, "_tier_policy_digest", ""):
            entry["tier_policy_sha256"] = self._tier_policy_digest
        if decision.allow and decision.contract_sha is not None:
            with _ledger_lock(Path(self.config.ledger_path)):
                with _ticket_lock(Path(self.config.ticket_dir)):
                    entry["attempt"] = self._next_attempt(decision.contract_sha)
                    self._append_entry(entry)
            return
        with _ledger_lock(Path(self.config.ledger_path)):
            self._append_entry(entry)

    def append_ledger_entry(self, entry: Mapping[str, object]) -> None:
        """Append an externally prepared denial entry under the gate lock."""

        if entry.get("decision") != "DENY":
            raise ValueError("append_ledger_entry accepts DENY entries only")

        with _ledger_lock(Path(self.config.ledger_path)):
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

    def _next_attempt(self, contract_sha: str) -> int:
        return 1 + sum(
            1
            for entry in self._read_entries()
            if entry.get("contract_sha") == contract_sha
            and entry.get("decision") == "ALLOW"
        )

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


FRONT_MATTER_DELIMITER = "---"
FRONT_MATTER_KNOWN_KEYS = frozenset(
    {"tier", "runtime", "repo", "budget", "tokens_basis", "writes", "standing_rules"}
)
FRONT_MATTER_REQUIRED_KEYS = ("tier", "runtime", "repo")
FRONT_MATTER_BUDGET_INT_NAMES = frozenset({"rounds", "hours", "tokens"})


def _parse_front_matter(text: str) -> tuple[dict[str, object] | None, str | None]:
    """Parse a contract's optional front matter block.

    Grammar: a first line "---", then flat "key: value" lines, then a line
    "---". A value is a bare scalar, or a list written "[a, b, c]" on one
    line. Nothing nested, no quoting beyond trimming surrounding spaces, no
    PyYAML (stdlib only, by design).

    Returns ``(parsed, None)`` when a block is present and well formed (an
    empty dict for a block with no lines), ``(None, None)`` when the text does
    not open with a front matter block at all, or ``(None, error)`` where
    ``error`` already names the offending key or line number.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return None, None

    parsed: dict[str, object] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        if line.strip() == FRONT_MATTER_DELIMITER:
            return parsed, None
        if ":" not in line:
            return None, f"line {line_number}: not a key: value line"
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()
        if key not in FRONT_MATTER_KNOWN_KEYS:
            return None, f"unknown key: {key}"
        if key in parsed:
            return None, f"line {line_number}: duplicate key: {key}"
        if raw_value.startswith("["):
            if not raw_value.endswith("]"):
                return None, f"line {line_number}: unterminated list"
            inner = raw_value[1:-1].strip()
            items = [] if not inner else [item.strip() for item in inner.split(",")]
            if any(not item for item in items):
                return None, f"line {line_number}: malformed list"
            parsed[key] = items
        else:
            parsed[key] = raw_value
    return None, f"line {len(lines) + 1}: unterminated front matter block"


def _known_standing_rule_names(
    standing_rules_path: Path, standing_rules_local_path: Path
) -> frozenset[str]:
    """Block names declared by ``## <name>`` headings in the rules file(s).

    A seat's local overlay joins the template file's own names, so a contract
    may reference a block either file declares.
    """

    names: set[str] = set()
    for path in (standing_rules_path, standing_rules_local_path):
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # An unreadable or malformed rules file contributes no names
            # instead of crashing the gate; a name a contract declares still
            # refuses, as a clean STANDING_RULE_UNKNOWN, never an exception.
            continue
        for line in text.splitlines():
            if line.startswith("## "):
                names.add(line[3:].strip())
    return frozenset(names)


# Lowercase, hyphenated token shape: matches the five canonical blocks
# (headless, ack-token, ...) and rejects a name that would break the
# dispatch wrapper's unquoted, space-joined shell loop over the names this
# gate allows through (a space, quote, or shell metacharacter).
STANDING_RULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def _validate_front_matter(
    front_matter: Mapping[str, object],
    request: DispatchRequest,
    tier_policy: ModelTierPolicy,
    computed_tier: str,
    standing_rules_path: Path,
    standing_rules_local_path: Path,
) -> tuple[dict[str, object] | None, ReasonCode | None, str]:
    """Validate a parsed front matter block against this check's context.

    Returns ``(normalized, None, "")`` on success, where ``normalized`` is a
    fresh dict (budget values coerced to int/float); the input is never
    mutated. Returns ``(None, reason, message)`` on the first refusal, in the
    order the contract fixes: required keys and shape, tier, runtime
    eligibility then runtime match, budget, writes, standing_rules.
    """

    for key in FRONT_MATTER_REQUIRED_KEYS:
        value = front_matter.get(key)
        if key not in front_matter:
            return None, ReasonCode.CONTRACT_FRONT_MATTER, f"missing required key: {key}"
        if not isinstance(value, str) or not value.strip():
            return (
                None,
                ReasonCode.CONTRACT_FRONT_MATTER,
                f"{key} must be a non-empty scalar",
            )

    declared_tier = front_matter["tier"].strip()
    # "unknown" is reserved and never appears in tier_names (the v2 loader
    # refuses a policy that names it as a real tier), so an unlisted model's
    # own computed tier of "unknown" could never match a declared tier by the
    # membership check alone; a contract correctly describing that model has
    # to be able to say so.
    known_tier = declared_tier in tier_policy.tier_names or (
        declared_tier == UNKNOWN_TIER and computed_tier == UNKNOWN_TIER
    )
    if not known_tier or declared_tier != computed_tier:
        return (
            None,
            ReasonCode.CONTRACT_TIER_MISMATCH,
            f"front_matter_tier={declared_tier} model_tier={computed_tier}",
        )

    declared_runtime = front_matter["runtime"].strip().casefold()
    # No policy shape joins a runtime to a tier today (measured: `tiers` names
    # model ids, not runtimes), so eligibility falls back to the policy's
    # whole runtime list for every tier until that join exists.
    if tier_policy.runtimes is not None and declared_runtime not in tier_policy.runtimes:
        return (
            None,
            ReasonCode.RUNTIME_NOT_ELIGIBLE,
            f"runtime={declared_runtime} tier={declared_tier}",
        )
    if declared_runtime != request.runtime.casefold():
        return (
            None,
            ReasonCode.CONTRACT_RUNTIME_MISMATCH,
            f"front_matter_runtime={declared_runtime} request_runtime={request.runtime}",
        )

    repo = front_matter["repo"].strip()
    normalized: dict[str, object] = {
        "tier": declared_tier,
        "runtime": declared_runtime,
        "repo": repo,
    }

    if "budget" in front_matter:
        budget_items = front_matter["budget"]
        if not isinstance(budget_items, list):
            return None, ReasonCode.CONTRACT_FRONT_MATTER, "budget must be a list"
        budget: dict[str, object] = {}
        for item in budget_items:
            if "=" not in item:
                return (
                    None,
                    ReasonCode.CONTRACT_FRONT_MATTER,
                    f"budget: malformed item: {item}",
                )
            name, _, value = item.partition("=")
            name = name.strip()
            value = value.strip()
            if name in FRONT_MATTER_BUDGET_INT_NAMES:
                # isdigit() alone accepts non-ASCII digit shapes (e.g. "²")
                # that int() cannot parse; isascii() narrows to plain "0"-"9".
                if not value.isascii() or not value.isdigit():
                    return (
                        None,
                        ReasonCode.CONTRACT_FRONT_MATTER,
                        f"budget.{name} must be a non-negative integer",
                    )
                budget[name] = int(value)
            elif name == "cost_usd":
                try:
                    cost = float(value)
                except ValueError:
                    cost = float("nan")
                if not math.isfinite(cost) or cost < 0:
                    return (
                        None,
                        ReasonCode.CONTRACT_FRONT_MATTER,
                        "budget.cost_usd must be a non-negative finite number",
                    )
                budget[name] = cost
            else:
                return (
                    None,
                    ReasonCode.CONTRACT_FRONT_MATTER,
                    f"budget: unknown item name: {name}",
                )
        normalized["budget"] = budget

    if "tokens_basis" in front_matter:
        tokens_basis = front_matter["tokens_basis"]
        if not isinstance(tokens_basis, str) or tokens_basis.strip() not in {
            "total",
            "uncached",
        }:
            return (
                None,
                ReasonCode.CONTRACT_FRONT_MATTER,
                "tokens_basis must be total or uncached",
            )
        normalized["tokens_basis"] = tokens_basis.strip()
    elif isinstance(normalized.get("budget"), dict) and "tokens" in normalized["budget"]:
        normalized["tokens_basis"] = "total"

    if "writes" in front_matter:
        writes = front_matter["writes"]
        if not isinstance(writes, list) or any(
            not isinstance(w, str) or not w.strip() for w in writes
        ):
            return (
                None,
                ReasonCode.CONTRACT_FRONT_MATTER,
                "writes must be a list of non-empty strings",
            )
        normalized["writes"] = list(writes)

    if "standing_rules" in front_matter:
        names = front_matter["standing_rules"]
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name.strip() for name in names
        ):
            return (
                None,
                ReasonCode.CONTRACT_FRONT_MATTER,
                "standing_rules must be a list of non-empty strings",
            )
        known = _known_standing_rule_names(standing_rules_path, standing_rules_local_path)
        for name in names:
            if STANDING_RULE_NAME_PATTERN.fullmatch(name) is None:
                return (
                    None,
                    ReasonCode.CONTRACT_FRONT_MATTER,
                    f"standing_rules: invalid name shape: {name}",
                )
            if name not in known:
                return (
                    None,
                    ReasonCode.STANDING_RULE_UNKNOWN,
                    f"standing_rules: unknown block: {name}",
                )
        normalized["standing_rules"] = list(names)

    return normalized, None, ""


def _load_tier_policy(path: Path) -> ModelTierPolicy:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(payload, dict) or isinstance(payload.get("version"), bool):
        raise ValueError("tier policy must be an object with a version")
    runtimes_payload = payload.get("runtimes", _MISSING)
    if payload.get("version") == 2:
        return _load_tier_policy_v2(payload, digest, runtimes_payload=runtimes_payload)
    if payload.get("version") != 1:
        raise ValueError("tier policy version must be 1 or 2")

    runtimes = _runtime_list_or_none(runtimes_payload)
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
        runtimes=runtimes,
    )


def _load_tier_policy_v2(
    payload: Mapping[str, object],
    digest: str,
    *,
    runtimes_payload: object = _MISSING,
) -> ModelTierPolicy:
    """Parse a version 2 policy: tiers plus optional per-window agent caps.

    A model absent from every tier is `unknown`, which is a tier like any other.
    A missing `fanout_caps` entry for any tier — including `unknown` — means
    uncapped, the same rule `cap_for` already applied to named tiers such as
    `efficient`. Requiring `unknown` while allowing other tiers to omit a key
    was the asymmetry that forced instance policies to invent a placeholder
    cap; absence is unambiguous for every tier. That is the difference from
    version 1, where an unrecognised name was denied outright and a new model
    stayed blocked until someone edited this file by hand.
    """

    runtimes = _runtime_list_or_none(runtimes_payload)
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
        runtimes=runtimes,
        tier_names=frozenset(tiers.keys()),
    )


def _model_list(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        raise ValueError("model lists must be arrays")
    if any(not isinstance(model, str) or not model.strip() for model in value):
        raise ValueError("model identifiers must be non-empty strings")
    if any(model != model.strip() for model in value):
        raise ValueError("model identifiers must not have surrounding whitespace")
    return frozenset(model.casefold() for model in value)


def _runtime_list_or_none(value: object) -> frozenset[str] | None:
    if value is _MISSING:
        return None
    if not isinstance(value, list):
        raise ValueError("runtimes must be an array")
    if any(not isinstance(runtime, str) or not runtime.strip() for runtime in value):
        raise ValueError("runtime identifiers must be non-empty strings")
    if any(runtime != runtime.strip() for runtime in value):
        raise ValueError("runtime identifiers must not have surrounding whitespace")
    if any(RUNTIME_PATTERN.fullmatch(runtime) is None for runtime in value):
        raise ValueError("runtime identifiers must match the runtime pattern")
    return frozenset(runtime.casefold() for runtime in value)


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


def _model_from_evidence(
    value: object,
    runtime: str | None = None,
) -> str | None:
    """Extract a model id from one raw JSONL evidence line."""

    if isinstance(value, Mapping):
        runtime_name = (runtime or "").casefold()
        if runtime_name == "codex":
            models = _main_session_models(value, runtime_name)
            if models:
                return models[0]
            if "type" in value:
                return None
        elif runtime_name == "claude":
            models = _main_session_models(value, runtime_name)
            if models:
                return models[0]
            if "type" in value:
                return None
        model = value.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
        for nested_key in ("message", "payload", "item", "response"):
            nested_model = _model_from_evidence(value.get(nested_key), runtime)
            if nested_model is not None:
                return nested_model
    elif isinstance(value, list):
        for item in value:
            nested_model = _model_from_evidence(item, runtime)
            if nested_model is not None:
                return nested_model
    return None


def _record_model_ids(
    record_text: str,
    runtime: str | None = None,
) -> tuple[str, ...]:
    """Collect main-session model ids from a runtime-shaped JSONL record."""

    return tuple(
        model
        for turn in _record_model_turns(record_text, runtime)
        for model in turn
    )


def _record_model_turns(
    record_text: str,
    runtime: str | None,
) -> tuple[tuple[str, ...], ...]:
    """Return model ids grouped by the record's explicit turn identity."""

    return tuple(models for _, models in _record_model_turns_with_keys(record_text, runtime))


def _record_model_turns_with_keys(
    record_text: str,
    runtime: str | None,
) -> tuple[tuple[str | int, tuple[str, ...]], ...]:
    """Return model ids grouped by turn key, preserving first-seen key order."""

    turns: dict[str | int, list[str]] = {}
    turn_order: list[str | int] = []
    for line_number, line in enumerate(record_text.splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping):
            continue
        models = _main_session_models(event, runtime)
        if not models:
            continue
        turn_key = _record_turn_key(event, line_number)
        if turn_key not in turns:
            turns[turn_key] = []
            turn_order.append(turn_key)
        for model in models:
            if model not in turns[turn_key]:
                turns[turn_key].append(model)
    return tuple((key, tuple(turns[key])) for key in turn_order)


def _main_session_models(
    event: Mapping[str, object],
    runtime: str | None,
) -> tuple[str, ...]:
    """Read only the model fields owned by a runtime's main session."""

    runtime_name = (runtime or "").casefold()
    if runtime_name == "codex":
        if event.get("type") not in {"session_meta", "turn_context"}:
            return ()
        payload = event.get("payload")
        source = payload if isinstance(payload, Mapping) else event
        model = source.get("model")
        return (model.strip(),) if isinstance(model, str) and model.strip() else ()

    if _is_sidechain_event(event):
        return ()
    if runtime_name == "claude":
        message = event.get("message")
        if not isinstance(message, Mapping):
            return ()
        if event.get("type") != "assistant" and message.get("role") != "assistant":
            return ()
        model = message.get("model")
        return (model.strip(),) if isinstance(model, str) and model.strip() else ()

    candidates: list[Mapping[str, object]] = [event]
    for key in ("message", "item", "payload", "response"):
        nested = event.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    saw_assistant = False
    for candidate in candidates:
        if candidate.get("role") == "assistant" or candidate.get("type") == "assistant":
            saw_assistant = True
        model = candidate.get("model")
        if saw_assistant and isinstance(model, str) and model.strip():
            return (model.strip(),)
    return ()


def _is_sidechain_event(event: Mapping[str, object]) -> bool:
    return any(
        event.get(key) is True
        for key in ("is_sidechain", "isSidechain", "sidechain")
    )


def _record_turn_key(event: Mapping[str, object], line_number: int) -> str | int:
    for key in ("turn_id", "turnId", "conversation_turn_id", "conversationTurnId"):
        value = event.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return f"turn:{value}"
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        for key in ("turn_id", "turnId", "conversation_turn_id", "conversationTurnId"):
            value = payload.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return f"turn:{value}"
    message = event.get("message")
    if isinstance(message, Mapping):
        value = message.get("id")
        if isinstance(value, str) and value.strip():
            return f"message:{value}"
    return line_number


def _model_matches_declared(
    model: str,
    declared: str,
    turns: Sequence[Sequence[str]],
) -> bool:
    if model.casefold() == declared.casefold():
        return True
    model_base = _undated_model_id(model)
    declared_base = _undated_model_id(declared)
    if model_base is None:
        model_base = model.strip().casefold()
    if declared_base is None:
        declared_base = declared.strip().casefold()
    if model_base != declared_base:
        return False
    model_is_dated = _undated_model_id(model) is not None
    declared_is_dated = _undated_model_id(declared) is not None
    if model_is_dated == declared_is_dated:
        return False
    return any(
        model.casefold() in {item.casefold() for item in turn}
        and declared.casefold() in {item.casefold() for item in turn}
        for turn in turns
    )


def _undated_model_id(model: str) -> str | None:
    normalized = model.strip().casefold()
    undated = re.sub(r"-\d{8}$", "", normalized)
    return undated if undated != normalized else None


def _relative_model_record_path(
    record_path: Path,
    roots: Sequence[Path],
) -> str:
    """Store evidence location relative to its accepted runtime root."""

    candidates: list[tuple[int, str]] = []
    for root in roots:
        try:
            relative = record_path.relative_to(root)
        except ValueError:
            continue
        candidates.append((len(root.parts), str(relative)))
    if candidates:
        return max(candidates, key=lambda candidate: candidate[0])[1]
    return record_path.name


def _dispatch_placement(
    entries: Sequence[Mapping[str, object]],
    dispatch_id: str,
    target: Mapping[str, object],
) -> Mapping[str, object]:
    """Join placement metadata recorded beside the dispatch row."""

    placement = dict(target)
    for entry in entries:
        if entry.get("job_id") != dispatch_id:
            continue
        for key in ("worktree_path", "agent_session_id"):
            if key not in placement and entry.get(key):
                placement[key] = entry[key]
    return placement


def _record_context(
    record_text: str,
    runtime: str | None = None,
) -> tuple[set[str], set[str], float | None]:
    """Collect identity only from session metadata or direct record fields.

    Tool events can mention another worktree while a session is operating on
    it. They are evidence of a command, not evidence of the session's own
    identity, so nested mappings are deliberately ignored here.
    """

    records: list[Mapping[str, object]] = []
    for line in record_text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            records.append(value)

    session_payloads = [
        value.get("payload")
        for value in records
        if value.get("type") == "session_meta"
        and isinstance(value.get("payload"), Mapping)
    ]
    if session_payloads:
        authoritative = session_payloads[:1]
        timestamp_sources = authoritative
    elif (runtime or "").casefold() == "claude":
        timestamp_sources = [
            value for value in records if not _is_sidechain_event(value)
        ]
        authoritative = [
            value
            for value in timestamp_sources
            if (
                value.get("type") == "assistant"
                or (
                    isinstance(value.get("message"), Mapping)
                    and value["message"].get("role") == "assistant"
                )
            )
        ]
    else:
        authoritative = records
        timestamp_sources = authoritative
    cwd_values: set[str] = set()
    session_values: set[str] = set()
    session_start: float | None = None

    for value in authoritative:
        if not isinstance(value, Mapping):
            continue
        for key in ("cwd", "worktree", "worktree_path"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                cwd_values.add(candidate.strip())
        for key in (
            "id",
            "session_id",
            "sessionId",
            "conversation_id",
            "conversationId",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                session_values.add(candidate.strip())
    for value in timestamp_sources:
        if not isinstance(value, Mapping):
            continue
        for key in (
            "timestamp",
            "created_at",
            "createdAt",
            "start_time",
            "startTime",
            "started_at",
            "startedAt",
            "ts",
        ):
            candidate = _session_timestamp(value.get(key))
            if candidate is not None:
                session_start = (
                    candidate
                    if session_start is None
                    else min(session_start, candidate)
                )
    return cwd_values, session_values, session_start


def _paths_match(left: str, right: str) -> bool:
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except (OSError, ValueError):
        return False


def _record_belongs_to_dispatch(
    target: Mapping[str, object],
    placement: Mapping[str, object],
    record_path: Path,
    record_text: str,
    session_roots: Mapping[str, tuple[Path, ...]],
) -> bool:
    """Require the record's runtime context to identify this dispatch."""

    worktree = _string_or_none(placement.get("worktree_path"))
    session_id = _string_or_none(placement.get("agent_session_id"))
    if not worktree and not session_id:
        return False

    runtime = _string_or_none(target.get("runtime"))
    cwd_values, session_values, _ = _record_context(record_text, runtime)
    if session_id:
        if session_id not in session_values:
            if _string_or_none(target.get("runtime")) == "agy":
                for brain_root in session_roots.get("agy", ()):
                    try:
                        relative = record_path.relative_to(brain_root)
                    except ValueError:
                        continue
                    if not relative.parts or relative.parts[0] != session_id:
                        continue
                    if session_values:
                        return False
                    if worktree and cwd_values and not any(
                        _paths_match(cwd, worktree) for cwd in cwd_values
                    ):
                        return False
                    return True
            return False
        if worktree and cwd_values:
            return any(_paths_match(cwd, worktree) for cwd in cwd_values)
        return True
    if worktree and any(_paths_match(cwd, worktree) for cwd in cwd_values):
        return True

    return False


def _replace_ledger_entries(
    ledger_path: Path,
    entries: Sequence[Mapping[str, object]],
) -> None:
    """Atomically rewrite the ledger after a verified model measurement."""

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = ledger_path.with_name(
        f".{ledger_path.name}.{os.getpid()}.measurement.tmp"
    )
    try:
        with temporary_path.open("w", encoding="utf-8") as ledger:
            for entry in entries:
                ledger.write(json.dumps(entry, sort_keys=True, separators=(",", ":")))
                ledger.write("\n")
            ledger.flush()
            os.fsync(ledger.fileno())
        os.replace(temporary_path, ledger_path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


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


@contextmanager
def _ledger_lock(ledger_path: Path) -> Iterator[None]:
    """Serialize ledger updates without creating the ticket directory."""

    lock_path = ledger_lock_path(ledger_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    inherited_fd = os.environ.get(LEDGER_LOCK_FD_ENV, "")
    try:
        fd = int(inherited_fd)
    except ValueError:
        fd = -1
    if fcntl is not None and fd >= 0:
        try:
            fd_stat = os.fstat(fd)
            lock_stat = lock_path.stat()
            same_file = (fd_stat.st_dev, fd_stat.st_ino) == (
                lock_stat.st_dev,
                lock_stat.st_ino,
            )
        except OSError:
            same_file = False
        if same_file:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                pass
            else:
                yield
                return
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


def _session_timestamp(value: object) -> float | None:
    numeric = _number_or_none(value)
    if numeric is not None and math.isfinite(numeric):
        return numeric
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
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
