from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.work_ledger import JsonlWorkLedger, WorkspaceRuntime


class WorkLedgerTests(unittest.TestCase):
    def test_register_update_close_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "workspace-ledger.jsonl"
            runtime = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(100.0)))

            first = runtime.register_track("track-1", "First track", ("AL-1", "doc:a"))
            updated = runtime.update_track("track-1", "IN_PROGRESS", "worker accepted")
            closed = runtime.close_track("track-1", "merged")

            self.assertEqual(first.status, "REGISTERED")
            self.assertEqual(updated.status, "IN_PROGRESS")
            self.assertEqual(updated.note, "worker accepted")
            self.assertEqual(closed.status, "CLOSED")
            self.assertEqual(closed.resolution, "merged")
            self.assertEqual(runtime.active_tracks(), {})

            events = _jsonl_events(ledger_path)
            self.assertEqual(
                [event["event"] for event in events],
                ["register", "update", "close"],
            )
            self.assertTrue(all(isinstance(event["ts"], float) for event in events))
            self.assertEqual(events[0]["refs"], ["AL-1", "doc:a"])


    def test_replay_reopens_same_active_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "workspace-ledger.jsonl"
            runtime = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(10.0)))

            runtime.register_track("track-1", "First", ("ref-1",))
            runtime.register_track("track-2", "Second", ())
            runtime.update_track("track-1", "RUNNING", "handoff sent")

            reopened = WorkspaceRuntime(JsonlWorkLedger(ledger_path))

            self.assertEqual(reopened.active_tracks(), runtime.active_tracks())
            self.assertEqual(reopened.active_tracks()["track-1"].status, "RUNNING")
            self.assertEqual(reopened.active_tracks()["track-2"].status, "REGISTERED")


    def test_refresh_reconciles_stale_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "workspace-ledger.jsonl"
            first = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(20.0)))
            second = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(30.0)))

            first.register_track("track-1", "First", ())

            self.assertEqual(second.active_tracks(), {})

            second.refresh()

            self.assertEqual(tuple(second.active_tracks()), ("track-1",))


    def test_corrupt_jsonl_lines_are_skipped_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "workspace-ledger.jsonl"
            ledger_path.write_text(
                "\n".join(
                    (
                        json.dumps(
                            {
                                "ts": 1.0,
                                "event": "register",
                                "track_id": "track-1",
                                "title": "First",
                                "refs": ["ref-1"],
                            },
                            sort_keys=True,
                        ),
                        "{broken json",
                        json.dumps(
                            {
                                "ts": 2.0,
                                "event": "update",
                                "track_id": "track-1",
                                "status": "RUNNING",
                                "note": "still valid after corrupt line",
                            },
                            sort_keys=True,
                        ),
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            ledger = JsonlWorkLedger(ledger_path)
            runtime = WorkspaceRuntime(ledger)

            self.assertEqual(runtime.active_tracks()["track-1"].status, "RUNNING")
            self.assertEqual(len(ledger.warnings), 1)
            self.assertIn("line 2", ledger.warnings[0])


    def test_close_excludes_track_from_active_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = WorkspaceRuntime(
                JsonlWorkLedger(Path(tmp) / "workspace-ledger.jsonl", clock=_Clock(40.0))
            )

            runtime.register_track("track-1", "First", ())
            runtime.register_track("track-2", "Second", ())
            runtime.close_track("track-1", "cancelled")

            active = runtime.active_tracks()
            self.assertEqual(tuple(active), ("track-2",))
            self.assertNotIn("track-1", active)


    def test_update_unregistered_track_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = WorkspaceRuntime(JsonlWorkLedger(Path(tmp) / "workspace-ledger.jsonl"))

            with self.assertRaisesRegex(ValueError, "unknown track"):
                runtime.update_track("missing", "RUNNING", "should fail")


    def test_realistic_three_track_reopen_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "dispatch-ledger-format.jsonl"
            runtime = WorkspaceRuntime(JsonlWorkLedger(ledger_path, clock=_Clock(50.0)))

            runtime.register_track("track-a", "Alpha", ("issue:a",))
            runtime.register_track("track-b", "Beta", ("issue:b",))
            runtime.register_track("track-c", "Gamma", ("issue:c",))
            runtime.update_track("track-b", "RUNNING", "worker active")
            runtime.close_track("track-c", "done")

            reopened = WorkspaceRuntime(JsonlWorkLedger(ledger_path))
            active = reopened.active_tracks()
            all_tracks = reopened.tracks()

            self.assertEqual(len(active), 2)
            self.assertEqual(active["track-b"].status, "RUNNING")
            self.assertEqual(all_tracks["track-c"].status, "CLOSED")
            self.assertEqual(all_tracks["track-c"].resolution, "done")


class _Clock:
    def __init__(self, start: float) -> None:
        self.value = start

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def _jsonl_events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
