"""Orca-native master succession helpers."""

from __future__ import annotations

import json
import os
import re
import shlex
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

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


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
    pty_id: str = ""
    worktree_id: str = ""
    session_id: str = ""
    process_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetirementReport:
    status: str
    target_handle: Optional[str]
    reason: str
    candidates: Tuple[SessionInfo, ...]
    closed: bool = False
    match_attempts: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["match_attempts"] = list(self.match_attempts)
        return payload


@dataclass(frozen=True)
class SpawnReport:
    status: str
    handle: Optional[str]
    worktree_id: Optional[str]
    requested_worktree: str
    verified: bool
    command: Tuple[str, ...]
    startup_command: str
    verification: Mapping[str, object]
    handle_reissued: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["command"] = list(self.command)
        return payload


OrcaRunner = Callable[[Sequence[str]], Tuple[int, str, str]]
ProcessProbe = Callable[[int], bool]

SPAWN_CREATE_ERROR = 20
SPAWN_PARSE_ERROR = 21
SPAWN_WORKTREE_MISMATCH = 22
SPAWN_CLOSE_ERROR = 23
SPAWN_HANDLE_STALE = 24
SPAWN_LIST_ERROR = 25
SPAWN_PLACEMENT_MISMATCH = 26

_SPAWN_HANDLE_HINT = re.compile(r'"(?:handle|terminal|terminalHandle)"\s*:\s*"([^"]+)"')
_SPAWN_SELECTOR_HINT = (
    "Accepted selector forms are full id:<repoId>::<path>, id:folder:<uuid> "
    "for folder workspaces; path: is matched by resolved directory."
)


def _title_matches(pane_title: str, session_title: str) -> bool:
    requested_title = pane_title.strip()
    if not requested_title:
        return False
    normalized_title = session_title
    while normalized_title and not normalized_title[0].isalnum():
        normalized_title = normalized_title[1:]
    return normalized_title.strip() == requested_title


def detect_trigger(text: str, context: Optional[Mapping[str, object]] = None) -> TriggerDecision:
    """Classify a user or runtime signal without auto-starting advisory succession."""

    normalized = (text or "").strip().lower()
    immediate_markers = (
        "succession now",
        "handoff to successor",
        "승계해줘",
        "다음 마스터로 넘기자",
        "승계 진행해",
    )
    if any(marker in normalized for marker in immediate_markers):
        return TriggerDecision(TRIGGER_IMMEDIATE, "explicit succession instruction")

    context = context or {}
    ratio = _float_or_none(context.get("context_ratio"))
    if ratio is not None and ratio >= 0.60:
        return TriggerDecision(
            TRIGGER_ADVISORY,
            "context ratio threshold reached",
            "Context ratio is high. Auto-succession is not permitted; propose succession only.",
        )
    milestone = str(context.get("milestone", "")).strip()
    if milestone:
        return TriggerDecision(
            TRIGGER_ADVISORY,
            "natural milestone reached",
            "A natural milestone was reached. Auto-succession is not permitted; propose succession only.",
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
    list_worktree: Optional[str] = None,
) -> Tuple[SessionInfo, ...]:
    """Return Orca-managed terminal sessions from ``orca terminal list --json``.

    When ``list_worktree`` is set, list only that worktree. Some Orca builds
    reject a bare global list with ``folder_workspace_not_found``; spawn always
    has a workspace selector and must use the scoped form.
    """

    if list_worktree:
        command: Tuple[str, ...] = (
            "orca",
            "terminal",
            "list",
            "--worktree",
            _terminal_list_worktree_selector(list_worktree),
            "--json",
        )
    else:
        command = ("orca", "terminal", "list", "--json")
    code, stdout, stderr = (orca_runner or _default_orca_runner)(command)
    if code != 0:
        raise SuccessionError(stderr.strip() or stdout.strip() or "orca terminal list failed")
    # A single malformed entry must not take every list consumer down; entries
    # without a handle are unaddressable anyway.
    sessions = tuple(
        _parse_session(item) for item in _terminal_items(stdout) if item.get("handle")
    )
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
    expected_substr: Optional[str] = None,
    orca_runner: Optional[OrcaRunner] = None,
    execute: bool = False,
    target_handle: Optional[str] = None,
    target_pty_id: Optional[str] = None,
    target_session_id: Optional[str] = None,
    process_probe: Optional[ProcessProbe] = None,
) -> RetirementReport:
    """Resolve and optionally close exactly one predecessor terminal."""

    _require_handle(self_handle)
    criteria = _retirement_criteria(
        predecessor_selector,
        expected_substr,
        target_handle,
        target_pty_id,
        target_session_id,
    )
    sessions = find_sessions(orca_runner)
    candidates, attempts = _retirement_candidates(sessions, criteria)
    if any(session.handle == self_handle for session in candidates):
        raise SuccessionError("self_handle matched retirement candidate; refusing to close self")
    if not candidates:
        return RetirementReport(
            "REFUSED",
            None,
            _retirement_refusal_reason("no predecessor candidates", candidates, attempts),
            candidates,
            False,
            attempts,
        )
    if len(candidates) > 1:
        return RetirementReport(
            "REFUSED",
            None,
            _retirement_refusal_reason("ambiguous predecessor candidates", candidates, attempts),
            candidates,
            False,
            attempts,
        )

    target = candidates[0]
    if not execute:
        return RetirementReport("DRY_RUN", target.handle, "dry-run only", (target,), False, attempts)

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
            False,
            attempts,
        )
    remaining = find_sessions(runner)
    if any(session.handle == target.handle for session in remaining):
        return RetirementReport(
            "REFUSED",
            target.handle,
            "target still present after close",
            (target,),
            False,
            attempts,
        )
    if target.process_id is not None:
        probe = process_probe or _default_process_probe
        if probe(target.process_id):
            return RetirementReport(
                "REFUSED",
                target.handle,
                "target process still present after close: pid={0}".format(target.process_id),
                (target,),
                False,
                attempts,
            )
        return RetirementReport(
            "CLOSED",
            target.handle,
            "target disappeared after close; process gone: pid={0}".format(target.process_id),
            (target,),
            True,
            attempts,
        )
    return RetirementReport(
        "CLOSED",
        target.handle,
        "target disappeared after close; no pid reported by terminal list",
        (target,),
        True,
        attempts,
    )


