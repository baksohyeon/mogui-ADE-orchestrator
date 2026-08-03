from __future__ import annotations

from windows_exec_surface import skip_windows_exec_surface
import json
import subprocess
from pathlib import Path
from typing import Sequence, Tuple

from master_runtime.core.recovery import (
    RecoveryConfig,
    _process_probe_from_runner,
    filter_running_monitor_processes,
    recover,
)
from master_runtime.core.work_ledger import JsonlWorkLedger, WorkspaceRuntime


ROLE_STATE_BLOCK = """```
Current Role: Reference Implementation
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```"""

GIT_NON_REPO_ERROR = "fatal: not a git repository (or any of the parent directories): .git\n"

PS_COMMAND_OUTPUT = """33196 /bin/zsh /private/tmp/claude-501/0464cb11-aaaa-bbbb-cccc-dddddddddddd/scratchpad/drift-monitor.sh
8241 /bin/zsh -c F=/private/tmp/claude-501/jobs/task-drift-monitor.json; printf %s "$F"
40309 pgrep -f drift-monitor.sh
"""


def test_recovery_all_steps_ok_with_active_track_checklist(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\nBody\n")
    ledger_path = tmp_path / "workspace-ledger.jsonl"
    runtime = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(100.0)))
    runtime.register_track("track-a", "Alpha", ("issue:a",))

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=handoff,
            ledger_path=ledger_path,
            repo_paths=(tmp_path / "repo",),
            monitor_pgrep_patterns=("no-monitor",),
            session_id=None,
        ),
        command_runner=_git_runner(
            {
                "rev-parse": (0, "1a2b3c4d\n", ""),
                "branch": (0, "main\n", ""),
                "status": (0, "", ""),
            }
        ),
        process_probe=lambda pattern: (1, "", ""),
    )

    payload = report.to_dict()
    assert _step(payload, "0")["status"] == "OK"
    assert _step(payload, "1")["status"] == "OK"
    assert _step(payload, "1-ledger")["status"] == "OK"
    assert _step(payload, "2-3")["status"] == "OK"
    assert _step(payload, "4")["status"] == "OK"
    assert _step(payload, "5")["status"] == "OK"
    assert _step(payload, "6")["status"] == "OK"
    assert payload["repositories"][0]["head"] == "1a2b3c4d"
    assert payload["repositories"][0]["branch"] == "main"
    assert payload["active_tracks"][0]["track_id"] == "track-a"
    assert "track-a (Alpha)" in _step(payload, "6")["manual_actions"][0]


def test_missing_charter_is_step0_miss_and_fail_closed(tmp_path: Path) -> None:
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    report = recover(
        RecoveryConfig(
            charter_path=tmp_path / "missing-charter.md",
            handoff_path=handoff,
            ledger_path=None,
            repo_paths=(tmp_path / "repo",),
            monitor_pgrep_patterns=("drift-monitor.sh",),
        ),
        command_runner=lambda command: (_raise_if_called(command)),
        process_probe=lambda pattern: (_raise_if_called((pattern,))),
    )

    payload = report.to_dict()
    assert _step(payload, "0")["status"] == "MISS"
    assert _step(payload, "1")["status"] == "SKIP"
    assert _step(payload, "2-3")["status"] == "SKIP"
    assert _step(payload, "5")["status"] == "SKIP"
    assert payload["repositories"] == []
    assert payload["monitors"] == []


def test_missing_handoff_is_step1_miss(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=tmp_path / "missing-handoff.md",
            ledger_path=None,
            repo_paths=(),
            monitor_pgrep_patterns=(),
        )
    )

    assert _step(report.to_dict(), "1")["status"] == "MISS"


def test_non_git_repo_path_warns_in_steps_2_3(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=handoff,
            ledger_path=None,
            repo_paths=(tmp_path / "not-git",),
            monitor_pgrep_patterns=(),
        ),
        command_runner=lambda command: (128, "", GIT_NON_REPO_ERROR),
    )

    payload = report.to_dict()
    assert _step(payload, "2-3")["status"] == "WARN"
    assert "not a git repository" in payload["repositories"][0]["evidence"]


def test_monitor_found_is_rearm_target(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=handoff,
            ledger_path=None,
            repo_paths=(),
            monitor_pgrep_patterns=("drift-monitor.sh",),
        ),
        process_probe=lambda pattern: (0, PgrepFixture.with_pattern(pattern), ""),
    )

    payload = report.to_dict()
    assert _step(payload, "5")["status"] == "WARN"
    assert payload["monitors"][0]["matches"][0].startswith("33196 /bin/zsh")
    assert len(payload["monitors"][0]["matches"]) == 1
    assert any(
        "Terminate then re-arm monitor pattern 'drift-monitor.sh'" in action
        for action in payload["manual_actions"]
    )


