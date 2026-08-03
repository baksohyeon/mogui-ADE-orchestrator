from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Sequence, Tuple

from master_runtime.core.bootstrap import RoleState
from master_runtime.core.recovery import RecoveryReport, RecoveryStep
from master_runtime.core.succession import (
    SPAWN_PLACEMENT_MISMATCH,
    SessionInfo,
    SuccessionError,
    _reissued_terminal_candidates,
    _spawn_startup_command,
    _worktrees_match,
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
_LIST_COMMAND = ("orca", "terminal", "list", "--json")
_GLOBAL_SNAPSHOT_FIXTURE = object()


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
    sessions = find_sessions(_runner({_LIST_COMMAND: (0, ORCA_LIST_JSON, "")}))

    assert sessions[0].handle == "term-self"
    assert sessions[0].pty_id == "pty-self"
    assert sessions[0].worktree_path.endswith("u9-succession")
    assert sessions[0].connected is True


def test_detect_duplicate_instances_excludes_self_handle() -> None:
    duplicates = detect_duplicate_instances(
        "u8-recovery",
        "term-u8",
        _runner({_LIST_COMMAND: (0, ORCA_LIST_JSON, "")}),
    )

    assert [session.handle for session in duplicates] == ["term-u8-shadow"]


def test_retire_predecessor_rejects_self_handle() -> None:
    with unittest.TestCase().assertRaisesRegex(SuccessionError, "self_handle"):
        retire_predecessor(
            predecessor_selector="u9-succession",
            self_handle="term-self",
            expected_substr="u9-succession",
            orca_runner=_runner({_LIST_COMMAND: (0, ORCA_LIST_JSON, "")}),
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
        orca_runner=_runner({_LIST_COMMAND: (0, fixture, "")}),
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
        orca_runner=_runner({_LIST_COMMAND: (0, ORCA_LIST_JSON, "")}),
    )

    assert report.status == "REFUSED"
    assert "ambiguous" in report.reason
    assert "term-u8" in report.reason
    assert "term-u8-shadow" in report.reason


def test_retire_predecessor_dry_run_does_not_close() -> None:
    calls = []
    runner = _recording_runner(
        {
            _LIST_COMMAND: (
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
            _LIST_COMMAND: [
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
        orca_runner=_runner({_LIST_COMMAND: (0, fixture, "")}),
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
            _LIST_COMMAND: [
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
            _LIST_COMMAND: [
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
    assert "expected_placement" not in report.verification


def test_spawn_successor_bare_folder_selector_uses_id_for_list_only() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    bare_list_command = _scoped_list_command("folder:unit-a")
    id_list_command = _scoped_list_command("id:folder:unit-a")
    runner = _recording_runner(
        {
            bare_list_command: (1, "", "selector_not_found"),
            id_list_command: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
    assert id_list_command in calls
    assert bare_list_command not in calls
    assert create_command in calls


def test_spawn_successor_id_folder_selector_keeps_working() -> None:
    calls = []
    create_command = _spawn_create_command("id:folder:unit-a", "start here", "/repo/example", "successor")
    id_list_command = _scoped_list_command("id:folder:unit-a")
    runner = _recording_runner(
        {
            id_list_command: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
        },
        calls,
    )

    report = spawn_successor(
        workspace_selector="id:folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.handle == "term-new"
    assert report.worktree_id == "folder:unit-a"
    assert id_list_command in calls
    assert create_command in calls


def test_worktrees_match_accepts_path_selector_resolved_repo_path() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        checkout = root / "checkout"
        checkout.mkdir()
        alias = root / "checkout_alias"
        alias.symlink_to(checkout, target_is_directory=True)

        assert _worktrees_match(
            "repoid::{0}/".format(checkout),
            "path:{0}/".format(alias),
        )
        assert _worktrees_match(
            "id:repoid::{0}".format(checkout),
            "path:{0}".format(alias),
        )


def test_worktrees_match_path_resolution_failure_fails_closed() -> None:
    assert not _worktrees_match("repoid::/repo/example", "path:\0")
    assert not _worktrees_match("repoid::", "path:")


def test_spawn_successor_expected_placement_passes() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
        }
    )

    report = spawn_successor(
        workspace_selector="folder:unit-a",
        expected_placement="id:folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.worktree_id == "folder:unit-a"
    assert report.verification["expected_placement"] == "id:folder:unit-a"


def test_spawn_successor_expected_placement_mismatch_closes_terminal() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "successor")), ""),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "placement mismatch") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            expected_placement="folder:other",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == SPAWN_PLACEMENT_MISMATCH
    assert "expected folder:other, got folder:unit-a" in str(raised.exception)
    assert "Accepted selector forms" in str(raised.exception)
    assert close_command in calls


def test_spawn_successor_mismatch_closes_terminal_and_fails_closed() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    scoped_list_command = (
        "orca",
        "terminal",
        "list",
        "--worktree",
        "folder:unit-a",
        "--json",
    )
    runner = _recording_runner(
        {
            scoped_list_command: (0, _orca_json_from_terminals(), ""),
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:wrong", "✳ successor")), ""),
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
    assert "Accepted selector forms" in str(raised.exception)
    assert close_command in calls


def test_spawn_successor_mismatch_does_not_close_preexisting_cross_worktree_handle() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-recycled", "--json")
    scoped_list_command = (
        "orca",
        "terminal",
        "list",
        "--worktree",
        "folder:unit-a",
        "--json",
    )
    preexisting = _list_terminal("term-recycled", "folder:wrong", "✳ successor")
    runner = _recording_runner(
        {
            scoped_list_command: (0, _orca_json_from_terminals(), ""),
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(preexisting), ""),
            _LIST_COMMAND: (0, _orca_json_from_terminals(preexisting), ""),
            create_command: (0, _orca_create_json("term-recycled", "folder:wrong"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(
        SuccessionError,
        "terminal not closed; ownership unconfirmed",
    ):
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert close_command not in calls


def test_spawn_startup_command_covers_agent_variants_and_shell_quoting() -> None:
    root = "/repo/with space"
    kickoff = "start; $(touch should-not-run)"

    assert _spawn_startup_command(root, "grok-4.5", kickoff, "grok") == (
        "cd '/repo/with space' && exec grok --model grok-4.5 --always-approve "
        "--cwd '/repo/with space' 'start; $(touch should-not-run)'"
    )
    assert _spawn_startup_command(root, "gpt-5.6-sol", kickoff, "codex") == (
        "cd '/repo/with space' && exec codex --model gpt-5.6-sol "
        "'start; $(touch should-not-run)'"
    )
    assert _spawn_startup_command(root, "custom-model", kickoff, "custom agent; touch") == (
        "cd '/repo/with space' && exec 'custom agent; touch' --model custom-model "
        "'start; $(touch should-not-run)'"
    )


def test_spawn_successor_close_failure_is_reported() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    scoped_list_command = (
        "orca",
        "terminal",
        "list",
        "--worktree",
        "folder:unit-a",
        "--json",
    )
    runner = _runner(
        {
            scoped_list_command: (0, _orca_json_from_terminals(), ""),
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: (0, _orca_json_from_terminals(_list_terminal("term-new", "folder:wrong", "✳ successor")), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "✳ successor")),
                    "",
                ),
            ],
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "✳ successor")),
                    "",
                ),
            ],
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "✳ successor")),
                    "",
                ),
            ],
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
    assert "expected_placement" not in report.verification
    assert calls == []


def test_spawn_successor_reissued_handle_resolves_via_list() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (
                0,
                _orca_json_from_terminals(_list_terminal("term-user", "folder:other", "shell")),
                "",
            ),
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
    assert report.verification["liveness_check"] == "reissued handle is live+new+connected in requested worktree"
    assert report.verification["title_matched"] is True


def test_spawn_successor_reissued_expected_placement_passes() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (
                0,
                _orca_json_from_terminals(_list_terminal("term-user", "folder:other", "shell")),
                "",
            ),
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
        expected_placement="id:folder:unit-a",
        kickoff_text="start here",
        root="/repo/example",
        title="successor",
        orca_runner=runner,
    )

    assert report.status == "CREATED"
    assert report.handle == "term-reissued"
    assert report.handle_reissued is True
    assert report.verification["result"] == "MATCH_REISSUED"
    assert report.verification["expected_placement"] == "id:folder:unit-a"