def spawn_successor(
    workspace_selector: str,
    kickoff_text: str,
    root: str,
    title: str,
    model: str = "claude-fable-5",
    agent: str = "claude",
    expected_placement: Optional[str] = None,
    orca_runner: Optional[OrcaRunner] = None,
    dry_run: bool = False,
) -> SpawnReport:
    """Create a successor terminal and fail closed on worktree or handle-liveness mismatch."""

    selector = _require_substr(workspace_selector, "workspace_selector")
    kickoff = _require_substr(kickoff_text, "kickoff_text")
    cwd = _require_substr(root, "root")
    pane_title = _require_substr(title, "title")
    model_name = _require_substr(model, "model")
    agent_name = _require_substr(agent, "agent")
    expected = (
        _require_substr(expected_placement, "expected_placement")
        if expected_placement is not None
        else None
    )
    startup_command = _spawn_startup_command(cwd, model_name, kickoff, agent_name)
    create_command = (
        "orca",
        "terminal",
        "create",
        "--worktree",
        selector,
        "--title",
        pane_title,
        "--command",
        startup_command,
        "--json",
    )
    verification = {
        "requested_worktree": selector,
        "expected_response_field": "worktreeId",
        "fail_closed_action": "terminal close on mismatch",
        "liveness_check": "reported handle must be live+new+connected in requested worktree, else adopt unique titled candidate or fail closed without closing",
        "agent": agent_name,
    }
    if expected is not None:
        verification["expected_placement"] = expected
    if dry_run:
        return SpawnReport(
            "DRY_RUN",
            None,
            None,
            selector,
            False,
            create_command,
            startup_command,
            verification,
        )

    runner = orca_runner or _default_orca_runner
    try:
        snapshot_handles = frozenset(
            session.handle for session in find_sessions(runner, list_worktree=selector)
        )
    except SuccessionError as exc:
        raise SuccessionError(
            "spawn precheck list failed: " + str(exc),
            SPAWN_LIST_ERROR,
        ) from exc
    global_snapshot_handles = None
    try:
        # A scoped snapshot cannot prove that a mismatch handle is new in a
        # different worktree. Best-effort global capture supplies that proof;
        # if the host rejects the global list, mismatch cleanup stays closed.
        global_snapshot_handles = frozenset(
            session.handle for session in find_sessions(runner)
        )
    except SuccessionError:
        pass

    code, stdout, stderr = runner(create_command)
    if code != 0:
        raise SuccessionError(
            "spawn terminal create failed: " + _command_error(stdout, stderr),
            SPAWN_CREATE_ERROR,
        )

    handle_hint = _spawn_handle_hint(stdout)
    try:
        terminal = _created_terminal(stdout)
    except SuccessionError as exc:
        _raise_spawn_error_after_cleanup(
            runner,
            handle_hint,
            exc,
            snapshot_handles,
            pane_title,
            list_worktree=selector,
            global_snapshot_handles=global_snapshot_handles,
        )
        raise

    handle = _spawn_field(terminal, ("handle", "terminal", "terminalHandle"), "handle")
    try:
        worktree_id = _spawn_field(terminal, ("worktreeId",), "worktreeId")
    except SuccessionError as exc:
        _raise_spawn_error_after_cleanup(
            runner,
            handle,
            exc,
            snapshot_handles,
            pane_title,
            list_worktree=selector,
            global_snapshot_handles=global_snapshot_handles,
        )
        raise
    if not _worktrees_match(worktree_id, selector):
        _raise_spawn_mismatch(
            runner,
            handle,
            "spawn worktree mismatch: requested {0}, got {1}".format(selector, worktree_id),
            "spawn worktree mismatch; closed terminal {0}: requested {1}, got {2}".format(
                handle,
                selector,
                worktree_id,
            ),
            SPAWN_WORKTREE_MISMATCH,
            snapshot_handles,
            pane_title,
            list_worktree=selector,
            global_snapshot_handles=global_snapshot_handles,
        )
    if expected is not None and not _worktrees_match(worktree_id, expected):
        _raise_spawn_mismatch(
            runner,
            handle,
            "spawn placement mismatch: expected {0}, got {1}".format(expected, worktree_id),
            "spawn placement mismatch; closed terminal {0}: expected {1}, got {2}".format(
                handle,
                expected,
                worktree_id,
            ),
            SPAWN_PLACEMENT_MISMATCH,
            snapshot_handles,
            pane_title,
            list_worktree=selector,
            global_snapshot_handles=global_snapshot_handles,
        )

    try:
        live_sessions = find_sessions(runner, list_worktree=selector)
    except SuccessionError as exc:
        _raise_spawn_error_after_cleanup(
            runner,
            handle,
            SuccessionError("spawn liveness list failed: " + str(exc), SPAWN_LIST_ERROR),
            snapshot_handles,
            pane_title,
            list_worktree=selector,
            global_snapshot_handles=global_snapshot_handles,
        )
        raise

    # A handle seen before the create cannot belong to the terminal the create
    # made, even if it is live now (handle recycling would point at a user's
    # pre-existing terminal).
    matched_live_session = next(
        (
            session
            for session in live_sessions
            if session.handle == handle
            and session.handle not in snapshot_handles
            and _worktrees_match(session.worktree_id, selector)
            and session.connected
        ),
        None,
    )
    if matched_live_session is not None:
        return SpawnReport(
            "CREATED",
            handle,
            worktree_id,
            selector,
            True,
            create_command,
            startup_command,
            {
                "requested_worktree": selector,
                "actual_worktree": worktree_id,
                "liveness_check": "reported handle is live+new+connected in requested worktree",
                "title_matched": _title_matches(pane_title, matched_live_session.title),
                "result": "MATCH",
                **({"expected_placement": expected} if expected is not None else {}),
            },
        )

    candidates, narrowed = _reissued_terminal_candidates(
        live_sessions,
        snapshot_handles,
        selector,
        pane_title,
    )
    reissued = narrowed[0] if len(narrowed) == 1 else None
    if reissued is None:
        raise SuccessionError(
            "spawn handle stale: reported handle {0} is not trusted as live; {1} new connected "
            "terminal(s) exist in worktree {2} ({5}), {3} of them carry pane title {4} ({6}); "
            "the created terminal "
            "may still be running unmanaged, reconcile via orca terminal list".format(
                handle,
                len(candidates),
                selector,
                len(narrowed),
                repr(pane_title),
                [session.handle for session in candidates],
                [session.handle for session in narrowed],
            ),
            SPAWN_HANDLE_STALE,
        )

    return SpawnReport(
        "CREATED",
        reissued.handle,
        reissued.worktree_id,
        selector,
        True,
        create_command,
        startup_command,
        {
            "requested_worktree": selector,
            "actual_worktree": reissued.worktree_id,
            "reported_handle": handle,
            "liveness_check": "reissued handle is live+new+connected in requested worktree",
            "title_matched": True,
            "result": "MATCH_REISSUED",
            **({"expected_placement": expected} if expected is not None else {}),
        },
        handle_reissued=True,
    )


