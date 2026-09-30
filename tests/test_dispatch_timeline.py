from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from master_runtime.core.dispatch_timeline import (
    DISPATCH_SHOW_SOURCE,
    EVENT_LOG_SOURCE,
    LEDGER_SOURCE,
    DispatchTimelineBuilder,
)


class JoinOrderTests(unittest.TestCase):
    def test_rows_from_all_three_sources_are_time_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"

            ledger.write_text(
                "\n".join(
                    [
                        json.dumps({"ts": 100, "job_id": "ctx_x", "orchestration_task": "task_x", "decision": "ALLOW"}),
                    ]
                ),
                encoding="utf-8",
            )
            event_log.write_text(
                "\n".join(
                    [
                        json.dumps({"ts": 50, "dispatch_id": "ctx_x", "task_id": "task_x", "event": "dispatch_launched", "outcome": "pass"}),
                        json.dumps({"ts": 150, "dispatch_id": "ctx_x", "task_id": "task_x", "event": "reaped", "outcome": "pass"}),
                    ]
                ),
                encoding="utf-8",
            )

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    payload = {
                        "result": {
                            "dispatch": {
                                "status": "COMPLETED",
                                "last_heartbeat_at": "1970-01-01T00:02:00+00:00",
                            }
                        }
                    }
                    return 0, json.dumps(payload), ""
                return 1, "", ""

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(task_id="task_x")

            self.assertEqual(len(timeline.rows), 4)
            sources = [row.source for row in timeline.rows]
            timestamps = [row.timestamp for row in timeline.rows]
            self.assertEqual(timestamps, sorted(timestamps))
            # Failability: a version that appended sources without sorting would
            # put the ledger row (ts=100) before the earlier event-log row (ts=50).
            self.assertEqual(sources[0], EVENT_LOG_SOURCE)
            self.assertEqual(timestamps[0], 50)
            self.assertEqual(timeline.missing_sources, ())

    def test_dispatch_id_lookup_filters_by_dispatch_id_not_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text(
                json.dumps({"ts": 10, "job_id": "ctx_other", "orchestration_task": "task_x"}) + "\n",
                encoding="utf-8",
            )
            event_log.write_text("", encoding="utf-8")

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                return 1, "", ""

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(dispatch_id="ctx_target")

            self.assertEqual(timeline.rows, ())
            self.assertIn(LEDGER_SOURCE, timeline.missing_sources)


class MissingSourceTests(unittest.TestCase):
    def test_absent_sources_are_named_not_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"  # does not exist
            event_log = Path(tmp) / "event-log.jsonl"  # does not exist

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                return 1, "", "dispatch-show failed"

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(task_id="task_missing")

            self.assertEqual(timeline.rows, ())
            self.assertEqual(
                set(timeline.missing_sources),
                {LEDGER_SOURCE, EVENT_LOG_SOURCE, DISPATCH_SHOW_SOURCE},
            )
            # Failability: a version that only reports missing sources when ALL
            # three are empty (rather than naming each independently) would
            # still pass an all-missing case but fail the next test, where only
            # dispatch-show is missing and the other two are present.

    def test_only_the_actually_empty_source_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text(
                json.dumps({"ts": 1, "job_id": "ctx_x", "orchestration_task": "task_x"}) + "\n",
                encoding="utf-8",
            )
            event_log.write_text(
                json.dumps({"ts": 2, "dispatch_id": "ctx_x", "task_id": "task_x", "event": "e"}) + "\n",
                encoding="utf-8",
            )

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                return 1, "", "orca not reachable"

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(task_id="task_x")

            self.assertEqual(timeline.missing_sources, (DISPATCH_SHOW_SOURCE,))
            self.assertEqual(len(timeline.rows), 2)


class SinceListingTests(unittest.TestCase):
    def test_since_lists_each_dispatch_with_its_last_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            now = time.time()

            ledger.write_text(
                "\n".join(
                    [
                        json.dumps({"ts": now - 60, "job_id": "ctx_a", "orchestration_task": "task_a", "decision": "ALLOW"}),
                    ]
                ),
                encoding="utf-8",
            )
            event_log.write_text(
                "\n".join(
                    [
                        json.dumps({"ts": now - 30, "dispatch_id": "ctx_a", "task_id": "task_a", "event": "wait_verdict", "outcome": "DEAD"}),
                        json.dumps({"ts": now - 999999, "dispatch_id": "ctx_old", "task_id": "task_old", "event": "dispatch_launched", "outcome": "pass"}),
                    ]
                ),
                encoding="utf-8",
            )

            builder = DispatchTimelineBuilder(
                orca_runner=lambda cmd: (1, "", ""), ledger_path=ledger, event_log_path=event_log
            )
            rows = builder.list_since(hours=1)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["dispatch_id"], "ctx_a")
            # The later event-log row (ts=now-30) must win over the earlier
            # ledger row (ts=now-60) as ctx_a's "last event".
            self.assertEqual(rows[0]["last_event"], "wait_verdict")
            self.assertEqual(rows[0]["last_outcome"], "DEAD")
            # Failability: a version that did not filter by cutoff would also
            # return ctx_old, whose only row is far outside the 1-hour window.

    def test_since_excludes_rows_before_the_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text("", encoding="utf-8")
            event_log.write_text(
                json.dumps(
                    {
                        "ts": time.time() - 7200,
                        "dispatch_id": "ctx_stale",
                        "task_id": "task_stale",
                        "event": "reaped",
                        "outcome": "pass",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            builder = DispatchTimelineBuilder(
                orca_runner=lambda cmd: (1, "", ""), ledger_path=ledger, event_log_path=event_log
            )
            rows = builder.list_since(hours=1)

            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