def test_spawn_successor_reissued_expected_placement_mismatch_closes_terminal() -> None:
    calls = []
    with tempfile.TemporaryDirectory() as tmpdir:
        checkout = Path(tmpdir) / "checkout"
        checkout.mkdir()
        selector = "path:{0}".format(checkout)
        expected = "repoa::{0}".format(checkout)
        create_command = _spawn_create_command(selector, "start here", "/repo/example", "successor")
        scoped_list_command = _scoped_list_command(selector)
        close_command = ("orca", "terminal", "close", "--terminal", "term-reissued", "--json")
        runner = _recording_runner(
            {
                scoped_list_command: [
                    (0, _orca_json_from_terminals(), ""),
                    (
                        0,
                        _orca_json_from_terminals(
                            _list_terminal("term-reissued", "repob::{0}".format(checkout), "⠂ successor")
                        ),
                        "",
                    ),
                    (
                        0,
                        _orca_json_from_terminals(
                            _list_terminal("term-reissued", "repob::{0}".format(checkout), "⠂ successor")
                        ),
                        "",
                    ),
                ],
                _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
                create_command: (0, _orca_create_json("term-old", "repoa::{0}".format(checkout)), ""),
                close_command: (0, '{"ok":true}', ""),
            },
            calls,
        )

        with unittest.TestCase().assertRaisesRegex(SuccessionError, "placement mismatch") as raised:
            spawn_successor(
                workspace_selector=selector,
                expected_placement=expected,
                kickoff_text="start here",
                root="/repo/example",
                title="successor",
                orca_runner=runner,
            )

    assert raised.exception.exit_code == SPAWN_PLACEMENT_MISMATCH
    assert "expected {0}, got repob::{1}".format(expected, checkout) in str(raised.exception)
    assert close_command in calls


