from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.bootstrap_live import latest_handoff, load_role_state


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


if __name__ == "__main__":
    unittest.main()