def _new_worktree_sessions(
    live_sessions: Sequence[SessionInfo],
    snapshot_handles: frozenset,
    selector: str,
) -> Tuple[SessionInfo, ...]:
    return tuple(
        session
        for session in live_sessions
        if _worktrees_match(session.worktree_id, selector)
        and session.handle not in snapshot_handles
        and session.connected
    )


def _reissued_terminal_candidates(
    live_sessions: Sequence[SessionInfo],
    snapshot_handles: frozenset,
    selector: str,
    pane_title: str,
) -> Tuple[Tuple[SessionInfo, ...], Tuple[SessionInfo, ...]]:
    candidates = _new_worktree_sessions(live_sessions, snapshot_handles, selector)
    narrowed = tuple(session for session in candidates if _title_matches(pane_title, session.title))
    return candidates, narrowed


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


def _created_terminal(stdout: str) -> Mapping[str, object]:
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise SuccessionError("invalid spawn JSON", SPAWN_PARSE_ERROR) from exc
    if not isinstance(payload, Mapping):
        raise SuccessionError("spawn JSON root must be an object", SPAWN_PARSE_ERROR)
    if payload.get("ok") is False:
        error = payload.get("error")
        if isinstance(error, Mapping):
            raise SuccessionError(
                "spawn orca error: " + str(error.get("message") or error.get("code") or "orca error"),
                SPAWN_CREATE_ERROR,
            )
        raise SuccessionError("spawn orca error", SPAWN_CREATE_ERROR)

    result = payload.get("result")
    if isinstance(result, Mapping):
        terminal = result.get("terminal")
        if isinstance(terminal, Mapping):
            return terminal
        terminals = result.get("terminals")
        if isinstance(terminals, list) and len(terminals) == 1 and isinstance(terminals[0], Mapping):
            return terminals[0]
        if "handle" in result or "terminalHandle" in result or "terminal" in result:
            return result
    if "handle" in payload or "terminalHandle" in payload or "terminal" in payload:
        return payload
    raise SuccessionError("spawn JSON missing created terminal", SPAWN_PARSE_ERROR)


