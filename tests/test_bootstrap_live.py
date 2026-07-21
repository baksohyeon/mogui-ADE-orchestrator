from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.bootstrap_live import (
    audit_memories,
    collect_tracks,
    compose,
    latest_handoff,
    load_role_state,
    run_live,
)


HANDOFF = """# handoff
## Role State
```
Current Role: Reference Implementation
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```
"""


class LatestHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_latest_handoff_picks_lexicographic_max(self) -> None:
        (self._dir / "2026-07-19-a.md").write_text("x", encoding="utf-8")
        (self._dir / "2026-07-20-gen6-handoff.md").write_text(HANDOFF, encoding="utf-8")
        picked = latest_handoff(self._dir)
        self.assertIsNotNone(picked)
        self.assertEqual(picked.name, "2026-07-20-gen6-handoff.md")


class LoadRoleStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_load_role_state_returns_block(self) -> None:
        (self._dir / "2026-07-20-gen6-handoff.md").write_text(HANDOFF, encoding="utf-8")
        block, alerts = load_role_state(self._dir)
        self.assertIsNotNone(block)
        self.assertIn("Current Role: Reference Implementation", block)
        self.assertEqual(alerts, [])

    def test_load_role_state_missing_dir_alerts(self) -> None:
        block, alerts = load_role_state(self._dir / "none")
        self.assertIsNone(block)
        self.assertTrue(any("role-state" in a for a in alerts))


MEMS = """### rule-a
내용 [L0] 규칙
### ptr-b
내용 [L1 포인터]
### naked-c
태그 없는 서사
"""


class AuditMemoriesTests(unittest.TestCase):
    def test_audit_counts_tiers_and_flags_untagged(self) -> None:
        line, alerts = audit_memories(MEMS, cap=15, budget_chars=12000)
        self.assertIn("memories=3", line)
        self.assertIn("L0=1", line)
        self.assertIn("L1=1", line)
        self.assertIn("untagged=1", line)
        self.assertTrue(any("untagged" in a for a in alerts))

    def test_audit_alerts_over_cap_and_budget(self) -> None:
        many = "\n".join("### k%d\n[L0] x" % i for i in range(16))
        line, alerts = audit_memories(many, cap=15, budget_chars=10)
        self.assertTrue(any("cap" in a for a in alerts))
        self.assertTrue(any("BUDGET-ALERT" in a for a in alerts))


class CollectTracksTests(unittest.TestCase):
    def test_collect_tracks_parses_titles(self) -> None:
        fake = lambda argv: "◐ AL-3be ● P1 OPS-02: batch 살리기\n◐ AL-mpr ● P1 QA-01: 마감\n"
        tracks, alerts = collect_tracks(fake)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(alerts, [])

    def test_collect_tracks_runner_failure_alerts(self) -> None:
        def boom(argv):
            raise RuntimeError("bd missing")

        tracks, alerts = collect_tracks(boom)
        self.assertEqual(tracks, [])
        self.assertTrue(any("tracks" in a for a in alerts))


class ComposeTests(unittest.TestCase):
    def test_compose_orders_sections_and_caps_self_block(self) -> None:
        out = compose(
            "Current Role: X",
            ["t"] * 500,
            "[BD-PRIME-AUDIT] ...",
            [],
            "[DUAL-INSTANCE] none",
            "Charter: Recovery Flow 0 정독",
        )
        self.assertTrue(out.startswith("[MASTER-BOOTSTRAP v1]"))
        self.assertLessEqual(len(out), 2200)
        self.assertIn("[BUDGET-ALERT] self-block", out)


class RunLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_run_live_never_raises(self) -> None:
        def boom(argv):
            raise RuntimeError("everything broken")

        out = run_live(self._dir / "none", bd_runner=boom, probe=lambda: "")
        self.assertTrue(
            "[MASTER-BOOTSTRAP v1]" in out or "[BOOTSTRAP-FALLBACK]" in out
        )


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_cli_exits_zero_with_missing_dir(self) -> None:
        script = Path(__file__).resolve().parent.parent / "scripts" / "master-bootstrap-live"
        proc = subprocess.run(
            [sys.executable, str(script), "--handoff-dir", str(self._dir / "none")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertNotEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
