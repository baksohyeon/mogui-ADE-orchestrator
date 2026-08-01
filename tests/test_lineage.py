from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.lineage import LineageValidationError, append_entry


GEN5_FIXTURE = """# Master Lineage

> **OBSERVABILITY ONLY.** This ledger is historical metadata. It must not become
> runtime memory and must not influence any execution decision. Use it for
> retrospectives, succession quality analysis, and operational metrics.
> Append-only: existing entries are never edited.

---

## Gen 5 — 2026-07-20 afternoon

- **Generation**: 5
- **Parent Session**: 39c1ec17 (claude PID 40309, Fable 5)
- **Successor Session**: 0464cb11 (claude PID 19909, Fable 5)
- **Timestamp**: 2026-07-20 afternoon (succession instruction) / 15:02 successor confirmed predecessor exit
- **Inherited Role**: Reference Implementation (Role Lock ENABLED; succession does not change the role)
- **Succession reason**: Advisory threshold (predecessor context measured at 63%, owner instruction)
- **Recovery sources**: Charter (Git) / thin handoff / run log / tracker (ready 15 + in_progress 6) / dispatch ledger
- **Inherited open tracks**: 7 (one active, six parked)
- **Verification**: **PASS** — baselines re-measured clean, dispatch ledger entry confirmed, drift monitor rearmed with a first heartbeat at 15:01
- **Repeated-question count**: 0
- **Reopened-decision count**: 0
- **Context-loss summary**: none; verification contract, dispatch discipline, and worktree map all carried over intact
- **Predecessor retirement verified**: YES — PID 40309 matched by command line, killed, absence reconfirmed with ps; other sessions unaffected
- **Notes**: orphan drift monitor from the predecessor was stopped and rearmed under Gen 5 with a double-run guard
"""


def valid_entry(generation: int = 6) -> dict[str, object]:
    return {
        "generation": generation,
        "parent_session": "0464cb11 (claude PID 19909, Fable 5)",
        "successor_session": "u10-test-successor (Fable 5)",
        "timestamp": "2026-07-20 afternoon (U10 dry-run)",
        "inherited_role": "Reference Implementation (Role Lock ENABLED; succession does not change the role)",
        "succession_reason": "U10 Lineage Recorder dry-run append verification",
        "recovery_sources": "Charter (Git) / thin handoff / bd prime / pytest fixture",
        "inherited_open_tracks": "1 (U10 Lineage Recorder landing verification)",
        "verification": "PASS",
        "repeated_question_count": 0,
        "reopened_decision_count": 0,
        "context_loss_summary": "none; dry-run fixture preserves existing bytes",
        "predecessor_retirement_verified": "YES — dry-run only, no real predecessor touched",
        "notes": "test entry shaped like the Gen 5 record",
    }


class LineageRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "MASTER-LINEAGE.md"
        self.path.write_text(GEN5_FIXTURE, encoding="utf-8")

    def test_append_entry_adds_gen_section(self) -> None:
        append_entry(self.path, valid_entry())

        content = self.path.read_text(encoding="utf-8")
        self.assertIn("## Gen 6 — 2026-07-20 afternoon (U10 dry-run)", content)
        self.assertIn("- **Generation**: 6", content)
        self.assertIn("- **Verification**: **PASS**", content)
        self.assertIn("- **Notes**: test entry shaped like the Gen 5 record", content)

    def test_missing_required_field_is_rejected(self) -> None:
        entry = valid_entry()
        del entry["parent_session"]

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

    def test_unknown_verification_is_rejected(self) -> None:
        entry = valid_entry()
        entry["verification"] = "UNKNOWN"

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

    def test_duplicate_generation_is_rejected(self) -> None:
        with self.assertRaises(LineageValidationError):
            append_entry(self.path, valid_entry(generation=5))

    def test_existing_content_bytes_are_unchanged(self) -> None:
        original = self.path.read_bytes()

        append_entry(self.path, valid_entry())

        updated = self.path.read_bytes()
        self.assertEqual(original, updated[: len(original)])

    def test_validation_failure_leaves_file_unchanged(self) -> None:
        original = self.path.read_bytes()
        entry = valid_entry()
        entry["repeated_question_count"] = -1

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

        self.assertEqual(original, self.path.read_bytes())

    def test_real_lineage_copy_dry_run_preserves_original_prefix(self) -> None:
        source = Path("/Users/dev/workspace/example-product/example-ops/docs/lineage/MASTER-LINEAGE.md")
        if not source.exists():
            self.skipTest("real MASTER-LINEAGE.md source is unavailable")

        dry_run_path = Path(self.tempdir.name) / "MASTER-LINEAGE-copy.md"
        shutil.copyfile(source, dry_run_path)
        original = dry_run_path.read_bytes()

        append_entry(
            dry_run_path,
            valid_entry(generation=_next_generation(dry_run_path)),
        )

        self.assertEqual(original, dry_run_path.read_bytes()[: len(original)])
        self.assertEqual(original, source.read_bytes())


def _next_generation(path: Path) -> int:
    generations: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- **Generation**: "):
            continue
        value = line.rsplit(":", maxsplit=1)[1].strip()
        if value.isdigit():
            generations.append(int(value))
    return max(generations, default=0) + 1


if __name__ == "__main__":
    unittest.main()