def _spawn_handle_hint(stdout: str) -> Optional[str]:
    match = _SPAWN_HANDLE_HINT.search(stdout)
    if not match:
        return None
    return match.group(1)


def _raise_spawn_error_after_cleanup(
    runner: OrcaRunner,
    handle: Optional[str],
    error: SuccessionError,
    snapshot_handles: frozenset,
    pane_title: str,
    list_worktree: Optional[str] = None,
    global_snapshot_handles: Optional[frozenset] = None,
) -> None:
    if not handle:
        raise error
    if handle in snapshot_handles:
        raise SuccessionError(
            "{0}; reported handle {1} is pre-existing; terminal not closed".format(
                str(error),
                handle,
            ),
            error.exit_code,
        ) from error
    if _close_spawned_terminal(
        runner,
        handle,
        str(error),
        snapshot_handles,
        pane_title,
        list_worktree=list_worktree,
        global_snapshot_handles=global_snapshot_handles,
    ):
        raise SuccessionError(
            "{0}; closed terminal {1}".format(str(error), handle),
            error.exit_code,
        ) from error
    raise SuccessionError(
        "{0}; terminal not closed; ownership unconfirmed, reconcile via orca terminal list".format(
            str(error),
        ),
        error.exit_code,
    ) from error


def _raise_spawn_mismatch(
    runner: OrcaRunner,
    handle: str,
    mismatch_message: str,
    closed_message: str,
    exit_code: int,
    snapshot_handles: frozenset,
    pane_title: str,
    list_worktree: Optional[str] = None,
    global_snapshot_handles: Optional[frozenset] = None,
) -> None:
    error = SuccessionError(mismatch_message, exit_code)
    if handle in snapshot_handles:
        raise SuccessionError(
            _with_selector_hint(
                "{0}; reported handle {1} is pre-existing; terminal not closed".format(
                    str(error),
                    handle,
                )
            ),
            error.exit_code,
        ) from error
    try:
        closed = _close_spawned_terminal(
            runner,
            handle,
            str(error),
            snapshot_handles,
            pane_title,
            list_worktree=list_worktree,
            global_snapshot_handles=global_snapshot_handles,
        )
    except SuccessionError as exc:
        if exc.exit_code == SPAWN_CLOSE_ERROR:
            raise SuccessionError(
                _with_selector_hint(str(exc)),
                exc.exit_code,
            ) from exc
        raise
    if closed:
        raise SuccessionError(
            _with_selector_hint(closed_message),
            error.exit_code,
        ) from error
    raise SuccessionError(
        _with_selector_hint(
            "{0}; terminal not closed; ownership unconfirmed, reconcile via orca terminal list".format(
                str(error),
            )
        ),
        error.exit_code,
    ) from error


