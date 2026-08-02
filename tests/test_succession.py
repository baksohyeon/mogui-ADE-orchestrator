from __future__ import annotations

import json
import shlex
import subprocess
import unittest
from pathlib import Path
from typing import Sequence, Tuple

from master_runtime.core.bootstrap import RoleState
from master_runtime.core.recovery import RecoveryReport, RecoveryStep
from master_runtime.core.succession import (
    SuccessionError,
    build_handoff,
    detect_duplicate_instances,
    detect_trigger,
    find_sessions,
    freeze_roles,
    retire_predecessor,
    spawn_successor,
    verify_successor,
)


ORCA_LIST_JSON = json.dumps(
    {
        "id": "local",
        "ok": True,
        "result": {
            "terminals": [
                {
                    "handle": "term-self",
                    "ptyId": "pty-self",
                    "worktreeId": "repo:u9",
                    "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
                    "branch": "feat/u9-succession",
                    "connected": True,
                    "title": "u9-succession master",
                },
                {
                    "handle": "term-u8",
                    "ptyId": "pty-u8",
                    "worktreeId": "repo:u8",
                    "worktreePath": "/repo/mogui-ADE-orchestrator/u8-recovery",
                    "branch": "feat/u8-recovery",
                    "connected": True,
                    "title": "u8-recovery predecessor",
                },
                {
                    "handle": "term-u8-shadow",
                    "ptyId": "pty-u8-shadow",
                    "worktreeId": "repo:u8",
                    "worktreePath": "/repo/mogui-ADE-orchestrator/u8-recovery",
                    "branch": "feat/u8-recovery",
                    "connected": False,
                    "title": "u8-recovery duplicate",
                },
            ]
        },
    }
)


def test_detect_trigger_has_immediate_advisory_and_none_branches() -> None:
    assert detect_trigger("succession now", {}).status == "IMMEDIATE"
    assert detect_trigger("handoff to successor", {}).status == "IMMEDIATE"
    assert detect_trigger("다음 마스터로 넘기자", {}).status == "IMMEDIATE"
    assert detect_trigger("승계해줘", {}).status == "IMMEDIATE"
    assert detect_trigger("승계 진행해", {}).status == "IMMEDIATE"
    advisory = detect_trigger("", {"context_ratio": 0.72})
    assert advisory.status == "ADVISORY"
    assert "Auto-succession is not permitted" in advisory.message
    assert detect_trigger("keep going", {}).status == "NONE"


def test_freeze_roles_keeps_current_role_only() -> None:
    frozen = freeze_roles(
        RoleState(
            role="Reference Implementation",
            lock_enabled=False,
            frozen="none",
            unlock="manual",
        )
    )

    assert frozen.current_role == "Reference Implementation"
    assert frozen.lock_enabled is True
    assert frozen.frozen == "all other roles"


def test_build_handoff_contains_required_sections() -> None:
    handoff = build_handoff(
        {
            "role_state": RoleState(
                role="Reference Implementation",
                lock_enabled=True,
                frozen="all other roles",
                unlock="explicit user instruction only",
            ),
            "current_objective": "Land U9 Succession Manager.",
            "active_tracks": ["U9 implementation"],
            "open_tracks": ["U10 follow-up"],
            "accepted_artifacts": ["U8 recovery"],
            "deferred_work": ["headless fallback"],
            "open_questions": ["none"],
            "recommended_next_role": "Reference Implementation",
            "observed_baseline": "repo clean",
        }
    )

    for section in (
        "## Role State",
        "## Current Objective",
        "## Active/Open Tracks",
        "## Accepted Artifacts",
        "## Deferred Work",
        "## Open Questions",
        "## Recommended Next Role",
        "## Observed Baseline",
    ):
        assert section in handoff


