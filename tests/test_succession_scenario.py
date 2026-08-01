from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from master_runtime.core.lineage import append_entry
from master_runtime.core.recovery import RecoveryConfig, recover
from master_runtime.core.succession import (
    build_handoff,
    retire_predecessor,
    verify_successor,
)
from master_runtime.core.work_ledger import JsonlWorkLedger, WorkspaceRuntime


class SuccessionScenarioTests(unittest.TestCase):
    def test_u9_mvp_scenario_recover_verify_retire_and_append_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            charter = root / "MASTER-ORCHESTRATOR-CHARTER.md"
            handoff = root / "u9-handoff.md"
            ledger = root / "workspace-ledger.jsonl"
            lineage = root / "MASTER-LINEAGE.md"
            charter.write_text("# Charter\n\n- Reference Implementation\n", encoding="utf-8")
            WorkspaceRuntime(JsonlWorkLedger(ledger, clock=_Clock(100.0))).register_track(
                "U9",
                "Succession Manager",
                ("docs/internal/specs/transcript-ledger-spec.md",),
            )
            handoff.write_text(
                build_handoff(
                    {
                        "current_role": "Reference Implementation",
                        "current_objective": "Land U9 Succession Manager MVP.",
                        "active_tracks": ["U9 Succession Manager"],
                        "open_tracks": ["U10 lineage append"],
                        "accepted_artifacts": ["U1 bootstrap", "U8 recovery", "U3 ledger"],
                        "deferred_work": ["headless non-Orca fallback"],
                        "open_questions": ["none"],
                        "recommended_next_role": "Reference Implementation",
                        "observed_baseline": "repo clean; monitors quiet",
                    }
                ),
                encoding="utf-8",
            )

            report = recover(
                RecoveryConfig(
                    charter_path=charter,
                    handoff_path=handoff,
                    ledger_path=ledger,
                    repo_paths=(root / "repo",),
                    monitor_pgrep_patterns=("drift-monitor.sh",),
                ),
                command_runner=_git_runner,
                process_probe=lambda pattern: (1, "", ""),
            )
            verification = verify_successor(report)
            retirement = retire_predecessor(
                predecessor_selector="u8-recovery",
                self_handle="term-u9",
                expected_substr="u8-recovery",
                orca_runner=_orca_runner,
                execute=False,
            )
            append_entry(
                lineage,
                {
                    "generation": 13,
                    "parent_session": "term-u8",
                    "successor_session": "term-u9",
                    "timestamp": "2026-07-20 U9 scenario",
                    "inherited_role": "Reference Implementation",
                    "succession_reason": "U9 integration scenario",
                    "recovery_sources": "U1 bootstrap / U8 recover / U3 ledger",
                    "inherited_open_tracks": "U9 Succession Manager",
                    "verification": verification.status,
                    "repeated_question_count": 0,
                    "reopened_decision_count": 0,
                    "context_loss_summary": "none",
                    "predecessor_retirement_verified": retirement.status,
                },
            )

            self.assertEqual(verification.status, "PASS")
            self.assertEqual(retirement.status, "DRY_RUN")
            self.assertIn("- **Generation**: 13", lineage.read_text(encoding="utf-8"))


def _git_runner(command):
    if tuple(command[-2:]) == ("--short=8", "HEAD"):
        return 0, "12345678\n", ""
    if tuple(command[-2:]) == ("branch", "--show-current"):
        return 0, "feat/u9-succession\n", ""
    if tuple(command[-2:]) == ("status", "--porcelain"):
        return 0, "", ""
    return 1, "", "unexpected command"


def _orca_runner(command):
    if tuple(command) != ("orca", "terminal", "list", "--json"):
        return 1, "", "unexpected command"
    return (
        0,
        """{"ok":true,"result":{"terminals":[{"handle":"term-u9","ptyId":"pty-u9","worktreeId":"repo:u9","worktreePath":"/repo/mogui-ADE-orchestrator/u9-succession","branch":"feat/u9-succession","connected":true,"title":"u9 successor"},{"handle":"term-u8","ptyId":"pty-u8","worktreeId":"repo:u8","worktreePath":"/repo/mogui-ADE-orchestrator/u8-recovery","branch":"feat/u8-recovery","connected":true,"title":"u8 predecessor"}]}}""",
        "",
    )


class _Clock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


if __name__ == "__main__":
    unittest.main()