def _close_spawned_terminal(
    runner: OrcaRunner,
    handle: str,
    failure_message: str,
    snapshot_handles: frozenset,
    pane_title: str,
    list_worktree: Optional[str] = None,
    global_snapshot_handles: Optional[frozenset] = None,
) -> bool:
    confirmed_from_global = False
    try:
        confirmed_sessions = find_sessions(runner, list_worktree=list_worktree)
    except SuccessionError:
        if not list_worktree:
            return False
        if global_snapshot_handles is None:
            return False
        try:
            # A scoped list can be unavailable on older hosts; the global list
            # is safe only when the pre-create global snapshot proves newness.
            confirmed_sessions = find_sessions(runner)
            confirmed_from_global = True
        except SuccessionError:
            return False
    confirmed = next(
        (session for session in confirmed_sessions if session.handle == handle),
        None,
    )
    if confirmed is None and list_worktree:
        if global_snapshot_handles is None:
            return False
        try:
            # A mismatch terminal is intentionally outside the requested
            # worktree, so scoped confirmation cannot see it. Retry globally
            # before giving up, but only with a global pre-create snapshot.
            confirmed_sessions = find_sessions(runner)
            confirmed_from_global = True
        except SuccessionError:
            return False
        confirmed = next(
            (session for session in confirmed_sessions if session.handle == handle),
            None,
        )
    if confirmed_from_global and handle in global_snapshot_handles:
        return False
    if (
        confirmed is None
        or handle in snapshot_handles
        or not confirmed.connected
        or not _title_matches(pane_title, confirmed.title)
    ):
        return False
    close_command = ("orca", "terminal", "close", "--terminal", handle, "--json")
    close_code, close_stdout, close_stderr = runner(close_command)
    if close_code != 0:
        raise SuccessionError(
            "{0} and close failed: close error: {1}".format(
                failure_message,
                _command_error(close_stdout, close_stderr),
            ),
            SPAWN_CLOSE_ERROR,
        )
    return True


def _spawn_field(item: Mapping[str, object], keys: Sequence[str], label: str) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    raise SuccessionError("spawn JSON missing " + label, SPAWN_PARSE_ERROR)


def _normalize_worktree_selector(value: str) -> str:
    """Normalize Orca worktree selectors for equality checks.

    Create/list payloads often return ``repoId::path`` while callers may pass
    ``id:repoId::path``. Treat those as the same worktree identity.
    """

    text = value.strip()
    if text.startswith("id:"):
        return text[3:]
    return text


def _terminal_list_worktree_selector(value: str) -> str:
    if value.startswith("folder:"):
        return "id:" + value
    return value


def _worktrees_match(actual: str, requested: str) -> bool:
    if not actual or not requested:
        return False
    if actual == requested:
        return True
    actual_text = _normalize_worktree_selector(actual)
    requested_text = _normalize_worktree_selector(requested)
    if actual_text == requested_text:
        return True
    return _path_worktree_matches(actual_text, requested_text)


def _path_worktree_matches(actual: str, requested: str) -> bool:
    if not requested.startswith("path:") or "::" not in actual:
        return False
    _repo_id, actual_path = actual.split("::", 1)
    requested_path = requested[5:]
    if not actual_path or not requested_path:
        return False
    try:
        return os.path.realpath(actual_path) == os.path.realpath(requested_path)
    except (OSError, RuntimeError, ValueError):
        return False


def _with_selector_hint(message: str) -> str:
    return message.rstrip(". ") + ". " + _SPAWN_SELECTOR_HINT