def test_verify_successor_pass_partial_and_failed() -> None:
    pass_report = RecoveryReport(
        steps=(
            RecoveryStep("0", "OK", "Role State restored"),
            RecoveryStep("2-3", "OK", "git state observed"),
            RecoveryStep("5", "OK", "no monitor patterns configured"),
            RecoveryStep("6", "OK", "successor verification checklist generated"),
        ),
        active_tracks=({"track_id": "U9", "title": "Succession"},),
    )
    assert verify_successor(pass_report).status == "PASS"

    partial_report = RecoveryReport(
        steps=(
            RecoveryStep("0", "OK", "Role State restored"),
            RecoveryStep("5", "WARN", "running monitor matches=1"),
            RecoveryStep("6", "OK", "successor verification checklist generated"),
        ),
        active_tracks=({"track_id": "U9", "title": "Succession"},),
    )
    assert verify_successor(partial_report).status == "PARTIAL"

    failed_report = RecoveryReport(
        steps=(RecoveryStep("0", "MISS", "Charter missing"),),
    )
    assert verify_successor(failed_report).status == "FAILED"


def test_find_sessions_parses_real_orca_json_shape() -> None:
    sessions = find_sessions(_runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}))

    assert sessions[0].handle == "term-self"
    assert sessions[0].pty_id == "pty-self"
    assert sessions[0].worktree_path.endswith("u9-succession")
    assert sessions[0].connected is True


def test_detect_duplicate_instances_excludes_self_handle() -> None:
    duplicates = detect_duplicate_instances(
        "u8-recovery",
        "term-u8",
        _runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}),
    )

    assert [session.handle for session in duplicates] == ["term-u8-shadow"]


def test_retire_predecessor_rejects_self_handle() -> None:
    with unittest.TestCase().assertRaisesRegex(SuccessionError, "self_handle"):
        retire_predecessor(
            predecessor_selector="u9-succession",
            self_handle="term-self",
            expected_substr="u9-succession",
            orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}),
        )


def test_retire_predecessor_refusal_explains_title_drift_and_empty_worktree() -> None:
    fixture = _orca_json_from_terminals(
        {
            "handle": "term-self",
            "ptyId": "pty-self",
            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
            "branch": "feat/u9-succession",
            "connected": True,
            "title": "u9 successor",
        },
        {
            "handle": "term-u8",
            "ptyId": "pty-u8",
            "worktreePath": "",
            "branch": "",
            "connected": True,
            "title": "conversation summary rewrote this pane title",
        },
    )

    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="u8-recovery",
        orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, fixture, "")}),
    )

    assert report.status == "REFUSED"
    assert report.target_handle is None
    assert report.candidates == ()
    assert "candidates=none" in report.reason
    assert "term-u8: selector=u8-recovery -> no-match" in report.match_attempts


def test_retire_predecessor_rejects_ambiguous_candidates() -> None:
    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="u8-recovery",
        orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}),
    )

    assert report.status == "REFUSED"
    assert "ambiguous" in report.reason
    assert "term-u8" in report.reason
    assert "term-u8-shadow" in report.reason


def test_retire_predecessor_dry_run_does_not_close() -> None:
    calls = []
    runner = _recording_runner(
        {
            ("orca", "terminal", "list", "--json"): (
                0,
                _orca_json_with_handles(("term-self", "u9-succession"), ("term-u8", "u8-recovery")),
                "",
            ),
        },
        calls,
    )

    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="u8-recovery",
        orca_runner=runner,
    )

    assert report.status == "DRY_RUN"
    assert report.target_handle == "term-u8"
    assert ("orca", "terminal", "close", "--terminal", "term-u8", "--json") not in calls


def test_retire_predecessor_execute_closes_and_rechecks() -> None:
    calls = []
    runner = _recording_runner(
        {
            ("orca", "terminal", "list", "--json"): [
                (0, _orca_json_with_handles(("term-self", "u9-succession"), ("term-u8", "u8-recovery")), ""),
                (0, _orca_json_with_handles(("term-self", "u9-succession")), ""),
            ],
            ("orca", "terminal", "close", "--terminal", "term-u8", "--json"): (0, '{"ok":true}', ""),
        },
        calls,
    )

    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="u8-recovery",
        orca_runner=runner,
        execute=True,
    )

    assert report.status == "CLOSED"
    assert report.target_handle == "term-u8"
    assert ("orca", "terminal", "close", "--terminal", "term-u8", "--json") in calls


