from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from master_runtime.core.worker_reap import (
    DispatchState,
    ReapError,
    ReapRecord,
    WorkerReaper,
)


class DispatchStateTests(unittest.TestCase):
    def test_is_settled_detects_wrapped_completed(self) -> None:
        state = DispatchState(
            _wrapped_dispatch_payload(
                status="completed",
                process_incarnation="repo::/tmp/wt-done@@proc",
            )
        )
        self.assertTrue(state.is_settled())
        self.assertEqual(state.dispatch_id, "ctx_done")
        self.assertEqual(state.task_id, "task_done")
        self.assertEqual(state.terminal_id, "term_done")
        self.assertEqual(state.worktree_path, "/tmp/wt-done")

    def test_is_settled_detects_wrapped_completed_windows_path(self) -> None:
        state = DispatchState(
            _wrapped_dispatch_payload(
                status="completed",
                process_incarnation="repo::C:\\tmp\\wt-done@@proc",
            )
        )
        self.assertTrue(state.is_settled())
        self.assertEqual(state.worktree_path, "C:\\tmp\\wt-done")

    def test_flat_shape_uses_worktree_path_fallback(self) -> None:
        state = DispatchState(
            {
                "dispatch_id": "d-flat",
                "task_id": "t-flat",
                "status": "COMPLETED",
                "process_incarnation": "not-parseable",
                "worktree_path": "/tmp/fallback-wt",
            }
        )
        self.assertEqual(state.worktree_path, "/tmp/fallback-wt")

    def test_flat_shape_rejects_relative_worktree_path_fallback(self) -> None:
        state = DispatchState(
            {
                "dispatch_id": "d-flat",
                "task_id": "t-flat",
                "status": "COMPLETED",
                "process_incarnation": "not-parseable",
                "worktree_path": "relative/wt",
            }
        )
        self.assertIsNone(state.worktree_path)

    def test_is_settled_rejects_wrapped_dispatched(self) -> None:
        state = DispatchState(_wrapped_dispatch_payload(status="dispatched"))
        self.assertFalse(state.is_settled())

    def test_is_settled_detects_accepted(self) -> None:
        state = DispatchState({"status": "ACCEPTED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_failed(self) -> None:
        state = DispatchState({"status": "FAILED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_abandoned(self) -> None:
        state = DispatchState({"status": "ABANDONED"})
        self.assertTrue(state.is_settled())

    def test_flat_shape_still_parses(self) -> None:
        state = DispatchState(
            {
                "dispatch_id": "d-flat",
                "task_id": "t-flat",
                "terminal_id": "term-flat",
                "status": "COMPLETED",
            }
        )
        self.assertEqual(state.dispatch_id, "d-flat")
        self.assertEqual(state.task_id, "t-flat")
        self.assertEqual(state.terminal_id, "term-flat")
        self.assertTrue(state.is_settled())

    def test_flat_shape_prefers_dispatch_id_over_id(self) -> None:
        state = DispatchState(
            {
                "id": "envelope-id",
                "dispatch_id": "d-flat",
                "task_id": "t-flat",
                "status": "COMPLETED",
            }
        )
        self.assertEqual(state.dispatch_id, "d-flat")

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

    def test_reap_resolves_dispatch_id_via_worker_list_snake_case(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "worker-list" in cmd:
                worker_list_payload = {
                    "result": {
                        "workers": [
                            {
                                "dispatch_id": "ctx_target",
                                "task_id": "task_target",
                            }
                        ]
                    }
                }
                return 0, json.dumps(worker_list_payload), ""
            if "dispatch-show" in cmd:
                dispatch = {
                    "dispatch_id": "ctx_target",
                    "task_id": "task_target",
                    "terminal_id": "term-target",
                    "status": "COMPLETED",
                }
                return 0, json.dumps(dispatch), ""
            if "terminal" in cmd and "close" in cmd:
                return 0, '{"ok":true}', ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(dispatch_id="ctx_target", execute=True)

        self.assertEqual(record.task_id, "task_target")
        self.assertIn(["orca", "orchestration", "dispatch-show", "--json", "--task", "task_target"], commands)

    def test_reap_resolves_dispatch_id_via_worker_list_camel_fallback(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                worker_list_payload = {
                    "result": {
                        "workers": [
                            {
                                "dispatchId": "ctx_target",
                                "taskId": "task_target",
                            }
                        ]
                    }
                }
                return 0, json.dumps(worker_list_payload), ""
            if "dispatch-show" in cmd:
                dispatch = {
                    "dispatch_id": "ctx_target",
                    "task_id": "task_target",
                    "terminal_id": "term-target",
                    "status": "COMPLETED",
                }
                return 0, json.dumps(dispatch), ""
            if "terminal" in cmd and "close" in cmd:
                return 0, '{"ok":true}', ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(dispatch_id="ctx_target", execute=True)

        self.assertEqual(record.task_id, "task_target")

    def test_reap_resolves_dispatch_id_when_snake_case_is_none(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                worker_list_payload = {
                    "result": {
                        "workers": [
                            {
                                "dispatch_id": None,
                                "dispatchId": "ctx_target",
                                "task_id": None,
                                "taskId": "task_target",
                            }
                        ]
                    }
                }
                return 0, json.dumps(worker_list_payload), ""
            if "dispatch-show" in cmd:
                dispatch = {
                    "dispatch_id": "ctx_target",
                    "task_id": "task_target",
                    "terminal_id": "term-target",
                    "status": "COMPLETED",
                }
                return 0, json.dumps(dispatch), ""
            if "terminal" in cmd and "close" in cmd:
                return 0, '{"ok":true}', ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(dispatch_id="ctx_target", execute=True)
        self.assertEqual(record.task_id, "task_target")

    def test_reap_errors_when_dispatch_id_missing_from_worker_list(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                worker_list_payload = {
                    "result": {
                        "workers": [
                            {
                                "dispatchId": "ctx_other",
                                "taskId": "task_other",
                            }
                        ]
                    }
                }
                return 0, json.dumps(worker_list_payload), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(
            ReapError,
            "Could not resolve dispatch ctx_missing: worker-list had no row for it",
        ):
            reaper.reap(dispatch_id="ctx_missing", execute=False)

    def test_reap_errors_when_dispatch_row_has_no_task_id(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                worker_list_payload = {
                    "result": {
                        "workers": [
                            {
                                "dispatchId": "ctx_target",
                            }
                        ]
                    }
                }
                return 0, json.dumps(worker_list_payload), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(
            ReapError,
            "worker-list row for dispatch ctx_target has no task_id",
        ):
            reaper.reap(dispatch_id="ctx_target", execute=False)

    def test_reap_handles_worker_list_null_result_payload(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                return 0, json.dumps({"result": None}), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(
            ReapError,
            "Could not resolve dispatch ctx_missing: worker-list had no row for it",
        ):
            reaper.reap(dispatch_id="ctx_missing", execute=False)

    def test_reap_handles_worker_list_non_list_workers_payload(self) -> None:
        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if "worker-list" in cmd:
                return 0, json.dumps({"result": {"workers": "not-a-list"}}), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(
            ReapError,
            "Could not resolve dispatch ctx_missing: worker-list had no row for it",
        ):
            reaper.reap(dispatch_id="ctx_missing", execute=False)

    def test_reap_flow_uses_wrapped_dispatch_shape_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapped_worktree = str(Path(tmp) / "wrapped-worktree")
            Path(wrapped_worktree).mkdir(parents=True, exist_ok=True)
            closed_terminals = []
            removed_paths = []

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if "dispatch-show" in cmd:
                    return 0, json.dumps(
                        _wrapped_dispatch_payload(
                            status="completed",
                            process_incarnation=f"repo::{wrapped_worktree}@@proc",
                        )
                    ), ""
                if "terminal" in cmd and "close" in cmd:
                    closed_terminals.append(cmd[-1])
                    return 0, '{"ok":true}', ""
                if "git" in cmd and "status" in cmd:
                    return 0, "", ""
                if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
                    return 0, "main\n", ""
                if "git" in cmd and "branch" in cmd and "--merged" in cmd:
                    return 0, "* main\n", ""
                if "git" in cmd and "worktree" in cmd and "remove" in cmd:
                    removed_paths.append(cmd[-1])
                    return 0, "", ""
                return 0, "", ""

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="task_done", execute=True)

            self.assertEqual(closed_terminals, ["term_done"])
            self.assertEqual(record.worktree_path, wrapped_worktree)
            self.assertIn("terminal_closed:term_done", record.actions_taken)
            self.assertIn(f"worktree_removed:{wrapped_worktree}", record.actions_taken)
            self.assertIn(wrapped_worktree, removed_paths)

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
                        "process_incarnation": f"repo::{tmp_path}@@worker",
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
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp_path,
                current_branch="main",
                merged_branches="* main\n  feature-x\n",
            )

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn(tmp_path, removed_paths)
            self.assertIn("worktree_removed:", record.actions_taken)

    def test_reap_removes_clean_squash_merged_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = tmp
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp_path,
                current_branch="feature-x",
                merged_branches="* main\n",
                origin_main_tree="tree-main",
                virtual_merge_tree="tree-main",
            )

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn(tmp_path, removed_paths)
            self.assertIn("worktree_removed:", record.actions_taken)

    def test_reap_leaves_clean_unmerged_worktree_with_unique_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = tmp
            fake_runner, _ = _clean_worktree_runner(
                tmp_path,
                current_branch="feature-x",
                merged_branches="* main\n",
                origin_main_tree="tree-main",
                virtual_merge_tree="tree-merged",
            )

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn("worktree_left:", record.actions_taken)
            self.assertIn("branch changes are not included", record.actions_taken)

    def test_squash_merge_detection_accepts_equivalent_real_git_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            (repo / "file.txt").write_text("base\n", encoding="utf-8")
            _git(repo, "add", "file.txt")
            _git(repo, "commit", "-m", "base")
            _git(repo, "checkout", "-b", "feature-x")
            (repo / "file.txt").write_text("base\nfeature\n", encoding="utf-8")
            _git(repo, "commit", "-am", "feature")
            _git(repo, "checkout", "main")
            (repo / "file.txt").write_text("base\nfeature\n", encoding="utf-8")
            _git(repo, "commit", "-am", "squash feature")
            _git(repo, "update-ref", "refs/remotes/origin/main", "main")
            _git(repo, "checkout", "feature-x")

            clean, merged, reason = WorkerReaper()._check_worktree_safe_to_remove(repo)

            self.assertTrue(clean)
            self.assertTrue(merged)
            self.assertEqual(reason, "")

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


def _clean_worktree_runner(
    worktree_path: str,
    *,
    current_branch: str,
    merged_branches: str,
    origin_main_tree: str | None = None,
    virtual_merge_tree: str | None = None,
) -> tuple[Callable[[list[str]], tuple[int, str, str]], list[str]]:
    removed_paths = []

    def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
        if "dispatch-show" in cmd:
            dispatch = {
                "dispatch_id": "d1",
                "task_id": "t1",
                "terminal_id": "term1",
                "status": "COMPLETED",
                "process_incarnation": f"repo::{worktree_path}@@worker",
            }
            return 0, json.dumps(dispatch), ""
        if "git" in cmd and "status" in cmd:
            return 0, "", ""
        if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
            return 0, f"{current_branch}\n", ""
        if "git" in cmd and "branch" in cmd and "--merged" in cmd:
            return 0, merged_branches, ""
        if "git" in cmd and "rev-parse" in cmd and origin_main_tree is not None:
            return 0, f"{origin_main_tree}\n", ""
        if "git" in cmd and "merge-tree" in cmd and virtual_merge_tree is not None:
            return 0, f"{virtual_merge_tree}\n", ""
        if "git" in cmd and "worktree" in cmd and "remove" in cmd:
            removed_paths.append(cmd[-1])
            return 0, "", ""
        if "terminal" in cmd and "close" in cmd:
            return 0, "", ""
        return 0, "", ""

    return fake_runner, removed_paths


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def _wrapped_dispatch_payload(
    *,
    status: str,
    process_incarnation: str = "repo::/tmp/wt-done@@proc",
) -> dict[str, object]:
    return {
        "id": "local",
        "ok": True,
        "result": {
            "dispatch": {
                "assignee_handle": "term_done",
                "assignee_pane_key": "pane_done",
                "capability_hash": "cap_done",
                "capability_revoked_at": None,
                "completed_at": "2026-09-14T00:00:00Z",
                "consumer_generation": 1,
                "contract_version": "v1",
                "created_at": "2026-09-14T00:00:00Z",
                "creator_dispatch_id": "ctx_parent",
                "creator_handle": "term_parent",
                "creator_pane_key": "pane_parent",
                "depth": 1,
                "dispatched_at": "2026-09-14T00:00:00Z",
                "failure_count": 0,
                "host_scope": "local",
                "id": "ctx_done",
                "last_failure": None,
                "last_heartbeat_at": "2026-09-14T00:00:00Z",
                "launch_token_hash": "tok_done",
                "process_incarnation": process_incarnation,
                "retry_of_dispatch_id": None,
                "run_id": "run_done",
                "status": status,
                "task_id": "task_done",
                "termination_reason": None,
            }
        },
        "_meta": {
            "runtimeId": "rt_done",
        },
    }