def _spawn_startup_command(
    root: str,
    model: str,
    kickoff_text: str,
    agent: str = "claude",
) -> str:
    """Build the agent TUI command for a founding/successor terminal."""

    agent_key = agent.strip().lower()
    quoted_root = shlex.quote(root)
    quoted_model = shlex.quote(model)
    quoted_kickoff = shlex.quote(kickoff_text)
    if agent_key in ("claude", "claude-code"):
        return "cd {0} && exec claude --model {1} --dangerously-skip-permissions {2}".format(
            quoted_root,
            quoted_model,
            quoted_kickoff,
        )
    if agent_key in ("grok", "grok-build"):
        return "cd {0} && exec grok --model {1} --always-approve --cwd {0} {2}".format(
            quoted_root,
            quoted_model,
            quoted_kickoff,
        )
    if agent_key in ("codex",):
        return "cd {0} && exec codex --model {1} {2}".format(
            quoted_root,
            quoted_model,
            quoted_kickoff,
        )
    # Unknown agent: treat the name as the executable and pass model + prompt.
    return "cd {0} && exec {1} --model {2} {3}".format(
        quoted_root,
        shlex.quote(agent.strip()),
        quoted_model,
        quoted_kickoff,
    )


def _command_error(stdout: str, stderr: str) -> str:
    return (stderr.strip() or stdout.strip() or "no error output")


def _retirement_criteria(
    predecessor_selector: str,
    expected_substr: Optional[str],
    target_handle: Optional[str],
    target_pty_id: Optional[str],
    target_session_id: Optional[str],
) -> Tuple[Tuple[str, str, bool], ...]:
    criteria = []
    if target_handle:
        criteria.append(("handle", target_handle, True))
    if target_pty_id:
        criteria.append(("pty_id", target_pty_id, True))
    if target_session_id:
        criteria.append(("session_id", target_session_id, True))
    if criteria:
        return tuple(criteria)

    selector = predecessor_selector or (expected_substr or "")
    _require_substr(selector, "predecessor_selector")
    return (("selector", selector, False),)


def _retirement_candidates(
    sessions: Sequence[SessionInfo],
    criteria: Sequence[Tuple[str, str, bool]],
) -> Tuple[Tuple[SessionInfo, ...], Tuple[str, ...]]:
    candidates = []
    attempts = []
    for session in sessions:
        matched_fields = []
        for label, expected, exact in criteria:
            fields = _retirement_match_fields(session)
            if exact:
                # Exact targets bind to the labeled field only
                # (handle==X means session.handle, never title/worktree_id collisions).
                field_map = dict(fields)
                value = field_map.get(label, "")
                matches = [label] if value and value == expected else []
            else:
                # Selector mode keeps substring search across all fields.
                matches = [
                    field
                    for field, value in fields
                    if value and expected in value
                ]
            attempts.append(
                "{0}: {1}={2} -> {3}".format(
                    session.handle,
                    label,
                    expected,
                    ",".join(matches) if matches else "no-match",
                )
            )
            matched_fields.extend(matches)
        if matched_fields:
            candidates.append(session)
    return tuple(candidates), tuple(attempts)


def _retirement_refusal_reason(
    reason: str,
    candidates: Sequence[SessionInfo],
    attempts: Sequence[str],
) -> str:
    candidate_handles = ",".join(session.handle for session in candidates) or "none"
    attempt_text = " | ".join(attempts) or "none"
    return "{0}; candidates={1}; match_attempts={2}".format(
        reason,
        candidate_handles,
        attempt_text,
    )


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
        pty_id=str(item.get("ptyId") or item.get("ptyID") or ""),
        worktree_id=str(item.get("worktreeId") or ""),
        session_id=str(item.get("sessionId") or item.get("sessionID") or ""),
        process_id=_optional_int(item.get("processId") or item.get("pid")),
    )


def _session_matches(session: SessionInfo, marker: str) -> bool:
    return any(value and marker in value for _field, value in _retirement_match_fields(session))


def _retirement_match_fields(session: SessionInfo) -> Tuple[Tuple[str, str], ...]:
    return (
        ("handle", session.handle),
        ("pty_id", session.pty_id),
        ("session_id", session.session_id),
        ("worktree_id", session.worktree_id),
        ("worktree_path", session.worktree_path),
        ("branch", session.branch),
        ("title", session.title),
    )


def _default_orca_runner(command: Sequence[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _default_process_probe(pid: int) -> bool:
    completed = subprocess.run(
        ("ps", "-p", str(pid), "-o", "pid="),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


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
    "SpawnReport",
    "SuccessionError",
    "TriggerDecision",
    "VerificationReport",
    "build_handoff",
    "detect_duplicate_instances",
    "detect_trigger",
    "find_sessions",
    "freeze_roles",
    "retire_predecessor",
    "spawn_successor",
    "verify_successor",
)