def test_retire_predecessor_exact_handle_ignores_title_and_worktree_collisions() -> None:
    """exact handle target must not match sessions whose title/worktree_id equal the handle string."""
    fixture = _orca_json_from_terminals(
        {
            "handle": "term-self",
            "ptyId": "pty-self",
            "worktreeId": "repo:self",
            "worktreePath": "/repo/mogui-ADE-orchestrator/self",
            "branch": "feat/self",
            "connected": True,
            "title": "self pane",
        },
        {
            "handle": "term-decoy-title",
            "ptyId": "pty-decoy-title",
            "worktreeId": "repo:decoy-title",
            "worktreePath": "/repo/mogui-ADE-orchestrator/decoy-title",
            "branch": "feat/decoy-title",
            "connected": True,
            "title": "term-u8",
        },
        {
            "handle": "term-decoy-wt",
            "ptyId": "pty-decoy-wt",
            "worktreeId": "term-u8",
            "worktreePath": "/repo/mogui-ADE-orchestrator/decoy-wt",
            "branch": "feat/decoy-wt",
            "connected": True,
            "title": "decoy worktree",
        },
        {
            "handle": "term-u8",
            "ptyId": "pty-u8",
            "worktreeId": "repo:u8",
            "worktreePath": "/repo/mogui-ADE-orchestrator/u8-recovery",
            "branch": "feat/u8-recovery",
            "connected": True,
            "title": "real predecessor",
        },
    )

    report = retire_predecessor(
        predecessor_selector="",
        self_handle="term-self",
        target_handle="term-u8",
        orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, fixture, "")}),
    )

    assert report.status == "DRY_RUN"
    assert report.target_handle == "term-u8"
    assert len(report.candidates) == 1
    assert report.candidates[0].handle == "term-u8"
    assert "term-decoy-title: handle=term-u8 -> no-match" in report.match_attempts
    assert "term-decoy-wt: handle=term-u8 -> no-match" in report.match_attempts
    assert "term-u8: handle=term-u8 -> handle" in report.match_attempts


def test_retire_predecessor_explicit_handle_closes_title_drift_folder_context() -> None:
    calls = []
    first_list = _orca_json_from_terminals(
        {
            "handle": "term-self",
            "ptyId": "pty-self",
            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
            "branch": "feat/u9-succession",
            "connected": True,
            "title": "u9 successor",
        },
        {
            "handle": "term-u8",
            "ptyId": "pty-u8",
            "processId": 4242,
            "worktreePath": "",
            "branch": "",
            "connected": True,
            "title": "conversation summary rewrote this pane title",
        },
    )
    second_list = _orca_json_from_terminals(
        {
            "handle": "term-self",
            "ptyId": "pty-self",
            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
            "branch": "feat/u9-succession",
            "connected": True,
            "title": "u9 successor",
        },
    )
    runner = _recording_runner(
        {
            ("orca", "terminal", "list", "--json"): [
                (0, first_list, ""),
                (0, second_list, ""),
            ],
            ("orca", "terminal", "close", "--terminal", "term-u8", "--json"): (0, '{"ok":true}', ""),
        },
        calls,
    )

    report = retire_predecessor(
        predecessor_selector="",
        self_handle="term-self",
        target_handle="term-u8",
        orca_runner=runner,
        execute=True,
        process_probe=lambda pid: False,
    )

    assert report.status == "CLOSED"
    assert report.target_handle == "term-u8"
    assert report.closed is True
    assert "process gone: pid=4242" in report.reason
    assert "term-u8: handle=term-u8 -> handle" in report.match_attempts
    assert ("orca", "terminal", "close", "--terminal", "term-u8", "--json") in calls


def test_retire_predecessor_refuses_when_pid_survives_close() -> None:
    runner = _runner(
        {
            ("orca", "terminal", "list", "--json"): [
                (
                    0,
                    _orca_json_from_terminals(
                        {
                            "handle": "term-self",
                            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
                            "connected": True,
                            "title": "u9 successor",
                        },
                        {
                            "handle": "term-u8",
                            "processId": 4242,
                            "worktreePath": "",
                            "connected": True,
                            "title": "conversation summary",
                        },
                    ),
                    "",
                ),
                (
                    0,
                    _orca_json_from_terminals(
                        {
                            "handle": "term-self",
                            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
                            "connected": True,
                            "title": "u9 successor",
                        },
                    ),
                    "",
                ),
            ],
            ("orca", "terminal", "close", "--terminal", "term-u8", "--json"): (0, '{"ok":true}', ""),
        }
    )

    report = retire_predecessor(
        predecessor_selector="",
        self_handle="term-self",
        target_handle="term-u8",
        orca_runner=runner,
        execute=True,
        process_probe=lambda pid: True,
    )

    assert report.status == "REFUSED"
    assert report.closed is False
    assert "target process still present after close: pid=4242" in report.reason


