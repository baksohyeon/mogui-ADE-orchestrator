from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.worker_reap import (
    DispatchState,
    ReapError,
    ReapRecord,
    WorkerReaper,
)


class DispatchStateTests(unittest.TestCase):
    def test_is_settled_detects_completed(self) -> None:
        state = DispatchState({"status": "COMPLETED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_accepted(self) -> None:
        state = DispatchState({"status": "ACCEPTED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_failed(self) -> None:
        state = DispatchState({"status": "FAILED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_abandoned(self) -> None:
        state = DispatchState({"status": "ABANDONED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_rejects_running(self) -> None:
        state = DispatchState({"status": "RUNNING"})
        self.assertFalse(state.is_settled())

    def test_is_settled_rejects_registered(self) -> None:
        state = DispatchState({"status": "REGISTERED"})
        self.assertFalse(state.is_settled())

    def test_is_success_detects_completed(self) -> None:
        state = DispatchState({"status": "COMPLETED"})
        self.assertTrue(state.is_success())

    def test_is_success_detects_accepted(self) -> None:
        state = DispatchState({"status": "ACCEPTED"})
        self.assertTrue(state.is_success())

    def test_is_success_rejects_failed(self) -> None:
        state = DispatchState({"status": "FAILED"})
        self.assertFalse(state.is_success())


class ReapRecordTests(unittest.TestCase):
    def test_to_dict_round_trips(self) -> None:
        original = ReapRecord(
            task_id="task-1",
            dispatch_id="dispatch-1",
            terminal_id="term-1",
            worktree_path="/path/to/wt",
            actions_taken="terminal_closed:term-1;worktree_removed:/path",
            timestamp=123.456,
        )
        data = original.to_dict()
        self.assertEqual(data["task_id"], "task-1")
        self.assertEqual(data["dispatch_id"], "dispatch-1")
        self.assertEqual(data["actions_taken"], "terminal_closed:term-1;worktree_removed:/path")


class WorkerReaperTests(unittest.TestCase):
    def test_reap_rejects_missing_both_ids(self) -> None:
        reaper = WorkerReaper(orca_runner=_FakeRunner())
        with self.assertRaisesRegex(ReapError, "Either task_id or dispatch_id"):
            reaper.reap(execute=False)

    def test_reap_rejects_open_dispatch(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "dispatch-show" in cmd:
                dispatch = {
                    "dispatch_id": "d1",
                    "task_id": "t1",
                    "terminal_id": "term1",
                    "status": "RUNNING",
                }
                return 0, json.dumps(dispatch), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(ReapError, "not settled"):
            reaper.reap(task_id="t1", execute=False)

    def test_reap_closes_terminal_when_settled(self) -> None:
        closed_terminals = []

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "dispatch-show" in cmd:
                dispatch = {
                    "dispatch_id": "d1",
                    "task_id": "t1",
                    "terminal_id": "term1",
                    "status": "COMPLETED",
                }
                return 0, json.dumps(dispatch), ""
            if "terminal" in cmd and "close" in cmd:
                closed_terminals.append(cmd[-1])
                return 0, '{"ok":true}', ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertIn("term1", closed_terminals)
        self.assertIn("terminal_closed:term1", record.actions_taken)

    def test_reap_leaves_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = tmp

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    dispatch = {
                        "dispatch_id": "d1",
                        "task_id": "t1",
                        "terminal_id": "term1",
                        "status": "COMPLETED",
                        "worktree_path": tmp_path,
                    }
                    return 0, json.dumps(dispatch), ""
                # git status shows dirty
                if "git" in cmd and "status" in cmd:
                    return 0, "M file.txt\n", ""
                if "terminal" in cmd and "close" in cmd:
                    return 0, '{"ok":true}', ""
                return 0, "", ""

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn("worktree_left:", record.actions_taken)

    def test_reap_removes_clean_merged_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = tmp
            removed_paths = []

            def fake_runner(cmd):
                if "dispatch-show" in cmd:
                    dispatch = {
                        "dispatch_id": "d1",
                        "task_id": "t1",
                        "terminal_id": "term1",
                        "status": "COMPLETED",
                        "worktree_path": tmp_path,
                    }
                    return 0, json.dumps(dispatch), ""
                if "git" in cmd and "status" in cmd:
                    return 0, "", ""
                if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
                    return 0, "main\n", ""
                if "git" in cmd and "branch" in cmd and "--merged" in cmd:
                    return 0, "* main\n  feature-x\n", ""
                if "git" in cmd and "worktree" in cmd and "remove" in cmd:
                    removed_paths.append(cmd[-1])
                    return 0, "", ""
                if "terminal" in cmd and "close" in cmd:
                    return 0, "", ""
                return 0, "", ""

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn(tmp_path, removed_paths)
            self.assertIn("worktree_removed:", record.actions_taken)

    def test_reap_appends_to_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "reap.jsonl"

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    dispatch = {
                        "dispatch_id": "d1",
                        "task_id": "t1",
                        "terminal_id": "term1",
                        "status": "COMPLETED",
                    }
                    return 0, json.dumps(dispatch), ""
                if "terminal" in cmd and "close" in cmd:
                    return 0, '{"ok":true}', ""
                return 0, "", ""

            reaper = WorkerReaper(
                orca_runner=fake_runner,
                reap_ledger_path=ledger_path,
            )
            reaper.reap(task_id="t1", execute=True)

            self.assertTrue(ledger_path.exists())
            lines = ledger_path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)

            entry = json.loads(lines[0])
            self.assertEqual(entry["event"], "reap")
            self.assertEqual(entry["task_id"], "t1")
            self.assertEqual(entry["dispatch_id"], "d1")


class _FakeRunner:
    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        return 0, "", ""
