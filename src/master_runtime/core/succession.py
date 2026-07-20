"""Orca-native master succession helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

from master_runtime.core.bootstrap import RoleState


TRIGGER_IMMEDIATE = "IMMEDIATE"
TRIGGER_ADVISORY = "ADVISORY"
TRIGGER_NONE = "NONE"

VERIFY_PASS = "PASS"
VERIFY_PARTIAL = "PARTIAL"
VERIFY_FAILED = "FAILED"


class SuccessionError(RuntimeError):
    """Raised when succession would violate a hard safety guard."""


@dataclass(frozen=True)
class TriggerDecision:
    status: str
    reason: str
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FrozenState:
    current_role: str
    lock_enabled: bool
    frozen: str
    unlock: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VerificationReport:
    status: str
    checks: Tuple[str, ...]
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionInfo:
    handle: str
    worktree_path: str
    branch: str
    title: str
    connected: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetirementReport:
    status: str
    target_handle: Optional[str]
    reason: str
    candidates: Tuple[SessionInfo, ...]
    closed: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


OrcaRunner = Callable[[Sequence[str]], Tuple[int, str, str]]


def detect_trigger(text: str, context: Optional[Mapping[str, object]] = None) -> TriggerDecision:
    """Classify a user or runtime signal without auto-starting advisory succession."""

    normalized = (text or "").strip().lower()
    immediate_markers = (
        "승계해줘",
        "다음 마스터로 넘기자",
        "승계 진행해",
        "succession now",
        "handoff to successor",
    )
    if any(marker in normalized for marker in immediate_markers):
        return TriggerDecision(TRIGGER_IMMEDIATE, "explicit succession instruction")

    context = context or {}
    ratio = _float_or_none(context.get("context_ratio"))
    if ratio is not None and ratio >= 0.60:
        return TriggerDecision(
            TRIGGER_ADVISORY,
            "context ratio threshold reached",
            "컨텍스트 임계치가 높습니다. 자동 승계 금지; 승계를 제안만 합니다.",
        )
    milestone = str(context.get("milestone", "")).strip()
    if milestone:
        return TriggerDecision(
            TRIGGER_ADVISORY,
            "natural milestone reached",
            "자연 마일스톤에 도달했습니다. 자동 승계 금지; 승계를 제안만 합니다.",
        )
    return TriggerDecision(TRIGGER_NONE, "no succession trigger")


def freeze_roles(role_state: object) -> FrozenState:
    """Freeze every role except the current inherited role."""

    role = _get_value(role_state, "role") or _get_value(role_state, "current_role")
    if not role:
        raise SuccessionError("role_state missing current role")
    return FrozenState(
        current_role=str(role),
        lock_enabled=True,
        frozen="all other roles",
        unlock="explicit user instruction only",
    )


def build_handoff(spec: Mapping[str, object]) -> str:
    """Build one thin handoff from structured succession state."""

    role_state = spec.get("role_state")
    if role_state is None:
        role_state = RoleState(
            role=str(spec.get("current_role", "Reference Implementation")),
            lock_enabled=True,
            frozen="all other roles",
            unlock="explicit user instruction only",
        )
    frozen = freeze_roles(role_state)
    lines = [
        "## Role State",
        "",
        "```",
        "Current Role: " + frozen.current_role,
        "Role Lock: " + ("ENABLED" if frozen.lock_enabled else "DISABLED"),
        "Frozen: " + frozen.frozen,
        "Unlock: " + frozen.unlock,
        "```",
        "",
        "## Current Objective",
        "",
        _text_field(spec, "current_objective"),
        "",
        "## Active/Open Tracks",
        "",
        _list_field(spec, "active_tracks") + _list_field(spec, "open_tracks"),
        "",
        "## Accepted Artifacts",
        "",
        _list_field(spec, "accepted_artifacts"),
        "",
        "## Deferred Work",
        "",
        _list_field(spec, "deferred_work"),
        "",
        "## Open Questions",
        "",
        _list_field(spec, "open_questions"),
        "",
        "## Recommended Next Role",
        "",
        _text_field(spec, "recommended_next_role", frozen.current_role),
        "",
        "## Observed Baseline",
        "",
        _text_field(spec, "observed_baseline"),
        "",
    ]
    return "\n".join(lines)


def verify_successor(recover_report: object) -> VerificationReport:
    """Verify successor recovery from the U8 recovery report shape."""

    payload = recover_report.to_dict() if hasattr(recover_report, "to_dict") else recover_report
    if not isinstance(payload, Mapping):
        raise SuccessionError("recover_report must be a mapping or expose to_dict()")
    steps = payload.get("steps") or []
    step_statuses = {
        str(step.get("step")): str(step.get("status"))
        for step in steps
        if isinstance(step, Mapping)
    }
    if any(status == "MISS" for status in step_statuses.values()):
        return VerificationReport(VERIFY_FAILED, ("fail-closed recovery miss",), "MISS in recovery steps")

    checks = []
    if step_statuses.get("6") == "OK":
        checks.append("open tracks recited")
    if step_statuses.get("2-3") in ("OK", None):
        checks.append("baseline matched")
    if step_statuses.get("5") == "OK":
        checks.append("monitors rearmed")

    if len(checks) == 3:
        status = VERIFY_PASS
    elif checks:
        status = VERIFY_PARTIAL
    else:
        status = VERIFY_FAILED
    return VerificationReport(status, tuple(checks), "checks={0}".format(",".join(checks)))


def find_sessions(
    orca_runner: Optional[OrcaRunner] = None,
    selector: Optional[str] = None,
) -> Tuple[SessionInfo, ...]:
    """Return Orca-managed terminal sessions from ``orca terminal list --json``."""

    code, stdout, stderr = (orca_runner or _default_orca_runner)(
        ("orca", "terminal", "list", "--json")
    )
    if code != 0:
        raise SuccessionError(stderr.strip() or stdout.strip() or "orca terminal list failed")
    sessions = tuple(_parse_session(item) for item in _terminal_items(stdout))
    if selector is None:
        return sessions
    return tuple(session for session in sessions if _session_matches(session, selector))


def detect_duplicate_instances(
    session_marker: str,
    self_handle: str,
    orca_runner: Optional[OrcaRunner] = None,
) -> Tuple[SessionInfo, ...]:
    """Find same-marker Orca sessions while excluding the current handle."""

    _require_handle(self_handle)
    marker = _require_substr(session_marker, "session_marker")
    return tuple(
        session
        for session in find_sessions(orca_runner)
        if session.handle != self_handle and _session_matches(session, marker)
    )


def retire_predecessor(
    predecessor_selector: str,
    self_handle: str,
    expected_substr: str,
    orca_runner: Optional[OrcaRunner] = None,
    execute: bool = False,
) -> RetirementReport:
    """Resolve and optionally close exactly one predecessor terminal."""

    _require_handle(self_handle)
    expected = _require_substr(expected_substr, "expected_substr")
    candidates = find_sessions(orca_runner, predecessor_selector)
    expected_candidates = tuple(
        session for session in candidates if _session_matches(session, expected)
    )
    if any(session.handle == self_handle for session in expected_candidates):
        raise SuccessionError("self_handle matched retirement candidate; refusing to close self")
    if not expected_candidates:
        return RetirementReport("REFUSED", None, "expected substring did not match target", candidates)
    if len(expected_candidates) > 1:
        return RetirementReport("REFUSED", None, "ambiguous predecessor candidates", expected_candidates)

    target = expected_candidates[0]
    if not execute:
        return RetirementReport("DRY_RUN", target.handle, "dry-run only", (target,))

    runner = orca_runner or _default_orca_runner
    code, stdout, stderr = runner(
        ("orca", "terminal", "close", "--terminal", target.handle, "--json")
    )
    if code != 0:
        return RetirementReport(
            "REFUSED",
            target.handle,
            stderr.strip() or stdout.strip() or "orca terminal close failed",
            (target,),
        )
    remaining = find_sessions(runner)
    if any(session.handle == target.handle for session in remaining):
        return RetirementReport("REFUSED", target.handle, "target still present after close", (target,))
    return RetirementReport("CLOSED", target.handle, "target disappeared after close", (target,), True)


def _terminal_items(stdout: str) -> Tuple[Mapping[str, object], ...]:
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise SuccessionError("invalid orca JSON") from exc
    if not isinstance(payload, Mapping):
        raise SuccessionError("orca JSON root must be an object")
    if payload.get("ok") is False:
        error = payload.get("error")
        if isinstance(error, Mapping):
            raise SuccessionError(str(error.get("message") or error.get("code") or "orca error"))
        raise SuccessionError("orca error")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise SuccessionError("orca JSON missing result")
    terminals = result.get("terminals")
    if not isinstance(terminals, list):
        raise SuccessionError("orca JSON missing result.terminals")
    return tuple(item for item in terminals if isinstance(item, Mapping))


def _parse_session(item: Mapping[str, object]) -> SessionInfo:
    handle = str(item.get("handle") or "")
    if not handle:
        raise SuccessionError("orca terminal missing handle")
    return SessionInfo(
        handle=handle,
        worktree_path=str(item.get("worktreePath") or ""),
        branch=str(item.get("branch") or ""),
        title=str(item.get("title") or ""),
        connected=bool(item.get("connected")),
    )


def _session_matches(session: SessionInfo, marker: str) -> bool:
    return marker in session.worktree_path or marker in session.title or marker in session.branch


def _default_orca_runner(command: Sequence[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _get_value(source: object, key: str) -> Optional[object]:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _float_or_none(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_field(spec: Mapping[str, object], key: str, default: str = "") -> str:
    value = spec.get(key, default)
    if value is None:
        return ""
    return str(value)


def _list_field(spec: Mapping[str, object], key: str) -> str:
    value = spec.get(key)
    if value is None:
        return "- none\n"
    if isinstance(value, str):
        return "- " + value + "\n"
    try:
        return "".join("- " + str(item) + "\n" for item in value)
    except TypeError:
        return "- " + str(value) + "\n"


def _require_handle(value: str) -> str:
    if not value:
        raise SuccessionError("self_handle is required")
    return value


def _require_substr(value: str, label: str) -> str:
    if not value:
        raise SuccessionError(label + " is required")
    return value


__all__ = (
    "FrozenState",
    "RetirementReport",
    "SessionInfo",
    "SuccessionError",
    "TriggerDecision",
    "VerificationReport",
    "build_handoff",
    "detect_duplicate_instances",
    "detect_trigger",
    "find_sessions",
    "freeze_roles",
    "retire_predecessor",
    "verify_successor",
)