def test_spawn_successor_creates_and_verifies_worktree() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _recording_runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
        },
        calls,
    )

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.handle == "term-new"
    assert report.worktree_id == "folder:unit-a"
    assert report.verified is True
    assert create_command in calls


def test_spawn_successor_mismatch_closes_terminal_and_fails_closed() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _recording_runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (0, _orca_create_json("term-new", "folder:wrong"), ""),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "worktree mismatch") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 22
    assert close_command in calls


def test_spawn_successor_close_failure_is_reported() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (0, _orca_create_json("term-new", "folder:wrong"), ""),
            close_command: (1, "", "close denied"),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "close failed") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 23


def test_spawn_successor_parse_error_after_handle_closes_terminal() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _recording_runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (0, '{"ok":true,"result":{"terminal":{"handle":"term-new",', ""),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "invalid spawn JSON") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 21
    assert close_command in calls


def test_spawn_successor_parse_error_close_failure_is_reported() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (0, '{"ok":true,"result":{"terminal":{"handle":"term-new",', ""),
            close_command: (1, "", "close denied"),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "invalid spawn JSON.*close failed") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 23


def test_spawn_successor_missing_worktree_after_handle_closes_terminal() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _recording_runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (
                0,
                json.dumps({"ok": True, "result": {"terminal": {"handle": "term-new"}}}),
                "",
            ),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "missing worktreeId") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 21
    assert close_command in calls


def test_spawn_successor_rejects_invalid_create_json() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: (0, _orca_json_from_terminals(), ""),
            create_command: (0, "not json", ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "invalid spawn JSON") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 21


def test_spawn_successor_dry_run_only_builds_plan() -> None:
    calls = []

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=lambda command: calls.append(tuple(command)) or (1, "", "unexpected call"),
        dry_run=True,
    )

    assert report.status == "DRY_RUN"
    assert report.handle is None
    assert report.verified is False
    assert report.command == _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    assert calls == []


def test_spawn_successor_reissued_handle_resolves_via_list() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(_list_terminal("term-user", "folder:other", "shell")), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-user", "folder:other", "shell"),
                        _list_terminal("term-reissued", "folder:unit-a", "⠂ successor"),
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.handle == "term-reissued"
    assert report.handle_reissued is True
    assert report.verified is True
    assert report.verification["result"] == "MATCH_REISSUED"
    assert report.verification["reported_handle"] == "term-old"


def test_spawn_successor_live_handle_is_not_reissued() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
        }
    )

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.handle == "term-new"
    assert report.handle_reissued is False
    assert report.verification["result"] == "MATCH"


def test_spawn_successor_stale_handle_zero_candidates_fails_closed() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _recording_runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(), ""),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24
    assert not any(command[:3] == ("orca", "terminal", "close") for command in calls)


def test_spawn_successor_stale_handle_ambiguous_candidates_fails_closed_without_close() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _recording_runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-a", "folder:unit-a", "successor"),
                        _list_terminal("term-b", "folder:unit-a", "successor"),
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24
    assert not any(command[:3] == ("orca", "terminal", "close") for command in calls)


def test_spawn_successor_stale_handle_title_narrows_candidates() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-shell", "folder:unit-a", "plain shell"),
                        _list_terminal("term-master", "folder:unit-a", "✳ successor"),
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.handle == "term-master"
    assert report.handle_reissued is True