def test_spawn_successor_live_handle_is_not_reissued() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
    assert report.verification["title_matched"] is True


def test_spawn_successor_stale_handle_zero_candidates_fails_closed() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(preexisting), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
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
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "master-gen2")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-a", "folder:unit-a", "master-gen2-copy"),
                        _list_terminal("term-b", "folder:unit-a", "grandmaster-gen2"),
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
            title="master-gen2",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24
    assert "2 new connected terminal(s) exist in worktree folder:unit-a (['term-a', 'term-b'])" in str(
        raised.exception
    )
    assert "0 of them carry pane title 'master-gen2' ([])" in str(raised.exception)


def test_spawn_successor_lone_substring_title_is_not_adopted() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "master-gen2")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(_list_terminal("term-copy", "folder:unit-a", "master-gen2-copy")), ""),
            ],
            create_command: (0, _orca_create_json("term-old", "folder:unit-a"), ""),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "stale") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="master-gen2",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 24


def test_reissued_title_matching_empty_pane_title_has_no_narrowed_candidates() -> None:
    candidate = SessionInfo(
        handle="term-new",
        worktree_path="/repo/example",
        branch="",
        title="✳ successor",
        connected=True,
        worktree_id="folder:unit-a",
    )

    candidates, narrowed = _reissued_terminal_candidates(
        (candidate,), frozenset(), "folder:unit-a", ""
    )

    assert candidates == (candidate,)
    assert narrowed == ()


def test_spawn_successor_disconnected_reported_handle_is_not_live() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    dead = dict(_list_terminal("term-new", "folder:unit-a", "successor"), connected=False)
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(dead), ""),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
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


def test_spawn_successor_disconnected_candidate_is_not_adopted() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    dead = dict(_list_terminal("term-dead", "folder:unit-a", "✳ successor"), connected=False)
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (0, _orca_json_from_terminals(dead), ""),
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


