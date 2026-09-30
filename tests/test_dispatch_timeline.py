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
            # task_id="task_x" matches the ledger row's task — only the
            # dispatch_id filter (not a task_id fallback) can explain the
            # row still being excluded below.
            timeline = builder.build(dispatch_id="ctx_target", task_id="task_x")

            self.assertEqual(timeline.rows, ())
            self.assertIn(LEDGER_SOURCE, timeline.missing_sources)
            # Failability: a version that matched on task_id instead of (or in
            # addition to) dispatch_id would include the ctx_other row here,
            # since its orchestration_task is task_x.

    def test_dispatch_id_lookup_resolves_task_id_before_dispatch_show(self) -> None:
        """dispatch-show only reliably serves the live snapshot by --task;
        a bare dispatch id must be resolved to its task id first, the same
        way worker_reap.py does, rather than passed through as --dispatch."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text("", encoding="utf-8")
            event_log.write_text("", encoding="utf-8")

            commands: list[list[str]] = []

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                commands.append(cmd)
                if "worker-list" in cmd:
                    payload = {
                        "result": {
                            "workers": [
                                {"dispatch_id": "ctx_target", "task_id": "task_target"}
                            ]
                        }
                    }
                    return 0, json.dumps(payload), ""
                if "dispatch-show" in cmd:
                    # Only --task is served; --dispatch is refused, the same
                    # way the real RPC only reliably serves --task lookups.
                    # A buggy version that passes --dispatch straight through
                    # gets refused here, landing dispatch-show in
                    # missing_sources — the assertion below then actually
                    # discriminates instead of passing either way.
                    if "--task" in cmd:
                        payload = {"result": {"dispatch": {"status": "COMPLETED"}}}
                        return 0, json.dumps(payload), ""
                    return 1, "", ""
                return 1, "", ""

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(dispatch_id="ctx_target")

            dispatch_show_cmds = [c for c in commands if "dispatch-show" in c]
            self.assertEqual(len(dispatch_show_cmds), 1)
            self.assertIn("--task", dispatch_show_cmds[0])
            self.assertIn("task_target", dispatch_show_cmds[0])
            self.assertNotIn("--dispatch", dispatch_show_cmds[0])
            self.assertNotIn(DISPATCH_SHOW_SOURCE, timeline.missing_sources)
            # Failability: a version that called dispatch-show with
            # --dispatch ctx_target directly (never resolving a task id)
            # would get refused by the fake RPC above and leave dispatch-show
            # in missing_sources, whereas the correct --task form succeeds.

    def test_event_log_row_with_only_dispatch_id_joins_via_ledger_link(self) -> None:
        """An event that carries a dispatch id but no task id (e.g. a
        wait_verdict for an OPEN_PANE row with no task id available at emit
        time) still belongs to this task's timeline once the ledger has
        linked that dispatch to the task."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text(
                json.dumps(
                    {"ts": 1, "job_id": "ctx_linked", "orchestration_task": "task_x"}
                )
                + "\n",
                encoding="utf-8",
            )
            event_log.write_text(
                json.dumps(
                    {
                        "ts": 2,
                        "dispatch_id": "ctx_linked",
                        "event": "wait_verdict",
                        "outcome": "OPEN_PANE",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            builder = DispatchTimelineBuilder(
                orca_runner=lambda cmd: (1, "", ""),
                ledger_path=ledger,
                event_log_path=event_log,
            )
            timeline = builder.build(task_id="task_x")

            events = [row.event for row in timeline.rows if row.source == EVENT_LOG_SOURCE]
            self.assertIn("wait_verdict", events)
            # Failability: a version that only matched event-log rows by their
            # own task_id field would drop this row, since it carries no
            # task_id at all.


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


class DispatchShowTimestampTests(unittest.TestCase):
    def test_epoch_zero_last_heartbeat_is_kept_not_discarded(self) -> None:
        """`_to_epoch` returns 0.0 for an epoch-0 timestamp, which is falsy;
        an `or` chain would discard it and fall through to "now" instead."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text("", encoding="utf-8")
            event_log.write_text("", encoding="utf-8")

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    payload = {
                        "result": {
                            "dispatch": {
                                "status": "COMPLETED",
                                "last_heartbeat_at": "1970-01-01T00:00:00+00:00",
                            }
                        }
                    }
                    return 0, json.dumps(payload), ""
                return 1, "", ""

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(task_id="task_x")

            show_rows = [r for r in timeline.rows if r.source == DISPATCH_SHOW_SOURCE]
            self.assertEqual(len(show_rows), 1)
            self.assertEqual(show_rows[0].timestamp, 0.0)
            # Failability: a version using `A or B or C or time.time()` would
            # report this row's timestamp as roughly "now" instead of 0.0.

    def test_completed_dispatch_uses_completion_time_not_an_earlier_heartbeat(
        self,
    ) -> None:
        """A heartbeat recorded while the worker was still running must not
        outrank the later completion timestamp for a COMPLETED dispatch —
        otherwise `status:COMPLETED` sorts before events that happened while
        the worker was still alive."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text("", encoding="utf-8")
            event_log.write_text("", encoding="utf-8")

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    payload = {
                        "result": {
                            "dispatch": {
                                "status": "COMPLETED",
                                "last_heartbeat_at": "1970-01-01T00:00:00+00:00",
                                "completed_at": "1970-01-01T00:05:00+00:00",
                            }
                        }
                    }
                    return 0, json.dumps(payload), ""
                return 1, "", ""

            builder = DispatchTimelineBuilder(
                orca_runner=fake_runner, ledger_path=ledger, event_log_path=event_log
            )
            timeline = builder.build(task_id="task_x")

            show_rows = [r for r in timeline.rows if r.source == DISPATCH_SHOW_SOURCE]
            self.assertEqual(len(show_rows), 1)
            self.assertEqual(show_rows[0].timestamp, 300.0)
            # Failability: a version that took the first nonempty timestamp
            # (heartbeat before completed_at) would report 0.0 here instead.


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

    def test_since_prefers_actions_taken_for_a_ledger_reap_row(self) -> None:
        """A ledger `reap` row has no `decision` and its outcome is the
        action summary in `actions_taken`, not the bare event name `reap`."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            event_log = Path(tmp) / "event-log.jsonl"
            ledger.write_text(
                json.dumps(
                    {
                        "ts": time.time(),
                        "dispatch_id": "ctx_reaped",
                        "task_id": "task_reaped",
                        "event": "reap",
                        "actions_taken": "terminal_closed:term_1",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            event_log.write_text("", encoding="utf-8")

            builder = DispatchTimelineBuilder(
                orca_runner=lambda cmd: (1, "", ""), ledger_path=ledger, event_log_path=event_log
            )
            rows = builder.list_since(hours=1)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["last_outcome"], "terminal_closed:term_1")
            # Failability: a version that fell back to `entry.get("event")`
            # before `actions_taken` would report "reap" here instead.


if __name__ == "__main__":
    unittest.main()