def test_spawn_successor_snapshot_handle_is_not_trusted_as_live() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    preexisting = _list_terminal("term-recycled", "folder:unit-a", "user shell")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(preexisting), ""),
                (0, _orca_json_from_terminals(preexisting), ""),
            ],
            create_command: (0, _orca_create_json("term-recycled", "folder:unit-a"), ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24


def test_spawn_successor_single_candidate_without_title_match_fails_closed() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-other", "folder:unit-a", "plain shell")), ""),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24


def test_spawn_successor_new_terminal_in_other_worktree_is_not_adopted() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-elsewhere", "folder:other", "successor")), ""),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24


def test_spawn_successor_title_containment_collision_fails_closed() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-a", "folder:unit-a", "✳ successor"),
                        _list_terminal("term-b", "folder:unit-a", "⠂ successor 2"),
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24


def test_spawn_successor_precheck_list_failure_blocks_create() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _recording_runner(
        {
            _LIST_COMMAND: (1, "", "orca offline"),
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "spawn precheck list failed") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert create_command not in calls


def test_spawn_successor_liveness_list_failure_closes_terminal() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _recording_runner(
        {
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "spawn liveness list failed.*closed terminal") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert close_command in calls


def test_cli_check_duplicates_outputs_json() -> None:
    result = subprocess.run(
        [
            str(Path(__file__).resolve().parent.parent / "scripts" / "master-succeed"),
            "check-duplicates",
            "--self-handle",
            "term-u8",
            "--marker",
            "u8-recovery",
            "--json",
            "--fixture-json",
            ORCA_LIST_JSON,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [item["handle"] for item in payload["duplicates"]] == ["term-u8-shadow"]


def test_cli_spawn_dry_run_outputs_json() -> None:
    result = subprocess.run(
        [
            str(Path(__file__).resolve().parent.parent / "scripts" / "master-succeed"),
            "spawn",
            "--workspace-selector",
            "folder:unit-a",
            "--kickoff-text",
            "start here",
            "--root",
            "/repo/example",
            "--title",
            "successor",
            "--dry-run",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["verification"]["fail_closed_action"] == "terminal close on mismatch"


def test_cli_retire_accepts_explicit_target_handle() -> None:
    fixture = _orca_json_from_terminals(
        {
            "handle": "term-self",
            "ptyId": "pty-self",
            "worktreePath": "/repo/mogui-ADE-orchestrator/u9-succession",
            "branch": "feat/u9-succession",
            "connected": True,
            "title": "u9 successor",
        },
        {
            "handle": "term-u8",
            "ptyId": "pty-u8",
            "worktreePath": "",
            "branch": "",
            "connected": True,
            "title": "conversation summary rewrote this pane title",
        },
    )
    result = subprocess.run(
        [
            str(Path(__file__).resolve().parent.parent / "scripts" / "master-succeed"),
            "retire",
            "--self-handle",
            "term-self",
            "--target-handle",
            "term-u8",
            "--json",
            "--fixture-json",
            fixture,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["target_handle"] == "term-u8"


def _runner(responses):
    def run(command: Sequence[str]) -> Tuple[int, str, str]:
        response = responses[tuple(command)]
        if isinstance(response, list):
            return response.pop(0)
        return response

    return run


def _recording_runner(responses, calls):
    base = _runner(responses)

    def run(command: Sequence[str]) -> Tuple[int, str, str]:
        calls.append(tuple(command))
        return base(command)

    return run


def _orca_json_with_handles(*items) -> str:
    return _orca_json_from_terminals(
        *(
            {
                "handle": handle,
                "ptyId": handle + "-pty",
                "worktreeId": "repo:" + marker,
                "worktreePath": "/repo/mogui-ADE-orchestrator/" + marker,
                "branch": "feat/" + marker,
                "connected": True,
                "title": marker + " master",
            }
            for handle, marker in items
        )
    )


_LIST_COMMAND = ("orca", "terminal", "list", "--json")


def _orca_json_from_terminals(*terminals) -> str:
    return json.dumps({"ok": True, "result": {"terminals": list(terminals)}})


def _list_terminal(handle: str, worktree_id: str, title: str) -> dict:
    return {
        "handle": handle,
        "worktreeId": worktree_id,
        "worktreePath": "/repo/example",
        "connected": True,
        "title": title,
    }


def _orca_create_json(handle: str, worktree_id: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "result": {
                "terminal": {
                    "handle": handle,
                    "worktreeId": worktree_id,
                    "title": "successor",
                }
            },
        }
    )


def _spawn_create_command(selector: str, kickoff: str, root: str, title: str, model: str = "claude-fable-5"):
    return (
        "orca",
        "terminal",
        "create",
        "--worktree",
        selector,
        "--title",
        title,
        "--command",
        "cd {0} && exec claude --model {1} --dangerously-skip-permissions {2}".format(
            shlex.quote(root),
            shlex.quote(model),
            shlex.quote(kickoff),
        ),
        "--json",
    )


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