def test_spawn_successor_live_reported_handle_beats_ambient_candidates() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-new", "folder:unit-a", "successor"),
                        _list_terminal("term-bystander", "folder:unit-a", "successor"),
                    ),
                    "",
                ),
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


def test_spawn_successor_liveness_list_failure_close_failure_is_reported() -> None:
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-new", "--json")
    runner = _runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
                (
                    0,
                    _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "✳ successor")),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-new", "folder:unit-a"), ""),
            close_command: (1, "", "close denied"),
        }
    )

    with unittest.TestCase().assertRaisesRegex(SuccessionError, "spawn liveness list failed.*close failed") as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 23


def test_find_sessions_skips_entries_without_handle() -> None:
    runner = _runner(
        {
            _LIST_COMMAND: (
                0,
                _orca_json_from_terminals(
                    {"worktreePath": "/repo/broken", "connected": True, "title": "no handle"},
                    _list_terminal("term-ok", "folder:unit-a", "fine"),
                ),
                "",
            ),
        }
    )

    sessions = find_sessions(runner)

    assert [session.handle for session in sessions] == ["term-ok"]


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
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
                (
                    0,
                    _orca_json_from_terminals(_list_terminal("term-new", "folder:unit-a", "✳ successor")),
                    "",
                ),
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


def test_spawn_successor_cleanup_does_not_close_recycled_handle_without_title_ownership() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-recycled", "--json")
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-recycled", "folder:unit-a", "unrelated terminal")
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-recycled", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(
        SuccessionError,
        "spawn liveness list failed.*not closed",
    ) as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert close_command not in calls