def test_monitor_filter_only_accepts_process_executing_script() -> None:
    matches = filter_running_monitor_processes("drift-monitor.sh", PS_COMMAND_OUTPUT)

    assert matches == (
        "33196 /bin/zsh /private/tmp/claude-501/0464cb11-aaaa-bbbb-cccc-dddddddddddd/scratchpad/drift-monitor.sh",
    )


def test_default_process_probe_builds_ps_command_lines_from_pids() -> None:
    result = _process_probe_from_runner(
        "drift-monitor.sh",
        _process_runner(
            {
                ("pgrep", "-f", "drift-monitor.sh"): (0, "28797\n33196\n40309\n", ""),
                ("ps", "-p", "28797", "-o", "pid=,command="): (
                    0,
                    '28797 /bin/zsh -c F=/private/tmp/claude-501/jobs/task-drift-monitor.json; printf %s "$F"\n',
                    "",
                ),
                ("ps", "-p", "33196", "-o", "pid=,command="): (
                    0,
                    "33196 /bin/zsh /private/tmp/claude-501/0464cb11-aaaa-bbbb-cccc-dddddddddddd/scratchpad/drift-monitor.sh\n",
                    "",
                ),
                ("ps", "-p", "40309", "-o", "pid=,command="): (
                    0,
                    "40309 pgrep -f drift-monitor.sh\n",
                    "",
                ),
            }
        ),
    )

    assert result[0] == 0
    assert filter_running_monitor_processes("drift-monitor.sh", result[1]) == (
        "33196 /bin/zsh /private/tmp/claude-501/0464cb11-aaaa-bbbb-cccc-dddddddddddd/scratchpad/drift-monitor.sh",
    )


def test_monitor_filter_empty_keeps_step5_ok(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")
    pgrep_output = """8241 /bin/zsh -c F=/private/tmp/claude-501/jobs/task-drift-monitor.json; printf %s "$F"
40309 /bin/zsh -lc pgrep -af drift-monitor.sh
"""

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=handoff,
            ledger_path=None,
            repo_paths=(),
            monitor_pgrep_patterns=("drift-monitor.sh",),
        ),
        process_probe=lambda pattern: (0, pgrep_output, ""),
    )

    payload = report.to_dict()
    assert payload["monitors"][0]["matches"] == ()
    assert _step(payload, "5")["status"] == "OK"
    assert not any(
        "Terminate then re-arm monitor pattern" in action
        for action in payload["manual_actions"]
    )


def test_missing_ledger_path_marks_step1_skip(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    report = recover(
        RecoveryConfig(
            charter_path=charter,
            handoff_path=handoff,
            ledger_path=None,
            repo_paths=(),
            monitor_pgrep_patterns=(),
        )
    )

    step1 = _step(report.to_dict(), "1-ledger")
    assert step1["status"] == "SKIP"
    assert "work ledger SKIP" in step1["evidence"]


@skip_windows_exec_surface
def test_cli_outputs_valid_json(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    result = subprocess.run(
        [
            str(Path(__file__).resolve().parent.parent / "scripts" / "master-recover"),
            "--charter",
            str(charter),
            "--handoff",
            str(handoff),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert _step(payload, "0")["status"] == "OK"


class PgrepFixture:
    @staticmethod
    def with_pattern(pattern: str) -> str:
        assert pattern == "drift-monitor.sh"
        return PS_COMMAND_OUTPUT


class _Clock:
    def __init__(self, start: float) -> None:
        self.value = start

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def _file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _git_runner(mapping: dict) -> callable:
    def run(command: Sequence[str]) -> Tuple[int, str, str]:
        joined = " ".join(command)
        if "rev-parse" in joined:
            return mapping["rev-parse"]
        if "branch --show-current" in joined:
            return mapping["branch"]
        if "status --porcelain" in joined:
            return mapping["status"]
        raise AssertionError("unexpected command: " + joined)

    return run


def _process_runner(mapping: dict) -> callable:
    def run(command: Sequence[str]) -> Tuple[int, str, str]:
        key = tuple(command)
        if key not in mapping:
            raise AssertionError("unexpected command: " + " ".join(command))
        return mapping[key]

    return run


def _step(payload: dict, step: str) -> dict:
    for item in payload["steps"]:
        if item["step"] == step:
            return item
    raise AssertionError("missing step " + step)


def _raise_if_called(command: Sequence[str]) -> Tuple[int, str, str]:
    raise AssertionError("unexpected command: " + " ".join(command))
