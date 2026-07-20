from __future__ import annotations

import json
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
    assert detect_trigger("다음 마스터로 넘기자", {}).status == "IMMEDIATE"
    advisory = detect_trigger("", {"context_ratio": 0.72})
    assert advisory.status == "ADVISORY"
    assert "자동 승계 금지" in advisory.message
    assert detect_trigger("계속 진행", {}).status == "NONE"


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


def test_retire_predecessor_rejects_expected_mismatch() -> None:
    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="not-present",
        orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}),
    )

    assert report.status == "REFUSED"
    assert report.target_handle is None


def test_retire_predecessor_rejects_ambiguous_candidates() -> None:
    report = retire_predecessor(
        predecessor_selector="u8-recovery",
        self_handle="term-self",
        expected_substr="u8-recovery",
        orca_runner=_runner({("orca", "terminal", "list", "--json"): (0, ORCA_LIST_JSON, "")}),
    )

    assert report.status == "REFUSED"
    assert "ambiguous" in report.reason


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
    return json.dumps(
        {
            "ok": True,
            "result": {
                "terminals": [
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
                ]
            },
        }
    )


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