def test_spawn_successor_cleanup_closes_recycled_handle_with_confirmed_title_ownership() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-recycled", "--json")
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
                (
                    0,
                    _orca_json_from_terminals(
                        _list_terminal("term-recycled", "folder:unit-a", "● successor")
                    ),
                    "",
                ),
            ],
            create_command: (0, _orca_create_json("term-recycled", "folder:unit-a"), ""),
            close_command: (0, '{"ok":true}', ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(
        SuccessionError,
        "spawn liveness list failed.*closed terminal",
    ) as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert close_command in calls


def test_spawn_successor_cleanup_does_not_close_disconnected_confirmed_handle() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-recycled", "--json")
    disconnected_confirmed = {
        "handle": "term-recycled",
        "worktreeId": "folder:unit-a",
        "worktreePath": "/repo/example",
        "connected": False,
        "title": "✳ successor",
    }
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(), ""),
                (1, "", "orca offline"),
                (0, _orca_json_from_terminals(disconnected_confirmed), ""),
            ],
            create_command: (0, _orca_create_json("term-recycled", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(
        SuccessionError,
        "spawn liveness list failed.*not closed",
    ) as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert close_command not in calls


def test_spawn_successor_liveness_list_failure_does_not_close_preexisting_handle() -> None:
    calls = []
    create_command = _spawn_create_command("folder:unit-a", "start here", "/repo/example", "successor")
    close_command = ("orca", "terminal", "close", "--terminal", "term-recycled", "--json")
    preexisting = _list_terminal("term-recycled", "folder:unit-a", "user shell")
    runner = _recording_runner(
        {
            _GLOBAL_SNAPSHOT_FIXTURE: (0, _orca_json_from_terminals(preexisting), ""),
            _LIST_COMMAND: [
                (0, _orca_json_from_terminals(preexisting), ""),
                (1, "", "orca offline"),
            ],
            create_command: (0, _orca_create_json("term-recycled", "folder:unit-a"), ""),
        },
        calls,
    )

    with unittest.TestCase().assertRaisesRegex(
        SuccessionError,
        "spawn liveness list failed.*pre-existing",
    ) as raised:
        spawn_successor(
            workspace_selector="folder:unit-a",
            kickoff_text="start here",
            root="/repo/example",
            title="successor",
            orca_runner=runner,
        )

    assert raised.exception.exit_code == 25
    assert close_command not in calls


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
    assert "expected_placement" not in payload["verification"]


def test_cli_spawn_dry_run_outputs_expected_placement() -> None:
    result = subprocess.run(
        [
            str(Path(__file__).resolve().parent.parent / "scripts" / "master-succeed"),
            "spawn",
            "--workspace-selector",
            "folder:unit-a",
            "--expected-placement",
            "id:folder:unit-a",
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
    assert payload["verification"]["expected_placement"] == "id:folder:unit-a"


def test_cli_spawn_uses_agent_specific_default_model() -> None:
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
            "--agent",
            "codex",
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
    assert "codex --model gpt-5.6-sol" in payload["startup_command"]


def test_cli_spawn_requires_model_for_unknown_agent() -> None:
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
            "--agent",
            "custom-agent",
            "--title",
            "successor",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--model is required for agent custom-agent" in result.stderr


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
    last_scoped_response = None
    global_snapshot_reused = False

    def run(command: Sequence[str]) -> Tuple[int, str, str]:
        nonlocal global_snapshot_reused, last_scoped_response
        key = tuple(command)
        if (
            key == _LIST_COMMAND
            and _GLOBAL_SNAPSHOT_FIXTURE in responses
            and last_scoped_response is not None
            and not global_snapshot_reused
        ):
            # Tests that exercise spawn_successor's global pre-create snapshot
            # opt in explicitly, without consuming the bare-list sequence.
            global_snapshot_reused = True
            return responses[_GLOBAL_SNAPSHOT_FIXTURE]
        if key not in responses and _is_scoped_terminal_list(command) and _LIST_COMMAND in responses:
            # Reuse bare-list fixtures only after applying the requested
            # worktree selector, so tests cannot hide a wrong selector.
            response = responses[_LIST_COMMAND]
            if isinstance(response, list):
                response = response.pop(0)
            last_scoped_response = response
            return _filter_scoped_response(response, command[4])
        response = responses[key]
        if isinstance(response, list):
            response = response.pop(0)
        if _is_scoped_terminal_list(command):
            last_scoped_response = response
        return response

    return run


def test_runner_does_not_shadow_explicit_global_list_fixture() -> None:
    scoped_list_command = (
        "orca",
        "terminal",
        "list",
        "--worktree",
        "folder:unit-a",
        "--json",
    )
    scoped_response = (0, _orca_json_from_terminals(), "")
    first_global_response = (
        0,
        _orca_json_from_terminals(_list_terminal("term-global", "folder:other", "shell")),
        "",
    )
    runner = _runner(
        {
            scoped_list_command: scoped_response,
            _LIST_COMMAND: [first_global_response],
        }
    )

    assert runner(scoped_list_command) == scoped_response
    assert runner(_LIST_COMMAND) == first_global_response


def _is_scoped_terminal_list(command: Sequence[str]) -> bool:
    return (
        len(command) >= 5
        and tuple(command[:3]) == ("orca", "terminal", "list")
        and command[3] == "--worktree"
        and command[-1] == "--json"
    )


def _scoped_list_command(selector: str) -> Tuple[str, ...]:
    return (
        "orca",
        "terminal",
        "list",
        "--worktree",
        selector,
        "--json",
    )


def _filter_scoped_response(response, selector: str):
    code, stdout, stderr = response
    if code != 0:
        return response
    payload = json.loads(stdout)
    result = payload.get("result")
    terminals = result.get("terminals") if isinstance(result, dict) else None
    if not isinstance(terminals, list):
        return response
    payload["result"]["terminals"] = [
        terminal
        for terminal in terminals
        if _fixture_worktree_matches(terminal, selector)
    ]
    return code, json.dumps(payload), stderr


def _fixture_worktree_matches(terminal: dict, selector: str) -> bool:
    requested = selector.removeprefix("id:")
    for key in ("worktreeId", "worktree_id", "worktreePath", "worktree_path"):
        value = terminal.get(key)
        if value and str(value).removeprefix("id:") == requested:
            return True
    return False


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
