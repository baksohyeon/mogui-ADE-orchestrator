from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from master_runtime.core.worker_reap import (
    AGENT_CLI_COMMANDS,
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
        state = DispatchState({"dispatch_id": "d-accepted", "status": "ACCEPTED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_failed(self) -> None:
        state = DispatchState({"dispatch_id": "d-failed", "status": "FAILED"})
        self.assertTrue(state.is_settled())

    def test_is_settled_detects_abandoned(self) -> None:
        state = DispatchState({"dispatch_id": "d-abandoned", "status": "ABANDONED"})
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
        state = DispatchState({"dispatch_id": "d-completed", "status": "COMPLETED"})
        self.assertTrue(state.is_success())

    def test_is_success_detects_accepted(self) -> None:
        state = DispatchState({"dispatch_id": "d-accepted", "status": "ACCEPTED"})
        self.assertTrue(state.is_success())

    def test_is_success_rejects_failed(self) -> None:
        state = DispatchState({"dispatch_id": "d-failed", "status": "FAILED"})
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


class _MeasuredEnvironment:
    """A fake `orca_runner` covering every measurement `reap()` now takes,
    defaulted to the happy path (settled dispatch, pane present, not reused,
    no agent process, clean+merged worktree) so each test flips exactly one
    measurement rather than re-describing the whole environment.
    """

    def __init__(
        self,
        *,
        dispatch_id: str = "d1",
        task_id: str = "t1",
        terminal_id: str = "term1",
        status: str = "COMPLETED",
        worktree_path: str | None = None,
        terminal_present: bool | None = True,
        terminal_list_fails: bool = False,
        reused_by: str | None = None,
        worker_list_fails: bool = False,
        agent_pid: str | None = None,
        agent_comm: str | None = None,
        ps_fails: bool = False,
    ) -> None:
        self.dispatch_id = dispatch_id
        self.task_id = task_id
        self.terminal_id = terminal_id
        self.status = status
        self.worktree_path = worktree_path
        self.terminal_present = terminal_present
        self.terminal_list_fails = terminal_list_fails
        self.reused_by = reused_by
        self.worker_list_fails = worker_list_fails
        self.agent_pid = agent_pid
        self.agent_comm = agent_comm
        self.ps_fails = ps_fails
        self.closed_terminals: list[str] = []
        self.removed_worktrees: list[str] = []
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        self.commands.append(cmd)

        if "dispatch-show" in cmd:
            dispatch: dict[str, object] = {
                "dispatch_id": self.dispatch_id,
                "task_id": self.task_id,
                "terminal_id": self.terminal_id,
                "status": self.status,
            }
            if self.worktree_path:
                dispatch["worktree_path"] = self.worktree_path
            return 0, json.dumps(dispatch), ""

        if cmd[:3] == ["orca", "terminal", "list"]:
            if self.terminal_list_fails:
                return 1, "", "orca unreachable"
            handles = [self.terminal_id] if self.terminal_present else []
            payload = {"result": {"terminals": [{"handle": h} for h in handles]}}
            return 0, json.dumps(payload), ""

        if cmd[:3] == ["orca", "orchestration", "worker-list"]:
            if self.worker_list_fails:
                return 1, "", "orca unreachable"
            workers = []
            if self.reused_by:
                workers.append(
                    {
                        "agentTerminalHandle": self.terminal_id,
                        "dispatchStatus": "dispatched",
                        "dispatchId": self.reused_by,
                    }
                )
            payload = {"result": {"workers": workers, "page": {"hasMore": False}}}
            return 0, json.dumps(payload), ""

        if cmd[:2] == ["ps", "-axo"]:
            if self.ps_fails:
                return 1, "", "ps unavailable"
            if self.agent_pid:
                return 0, f"{self.agent_pid} {self.agent_comm}\n", ""
            return 0, "", ""

        if cmd[:2] == ["lsof", "-a"] and self.agent_pid:
            return 0, f"p{self.agent_pid}\nfcwd\nn{self.worktree_path}\n", ""

        if cmd[:2] == ["orca", "terminal"] and "close" in cmd:
            self.closed_terminals.append(cmd[-1])
            return 0, '{"ok":true}', ""

        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, "[]", ""

        # Worktree cleanliness/merge scenarios (dirty, non-main branch, not
        # yet merged) are covered by the dedicated _clean_worktree_runner
        # fake below, not by this one: every _MeasuredEnvironment call site
        # only needs the worktree checks to clear, never to flip, so this
        # always reports a clean, merged main branch.
        if "git" in cmd and "status" in cmd:
            return 0, "", ""
        if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
            return 0, "main\n", ""
        if "git" in cmd and cmd[3:5] == ["rev-parse", "HEAD"]:
            return 0, "tip\n", ""
        if "git" in cmd and "--git-common-dir" in cmd:
            return 0, "/repo/.git\n", ""
        if "git" in cmd and cmd[3:] == ["remote", "get-url", "origin"]:
            return 0, "https://github.com/example/worker-reap.git\n", ""
        if "git" in cmd and "branch" in cmd and "--merged" in cmd:
            return 0, "* main\n", ""
        if "git" in cmd and "worktree" in cmd and "remove" in cmd:
            self.removed_worktrees.append(cmd[-1])
            return 0, "", ""

        return 0, "", ""


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

    def test_reap_closes_terminal_when_all_three_measurements_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _MeasuredEnvironment(worktree_path=tmp)
            reaper = WorkerReaper(orca_runner=env)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn("term1", env.closed_terminals)
            self.assertIn(
                ["orca", "terminal", "close", "--terminal", "term1"], env.commands
            )
            self.assertIn("terminal_closed:term1", record.actions_taken)
            self.assertEqual(record.measurements["terminal_present"], True)
            self.assertEqual(record.measurements["terminal_reused_by"], "")
            self.assertEqual(record.measurements["agent_process"], "")

    def test_reap_leaves_pane_absent_from_terminal_list(self) -> None:
        env = _MeasuredEnvironment(terminal_present=False)
        reaper = WorkerReaper(orca_runner=env)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertEqual(env.closed_terminals, [])
        self.assertIn("terminal_left:term1:pane_absent", record.actions_taken)
        self.assertEqual(record.measurements["terminal_present"], False)
        # Failability: a version that skipped the presence check would still
        # attempt the close below, so closed_terminals would be non-empty.

    def test_reap_leaves_pane_whose_presence_is_unmeasured(self) -> None:
        env = _MeasuredEnvironment(terminal_list_fails=True)
        reaper = WorkerReaper(orca_runner=env)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertEqual(env.closed_terminals, [])
        self.assertIn("terminal_left:term1:presence_unmeasured", record.actions_taken)
        self.assertIsNone(record.measurements["terminal_present"])
        # Failability: a version that treated a failed `terminal list` call as
        # "absent" (or worse, "present") rather than refusing would either
        # report pane_absent here or proceed to close the terminal.

    def test_reap_leaves_pane_reused_by_a_dispatched_dispatch(self) -> None:
        env = _MeasuredEnvironment(reused_by="ctx_newer")
        reaper = WorkerReaper(orca_runner=env)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertEqual(env.closed_terminals, [])
        self.assertIn("terminal_left:term1:reused_by:ctx_newer", record.actions_taken)
        self.assertEqual(record.measurements["terminal_reused_by"], "ctx_newer")
        # Failability: a version that closed the pane here would kill the
        # live worker the newer, still-`dispatched` dispatch is using.

    def test_reap_leaves_pane_whose_reuse_is_unmeasured(self) -> None:
        env = _MeasuredEnvironment(worker_list_fails=True)
        reaper = WorkerReaper(orca_runner=env)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertEqual(env.closed_terminals, [])
        self.assertIn("terminal_left:term1:reuse_unmeasured", record.actions_taken)
        self.assertIsNone(record.measurements["terminal_reused_by"])

    def test_reap_leaves_pane_when_worker_list_pagination_cannot_finish(self) -> None:
        """`hasMore: true` with no `nextCursor` is a stuck page: the pagination
        loop must refuse (None), not stop and treat what it has as complete."""

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if cmd[:3] == ["orca", "orchestration", "worker-list"]:
                payload = {"result": {"workers": [], "page": {"hasMore": True}}}
                return 0, json.dumps(payload), ""
            return _MeasuredEnvironment()(cmd)

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertIn("terminal_left:term1:reuse_unmeasured", record.actions_taken)
        self.assertIsNone(record.measurements["terminal_reused_by"])
        # Failability: a version that broke out of the loop whenever
        # `nextCursor` was missing would treat this stuck page as the last
        # page and return the (incomplete) rows collected so far.

    def test_reap_leaves_pane_when_worker_list_shape_is_malformed(self) -> None:
        """A worker row that isn't an object is unmeasurable, not "no reuse"."""

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if cmd[:3] == ["orca", "orchestration", "worker-list"]:
                payload = {"result": {"workers": ["not-a-dict"]}}
                return 0, json.dumps(payload), ""
            return _MeasuredEnvironment()(cmd)

        reaper = WorkerReaper(orca_runner=fake_runner)
        record = reaper.reap(task_id="t1", execute=True)

        self.assertIn("terminal_left:term1:reuse_unmeasured", record.actions_taken)
        self.assertIsNone(record.measurements["terminal_reused_by"])

    def test_all_worker_list_rows_joins_every_page(self) -> None:
        pages = {
            None: {
                "result": {
                    "workers": [{"dispatch_id": "a"}],
                    "page": {"hasMore": True, "nextCursor": "c2"},
                }
            },
            "c2": {
                "result": {
                    "workers": [{"dispatch_id": "b"}],
                    "page": {"hasMore": False},
                }
            },
        }

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            cursor = cmd[cmd.index("--cursor") + 1] if "--cursor" in cmd else None
            return 0, json.dumps(pages[cursor]), ""

        rows = WorkerReaper(orca_runner=fake_runner)._all_worker_list_rows()
        self.assertEqual(rows, [{"dispatch_id": "a"}, {"dispatch_id": "b"}])

    def test_reap_leaves_pane_with_an_agent_process_in_the_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _MeasuredEnvironment(
                worktree_path=tmp,
                agent_pid="4242",
                agent_comm="claude",
            )
            reaper = WorkerReaper(orca_runner=env)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(env.closed_terminals, [])
            self.assertIn(
                "terminal_left:term1:agent_process:4242:claude", record.actions_taken
            )
            self.assertEqual(record.measurements["agent_process"], "4242:claude")
            # Failability: a version that ignored the process scan would close
            # a pane that still has a live agent CLI sitting in its worktree.

    def test_reap_leaves_pane_with_every_agent_cli_command_in_the_worktree(
        self,
    ) -> None:
        """Every name in AGENT_CLI_COMMANDS is actually matched by the scan,
        not just the ones exercised elsewhere (e.g. `cursor-agent`)."""
        for comm in sorted(AGENT_CLI_COMMANDS):
            with self.subTest(comm=comm):
                with tempfile.TemporaryDirectory() as tmp:
                    env = _MeasuredEnvironment(
                        worktree_path=tmp,
                        agent_pid="4242",
                        agent_comm=comm,
                    )
                    reaper = WorkerReaper(orca_runner=env)
                    record = reaper.reap(task_id="t1", execute=True)

                    self.assertEqual(env.closed_terminals, [])
                    self.assertEqual(
                        record.measurements["agent_process"], f"4242:{comm}"
                    )

    def test_reap_leaves_pane_whose_agent_process_scan_is_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _MeasuredEnvironment(worktree_path=tmp, ps_fails=True)
            reaper = WorkerReaper(orca_runner=env)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(env.closed_terminals, [])
            self.assertIn(
                "terminal_left:term1:agent_process_unmeasured", record.actions_taken
            )
            self.assertIsNone(record.measurements["agent_process"])

    def test_reap_leaves_pane_when_matching_process_cwd_cannot_be_resolved(
        self,
    ) -> None:
        """A process whose comm matches an agent CLI but whose cwd cannot be
        read (both `lsof` and `/proc/<pid>/cwd` fail) must refuse, not clear —
        the scan must not silently skip it and return "" as if no agent were
        present."""
        with tempfile.TemporaryDirectory() as tmp:
            env = _MeasuredEnvironment(worktree_path=tmp, agent_pid="4242", agent_comm="claude")

            def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
                if cmd[:2] == ["lsof", "-a"]:
                    return 1, "", "lsof: permission denied"
                if cmd[:1] == ["readlink"]:
                    return 1, "", "readlink: No such file or directory"
                return env(cmd)

            reaper = WorkerReaper(orca_runner=fake_runner)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(env.closed_terminals, [])
            self.assertIn(
                "terminal_left:term1:agent_process_unmeasured", record.actions_taken
            )
            self.assertIsNone(record.measurements["agent_process"])
            # Failability: a version that `continue`s past an unresolved cwd
            # and falls through to `return ""` would close this pane while an
            # agent CLI process may still be sitting in the worktree.

    def test_reap_dry_run_never_prints_terminal_closed(self) -> None:
        env = _MeasuredEnvironment(worktree_path="/tmp/wt-happy-path")
        reaper = WorkerReaper(orca_runner=env)
        record = reaper.reap(task_id="t1", execute=False)

        self.assertEqual(env.closed_terminals, [])
        self.assertNotIn("terminal_closed", record.actions_taken)
        self.assertIn("would_close_terminal:term1", record.actions_taken)
        # Failability: a version whose dry-run path still called
        # `_close_terminal` (or hardcoded the `terminal_closed:` action label
        # regardless of `execute`) would fail either assertion above.

    def test_reap_dry_run_worktree_shape_says_would_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _MeasuredEnvironment(worktree_path=tmp)
            reaper = WorkerReaper(orca_runner=env)
            record = reaper.reap(task_id="t1", execute=False)

            self.assertEqual(env.removed_worktrees, [])
            self.assertNotIn("worktree_removed", record.actions_taken)
            self.assertIn(f"would_remove_worktree:{tmp}", record.actions_taken)
            self.assertEqual(record.measurements["worktree_clean"], True)
            self.assertEqual(record.measurements["worktree_merged"], True)

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

    def test_reap_errors_when_dispatch_show_returns_wrapped_null_dispatch(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "dispatch-show" in cmd:
                return 0, json.dumps(
                    {
                        "id": "0739e4b9-eb0b-4a0a-a2d3-eb3997d30288",
                        "ok": True,
                        "result": {"dispatch": None},
                        "_meta": {"runtimeId": "rt-null"},
                    }
                ), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(ReapError, "no such task: task_0000deadbeef") as ctx:
            reaper.reap(task_id="task_0000deadbeef", execute=True)

        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertFalse(any("terminal" in cmd and "close" in cmd for cmd in commands))
        self.assertFalse(any("git" in cmd and "worktree" in cmd and "remove" in cmd for cmd in commands))

    def test_reap_errors_when_dispatch_show_result_omits_dispatch_key(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "dispatch-show" in cmd:
                return 0, json.dumps(
                    {
                        "id": "0739e4b9-eb0b-4a0a-a2d3-eb3997d30288",
                        "ok": True,
                        "result": {},
                        "_meta": {"runtimeId": "rt-null"},
                    }
                ), ""
            return 0, "", ""

        reaper = WorkerReaper(orca_runner=fake_runner)
        with self.assertRaisesRegex(ReapError, "no such task: task_0000deadbeef") as ctx:
            reaper.reap(task_id="task_0000deadbeef", execute=True)

        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertFalse(any("terminal" in cmd and "close" in cmd for cmd in commands))
        self.assertFalse(any("git" in cmd and "worktree" in cmd and "remove" in cmd for cmd in commands))

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
                if cmd[:3] == ["orca", "terminal", "list"]:
                    payload = {"result": {"terminals": [{"handle": "term_done"}]}}
                    return 0, json.dumps(payload), ""
                if cmd[:3] == ["orca", "orchestration", "worker-list"]:
                    payload = {"result": {"workers": [], "page": {"hasMore": False}}}
                    return 0, json.dumps(payload), ""
                if cmd[:2] == ["ps", "-axo"]:
                    return 0, "", ""
                if "terminal" in cmd and "close" in cmd:
                    closed_terminals.append(cmd[-1])
                    return 0, '{"ok":true}', ""
                if cmd[:3] == ["gh", "pr", "list"]:
                    return 0, "[]", ""
                if "git" in cmd and "status" in cmd:
                    return 0, "", ""
                if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
                    return 0, "main\n", ""
                if "git" in cmd and cmd[3:5] == ["rev-parse", "HEAD"]:
                    return 0, "tip\n", ""
                if "git" in cmd and "--git-common-dir" in cmd:
                    return 0, f"{FAKE_GIT_COMMON_DIR}\n", ""
                if "git" in cmd and cmd[3:] == ["remote", "get-url", "origin"]:
                    return 0, "https://github.com/example/worker-reap.git\n", ""
                if "git" in cmd and "branch" in cmd and "--merged" in cmd:
                    return 0, "* main\n", ""
                if "git" in cmd and "rev-parse" in cmd and "--git-common-dir" in cmd:
                    return 0, f"{FAKE_GIT_COMMON_DIR}\n", ""
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

    def test_pycache_litter_alone_does_not_count_as_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, _removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_pycache_litter(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd:
                    return 0, "?? __pycache__/stray.pyc\n", ""
                return original_runner(cmd)

            clean, merged, reason = WorkerReaper(
                orca_runner=runner_with_pycache_litter
            )._check_worktree_safe_to_remove(Path(tmp))

            self.assertTrue(clean)
            self.assertTrue(merged)
            self.assertEqual(reason, "")
            # Failability: a version that dropped the __pycache__/ filter would
            # read this porcelain line as an uncommitted change and refuse.

    def test_tracked_pycache_change_still_counts_as_dirty(self) -> None:
        """The pycache exemption is for untracked litter only — a tracked
        change under a __pycache__ path (however that happened) must still
        block removal, never be waved through as litter."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, _removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_tracked_pycache_change(
                cmd: list[str],
            ) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd:
                    return 0, " M __pycache__/tracked.pyc\n", ""
                return original_runner(cmd)

            clean, merged, reason = WorkerReaper(
                orca_runner=runner_with_tracked_pycache_change
            )._check_worktree_safe_to_remove(Path(tmp))

            self.assertFalse(clean)
            self.assertFalse(merged)
            self.assertEqual(reason, "Worktree has uncommitted changes")
            # Failability: a version that exempted any line mentioning
            # __pycache__/ (tracked or not) would call this clean and let the
            # reaper remove a worktree with a real uncommitted change in it.

    def test_real_pycache_only_worktree_is_still_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            (repo / "file.txt").write_text("base\n", encoding="utf-8")
            _git(repo, "add", "file.txt")
            _git(repo, "commit", "-m", "base")
            _git(repo, "update-ref", "refs/remotes/origin/main", "main")
            # A directory untracked in its entirety collapses to one porcelain
            # line for the directory itself (`?? __pycache__/`), not its
            # contents — so it must sit at a level git won't fold into an
            # already-untracked parent, matching how it appears in practice.
            (repo / "__pycache__").mkdir()
            (repo / "__pycache__" / "a.pyc").write_text("junk", encoding="utf-8")

            clean, merged, reason = WorkerReaper()._check_worktree_safe_to_remove(repo)

            self.assertTrue(clean)
            self.assertTrue(merged)
            self.assertEqual(reason, "")

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

    def test_legacy_pr_state_is_not_measured_for_ancestry_reclaim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )

            def runner_with_unavailable_gh(cmd: list[str]) -> tuple[int, str, str]:
                if cmd[:3] == ["gh", "pr", "list"]:
                    return 1, "", "gh unavailable"
                return fake_runner(cmd)

            record = WorkerReaper(orca_runner=runner_with_unavailable_gh).reap(
                task_id="t1", execute=True
            )

            self.assertEqual(
                {key for key in record.measurements if key.startswith("worktree_pr_")},
                set(),
            )
            self.assertIn("worktree_removed:", record.actions_taken)
            self.assertIn(tmp, removed_paths)

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

    def test_reaper_resets_landing_rule_between_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            first.mkdir()
            second.mkdir()

            def runner(cmd: list[str]) -> tuple[int, str, str]:
                path = str(cmd[2]) if len(cmd) > 2 and cmd[:2] == ["git", "-C"] else ""
                if "status" in cmd:
                    return 0, "", ""
                if "remote" in cmd and "get-url" in cmd:
                    return 0, "https://github.com/example/worker-reap.git\n", ""
                if cmd[:3] == ["gh", "repo", "view"]:
                    return 0, json.dumps({"defaultBranchRef": {"name": "main"}}), ""
                if "branch" in cmd and "--show-current" in cmd:
                    return 0, ("main\n" if path == str(first) else "feature-x\n"), ""
                if "branch" in cmd and "--merged" in cmd:
                    return 0, "* main\n", ""
                if "merge-base" in cmd:
                    return 0, "base\n", ""
                if "--name-only" in cmd:
                    return 0, "src/worker.py\0", ""
                if "--quiet" in cmd:
                    return (0 if path == str(first) else 1), "", ""
                return 0, "", ""

            reaper = WorkerReaper(orca_runner=runner)
            first_result = reaper._check_worktree_safe_to_remove(first)
            second_result = reaper._check_worktree_safe_to_remove(second)

            self.assertEqual(first_result[:2], (True, True))
            self.assertEqual(second_result[:2], (False, False))
            self.assertIsNone(reaper._last_landing_rule)

    def test_reap_removes_the_worktree_through_its_git_dir_from_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = tmp
            commands = []
            fake_runner, _removed_paths = _clean_worktree_runner(
                tmp_path,
                current_branch="main",
                merged_branches="* main\n",
            )

            def recording_runner(cmd: list[str]) -> tuple[int, str, str]:
                commands.append(cmd)
                return fake_runner(cmd)

            reaper = WorkerReaper(orca_runner=recording_runner)
            reaper.reap(task_id="t1", execute=True)

            common_dir_commands = [cmd for cmd in commands if "--git-common-dir" in cmd]
            self.assertEqual(
                common_dir_commands,
                [
                    [
                        "git",
                        "-C",
                        tmp_path,
                        "rev-parse",
                        "--git-common-dir",
                    ]
                ],
            )
            remove_commands = [
                cmd for cmd in commands
                if "git" in cmd and "worktree" in cmd and "remove" in cmd
            ]
            self.assertEqual(len(remove_commands), 1)
            remove_command = remove_commands[0]
            self.assertTrue(remove_command[1].startswith("--git-dir="))
            # FAKE_GIT_COMMON_DIR is a POSIX literal; os.path.abspath joins it
            # onto tmp_path the same way the code does, so the expectation
            # lands on whatever separator this platform actually produces.
            expected_git_dir = os.path.abspath(
                os.path.join(tmp_path, FAKE_GIT_COMMON_DIR)
            )
            self.assertEqual(
                os.path.normcase(os.path.normpath(remove_command[1][len("--git-dir="):])),
                os.path.normcase(os.path.normpath(expected_git_dir)),
            )
            self.assertEqual(remove_command[2:], ["worktree", "remove", tmp_path])
            self.assertNotIn("-C", remove_command)

    def test_remove_worktree_raises_when_the_git_dir_cannot_be_resolved(self) -> None:
        commands = []

        def failing_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "--git-common-dir" in cmd:
                return 128, "", "fatal: not a git repository"
            return 0, "", ""

        with self.assertRaises(ReapError):
            WorkerReaper(orca_runner=failing_runner)._remove_worktree(Path("/tmp/wt"))
        self.assertFalse(any("remove" in cmd for cmd in commands))

    def test_remove_worktree_raises_when_the_git_dir_resolves_to_an_empty_path(self) -> None:
        commands = []

        def empty_path_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "--git-common-dir" in cmd:
                return 0, "\n", ""
            return 0, "", ""

        with self.assertRaises(ReapError):
            WorkerReaper(orca_runner=empty_path_runner)._remove_worktree(Path("/tmp/wt"))
        self.assertFalse(any("remove" in cmd for cmd in commands))

    def test_remove_worktree_resolves_a_relative_git_common_dir(self) -> None:
        commands = []
        worktree_path = os.path.join("/repo", "worktrees", "wt")
        relative_common_dir = os.path.join(".git", "worktrees", "wt")

        def relative_path_runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            if "--git-common-dir" in cmd:
                return 0, f"{relative_common_dir}\n", ""
            return 0, "", ""

        WorkerReaper(orca_runner=relative_path_runner)._remove_worktree(
            Path(worktree_path)
        )

        remove_commands = [
            cmd for cmd in commands
            if "git" in cmd and "worktree" in cmd and "remove" in cmd
        ]
        self.assertEqual(len(remove_commands), 1)
        remove_command = remove_commands[0]
        self.assertTrue(remove_command[1].startswith("--git-dir="))
        # The code joins str(Path(worktree_path)) (platform-normalized), not
        # the raw worktree_path string, so build the expectation the same way
        # and normalize both sides before comparing.
        expected_common_dir = os.path.abspath(
            os.path.join(str(Path(worktree_path)), relative_common_dir)
        )
        self.assertEqual(
            os.path.normcase(os.path.normpath(remove_command[1][len("--git-dir="):])),
            os.path.normcase(os.path.normpath(expected_common_dir)),
        )
        self.assertEqual(remove_command[0], "git")
        self.assertEqual(remove_command[2], "worktree")
        self.assertEqual(remove_command[3], "remove")
        self.assertEqual(
            os.path.normcase(os.path.normpath(remove_command[4])),
            os.path.normcase(os.path.normpath(worktree_path)),
        )

    def test_remove_worktree_works_from_a_non_repository_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            worktree = Path(tmp) / "wt"
            outside = Path(tmp) / "outside"
            repo.mkdir()
            outside.mkdir()
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            _git(repo, "commit", "--allow-empty", "-m", "base")
            _git(repo, "worktree", "add", "-b", "feature-x", str(worktree))

            previous_cwd = os.getcwd()
            os.chdir(outside)
            try:
                WorkerReaper()._remove_worktree(worktree)
            finally:
                os.chdir(previous_cwd)

            self.assertFalse(worktree.exists())
            self.assertNotIn(str(worktree.resolve()), _git(repo, "worktree", "list"))

    def test_remove_worktree_ignores_inherited_git_repository_env_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            other_repo = Path(tmp) / "other-repo"
            worktree = Path(tmp) / "wt"
            repo.mkdir()
            other_repo.mkdir()
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            _git(repo, "commit", "--allow-empty", "-m", "base")
            _git(repo, "worktree", "add", "-b", "feature-x", str(worktree))
            _git(other_repo, "init", "--initial-branch", "main")

            # A caller whose own process has these set (another repo's -C,
            # or a shell left over from one) must not steer the reaper onto
            # that repo instead of the worktree it was told to remove.
            inherited_env = {
                "GIT_DIR": str(other_repo / ".git"),
                "GIT_WORK_TREE": str(other_repo),
                "GIT_COMMON_DIR": str(other_repo / ".git"),
            }
            previous_values = {key: os.environ.get(key) for key in inherited_env}
            os.environ.update(inherited_env)
            try:
                WorkerReaper()._remove_worktree(worktree)
            finally:
                for key, previous in previous_values.items():
                    if previous is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = previous

            self.assertFalse(worktree.exists())
            self.assertNotIn(str(worktree.resolve()), _git(repo, "worktree", "list"))

    def test_run_subprocess_strips_git_index_and_object_env_vars(self) -> None:
        # An inherited index or object-store path would make a git call
        # read/write the caller's repository state instead of the one named
        # by -C, the same hazard GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR cover.
        inherited_env = {
            "GIT_INDEX_FILE": "/tmp/other-repo/.git/index",
            "GIT_OBJECT_DIRECTORY": "/tmp/other-repo/.git/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/other-repo/.git/objects-alt",
        }
        previous_values = {key: os.environ.get(key) for key in inherited_env}
        os.environ.update(inherited_env)
        captured_env: dict[str, str] = {}

        def fake_run(command, **kwargs):
            # Strict key access: a call that silently drops `env=` must fail
            # this test, not pass it vacuously against an empty dict.
            captured_env.update(kwargs["env"])
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        try:
            with mock.patch("master_runtime.core.worker_reap.subprocess.run", fake_run):
                WorkerReaper()._run_subprocess(["git", "status"])
        finally:
            for key, previous in previous_values.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous

        for key in inherited_env:
            self.assertNotIn(key, captured_env)

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

    def test_squash_merge_detection_does_not_quote_non_ascii_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            path = repo / "한글.md"
            path.write_text("base\n", encoding="utf-8")
            _git(repo, "add", "한글.md")
            _git(repo, "commit", "-m", "base")
            _git(repo, "checkout", "-b", "feature-x")
            path.write_text("feature\n", encoding="utf-8")
            _git(repo, "commit", "-am", "feature")
            _git(repo, "checkout", "main")
            _git(repo, "update-ref", "refs/remotes/origin/main", "main")
            _git(repo, "checkout", "feature-x")

            clean, merged, reason = WorkerReaper()._check_worktree_safe_to_remove(repo)

            self.assertFalse(clean)
            self.assertFalse(merged)
            self.assertIn("differing paths: 한글.md", reason)
            # Mutant proof: newline parsing of Git's quoted name reports a
            # pathspec that matches nothing and falsely returns landed.

    def test_squash_merge_detection_disables_rename_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "--initial-branch", "main")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            (repo / "old.txt").write_text(
                "line one\nline two\nline three\nline four\nline five\n",
                encoding="utf-8",
            )
            _git(repo, "add", "old.txt")
            _git(repo, "commit", "-m", "base")
            _git(repo, "checkout", "-b", "feature-x")
            _git(repo, "mv", "old.txt", "new.txt")
            (repo / "new.txt").write_text(
                "line one\nline two\nline three\nline four\nfeature\n",
                encoding="utf-8",
            )
            _git(repo, "commit", "-am", "feature rename")
            _git(repo, "checkout", "main")
            (repo / "new.txt").write_text(
                "line one\nline two\nline three\nline four\nfeature\n",
                encoding="utf-8",
            )
            _git(repo, "add", "new.txt")
            _git(repo, "commit", "-m", "squash new content")
            _git(repo, "update-ref", "refs/remotes/origin/main", "main")
            _git(repo, "checkout", "feature-x")

            clean, merged, reason = WorkerReaper()._check_worktree_safe_to_remove(repo)

            self.assertFalse(clean)
            self.assertFalse(merged)
            self.assertIn("old.txt", reason)
            # Mutant proof: rename detection lists only new.txt, which is
            # identical on main and would falsely report the branch landed.

    def test_reap_leaves_clean_merged_worktree_holding_ignored_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_media(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    return 0, "!! out/render.mp4\0", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_media)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(removed_paths, [])
            self.assertIn(f"worktree_left:{tmp}:ignored_media:1", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 1)
            # Failability: a version that ignored this measurement would
            # remove a worktree whose .gitignore covers rendered media,
            # losing that media with the worktree.

    def test_reap_leaves_clean_merged_worktree_holding_media_in_ignored_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_media(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    if "--untracked-files=all" in cmd and "-z" in cmd:
                        return 0, "!! renders/clip.mp4\0", ""
                    return 0, "!! renders/\n", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_media)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(removed_paths, [])
            self.assertIn(f"worktree_left:{tmp}:ignored_media:1", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 1)
            # Failability: dropping `--untracked-files=all` or `-z` in
            # production makes the fake runner fold the match to the
            # ignored directory itself, which carries no media suffix, so
            # this assertion catches either flag going missing.

    def test_reap_leaves_clean_merged_worktree_holding_ignored_media_with_space(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_media(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    if "--untracked-files=all" in cmd and "-z" in cmd:
                        return 0, "!! out/final cut.mp4\0", ""
                    return 0, "!! out/\n", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_media)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(removed_paths, [])
            self.assertIn(f"worktree_left:{tmp}:ignored_media:1", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 1)
            # Failability: dropping `--untracked-files=all` or `-z` in
            # production makes the fake runner fold the match to the
            # ignored directory itself, which carries no media suffix, so
            # this assertion catches either flag going missing, the same way
            # it would miss a quoted or spaced path without the real `-z`.

    def test_reap_removes_worktree_with_ignored_media_when_flag_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_media(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    return 0, "!! out/render.mp4\0", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_media)
            record = reaper.reap(task_id="t1", execute=True, remove_ignored_media=True)

            self.assertIn(tmp, removed_paths)
            self.assertIn(f"worktree_removed:{tmp}", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 1)

    def test_reap_removes_worktree_with_only_non_media_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_pyc(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    return 0, "!! module.pyc\0", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_pyc)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertIn(tmp, removed_paths)
            self.assertIn(f"worktree_removed:{tmp}", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 0)

    def test_reap_leaves_worktree_whose_ignored_media_scan_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_scan_failure(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    return 1, "", "git error"
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_scan_failure)
            record = reaper.reap(task_id="t1", execute=True)

            self.assertEqual(removed_paths, [])
            self.assertIn(
                f"worktree_left:{tmp}:ignored_media_unmeasured", record.actions_taken
            )
            self.assertIsNone(record.measurements["worktree_ignored_media"])
            # Failability: a version that read a failed `--ignored` scan as
            # "no ignored media" would remove the worktree unmeasured.

    def test_reap_dry_run_ignored_media_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_runner, removed_paths = _clean_worktree_runner(
                tmp,
                current_branch="main",
                merged_branches="* main\n",
            )
            original_runner = fake_runner

            def runner_with_ignored_media(cmd: list[str]) -> tuple[int, str, str]:
                if "git" in cmd and "status" in cmd and "--ignored" in cmd:
                    return 0, "!! out/render.mp4\0", ""
                return original_runner(cmd)

            reaper = WorkerReaper(orca_runner=runner_with_ignored_media)
            record = reaper.reap(task_id="t1", execute=False)

            self.assertEqual(removed_paths, [])
            self.assertIn(f"worktree_left:{tmp}:ignored_media:1", record.actions_taken)
            self.assertEqual(record.measurements["worktree_ignored_media"], 1)
            # Failability: a dry run that skipped this measurement would not
            # warn about the media before a real reap removes it.

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


class BranchDeletionTests(unittest.TestCase):
    """Branch deletion is gated by GitHub's merged PR and exact head OID."""

    def test_orca_cleanup_detection_requires_usage_lines(self) -> None:
        def runner(cmd: list[str]) -> tuple[int, str, str]:
            if cmd == ["orca", "terminal", "close", "--help"]:
                return 0, "--worktree <selector> --all\n", ""
            if cmd == ["orca", "worktree", "rm", "--help"]:
                return 0, "--worktree <selector> --delete-branch\n", ""
            return 0, "", ""

        self.assertFalse(WorkerReaper(orca_runner=runner)._orca_cleanup_supported())

    def test_orca_cleanup_detection_requires_selector_flags(self) -> None:
        for missing in ("terminal", "worktree"):
            with self.subTest(missing=missing):
                def runner(cmd: list[str]) -> tuple[int, str, str]:
                    if cmd == ["orca", "terminal", "close", "--help"]:
                        usage = "Usage: orca terminal close"
                        flags = " --all" if missing == "terminal" else " --worktree <selector> --all"
                        return 0, usage + flags + "\n", ""
                    if cmd == ["orca", "worktree", "rm", "--help"]:
                        usage = "Usage: orca worktree rm"
                        flags = " --delete-branch" if missing == "worktree" else " --worktree <selector> --delete-branch"
                        return 0, usage + flags + "\n", ""
                    return 0, "", ""

                self.assertFalse(WorkerReaper(orca_runner=runner)._orca_cleanup_supported())

    def _repo_with_branch(self, root: Path) -> tuple[Path, str, str]:
        repo = root / "repo"
        repo.mkdir()
        _git(repo, "init", "--initial-branch", "main")
        _git(repo, "config", "user.email", "worker-reap@example.invalid")
        _git(repo, "config", "user.name", "worker-reap test")
        (repo / "README").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "README")
        _git(repo, "commit", "-m", "base")
        _git(repo, "branch", "feature/test")
        tip = _git(repo, "rev-parse", "refs/heads/feature/test").strip()
        common_dir = _git(repo, "rev-parse", "--git-common-dir").strip()
        return repo, tip, str((repo / common_dir).resolve())

    def _run_case(
        self,
        case: str,
        branch_tip: str,
        common_dir: str,
        *,
        gh_head: str | None = None,
        execute: bool = True,
    ) -> str:
        def runner(cmd: list[str]) -> tuple[int, str, str]:
            if cmd and cmd[0] == "gh":
                head = gh_head or branch_tip
                if case == "merged":
                    return 0, json.dumps({"state": "MERGED", "headRefOid": head}), ""
                if case == "merged-empty-head":
                    return 0, json.dumps({"state": "MERGED"}), ""
                if case == "open":
                    return 0, json.dumps({"state": "OPEN", "headRefOid": head}), ""
                if case == "no-pr":
                    return 1, "", "no pull request found"
                if case == "unavailable":
                    return 1, "", "gh unavailable"
                return 1, "", "unknown gh fixture"
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode, result.stdout, result.stderr

        return WorkerReaper(orca_runner=runner)._plan_branch_deletion(
            "feature/test",
            branch_tip,
            common_dir,
            "example/worker-reap",
            execute=execute,
            reason="",
        )

    def test_merged_pr_with_equal_tip_deletes_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case("merged", tip, common_dir)

            self.assertEqual(action, "branch_deleted:feature/test")
            self.assertEqual(_git(repo, "branch", "--list", "feature/test"), "")

    def test_merged_pr_with_different_tip_keeps_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            different_tip = "0" * 40
            action = self._run_case(
                "merged",
                tip,
                common_dir,
                gh_head=different_tip,
            )

            self.assertIn("branch_left:feature/test:tip differs", action)
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )
            # Mutant proof: remove the tip-equality check and this different-tip
            # case must fail because the branch would be deleted.

    def test_open_pr_keeps_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case("open", tip, common_dir)

            self.assertEqual(action, "branch_left:feature/test:not merged")
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )

    def test_no_pr_keeps_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case("no-pr", tip, common_dir)

            self.assertEqual(action, "branch_left:feature/test:no PR")
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )

    def test_merged_pr_without_head_oid_keeps_branch_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case("merged-empty-head", tip, common_dir)

            self.assertEqual(action, "branch_left:feature/test:gh unavailable")
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )

    def test_gh_unavailable_keeps_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case(
                "unavailable", tip, common_dir
            )

            self.assertEqual(action, "branch_left:feature/test:gh unavailable")
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )

    def test_dry_run_reports_branch_deletion_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, tip, common_dir = self._repo_with_branch(root)
            action = self._run_case(
                "merged", tip, common_dir, execute=False
            )

            self.assertEqual(action, "would_delete_branch:feature/test")
            self.assertEqual(
                _git(repo, "rev-parse", "refs/heads/feature/test").strip(), tip
            )

    def test_reap_deletes_branch_after_worktree_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp)
            tip = "a" * 40
            common_dir = str(worktree / "repo.git")
            calls: list[list[str]] = []

            def runner(cmd: list[str]) -> tuple[int, str, str]:
                calls.append(cmd)
                if "dispatch-show" in cmd:
                    return 0, json.dumps(
                        {
                            "dispatch_id": "d1",
                            "task_id": "t1",
                            "status": "COMPLETED",
                            "worktree_path": str(worktree),
                        }
                    ), ""
                if cmd[:3] == ["git", "-C", str(worktree)] and "status" in cmd:
                    return 0, "", ""
                if cmd[:3] == ["git", "-C", str(worktree)] and "--show-current" in cmd:
                    return 0, "feature/test\n", ""
                if (
                    cmd[:3] == ["git", "-C", str(worktree)]
                    and cmd[3:5] == ["rev-parse", "HEAD"]
                ):
                    return 0, f"{tip}\n", ""
                if cmd[:3] == ["git", "-C", str(worktree)] and "--git-common-dir" in cmd:
                    return 0, f"{common_dir}\n", ""
                if cmd[:3] == ["git", "-C", str(worktree)] and cmd[3:] == [
                    "remote",
                    "get-url",
                    "origin",
                ]:
                    return 0, "https://github.com/example/worker-reap.git\n", ""
                if cmd[:2] == ["git", f"--git-dir={common_dir}"] and "rev-parse" in cmd:
                    return 0, f"{tip}\n", ""
                if "branch" in cmd and "--merged" in cmd:
                    return 0, "* main\n", ""
                if "rev-parse" in cmd and "origin/main^{tree}" in cmd:
                    return 0, "tree-main\n", ""
                if "merge-tree" in cmd:
                    return 0, "tree-main\n", ""
                if cmd and cmd[0] == "gh":
                    return 0, json.dumps(
                        [{"state": "MERGED", "headRefOid": tip}]
                    ), ""
                if "worktree" in cmd and "remove" in cmd:
                    return 0, "", ""
                if "branch" in cmd and "-D" in cmd:
                    return 0, "", ""
                return 0, "", ""

            record = WorkerReaper(orca_runner=runner).reap(task_id="t1", execute=True)

            self.assertIn(f"worktree_removed:{worktree}", record.actions_taken)
            self.assertIn("branch_deleted:feature/test", record.actions_taken)
            self.assertIn(
                [
                    "gh",
                    "pr",
                    "view",
                    "feature/test",
                    "--repo",
                    "github.com/example/worker-reap",
                    "--json",
                    "state,headRefOid",
                ],
                calls,
            )
            remove_index = next(
                i for i, cmd in enumerate(calls) if "worktree" in cmd and "remove" in cmd
            )
            delete_index = next(
                i for i, cmd in enumerate(calls) if "branch" in cmd and "-D" in cmd
            )
            self.assertLess(remove_index, delete_index)

    def test_selector_reaps_squash_merged_content_with_orca_verbs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertEqual(
                env.closed_commands,
                [["orca", "terminal", "close", "--worktree", "id:repo:target", "--all", "--json"]],
            )
            self.assertEqual(
                env.removed_commands,
                [["orca", "worktree", "rm", "--worktree", "id:repo:target", "--delete-branch", "--json"]],
            )
            self.assertEqual(record.measurements["worktree_landed_by"], "content")
            self.assertIn("worktree_remove_requested:", record.actions_taken)
            self.assertEqual(len(env.quiet_commands), 1)
            self.assertEqual(env.quiet_commands[0][-2:], ["--", "src/worker.py"])
            # Mutant proof: replacing the content rule with ancestry leaves
            # this squash-merged branch unreaped.

    def test_unpushed_worktree_skips_orca_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, content_equal=False)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("branch changes are not included", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            self.assertIn("would_close_worktree:id:repo:target", record.actions_taken)
            self.assertEqual(record.measurements["worktree_terminal_handles"], ["term-target"])
            self.assertEqual(record.measurements["pane_states"], {"term-target": "idle"})
            self.assertEqual(record.measurements["agent_process"], "")
            # Mutant proof: calling cleanup verbs before the unpushed check
            # would discard the resume worktree.

    def test_squash_merge_pr_evidence_routes_through_orca(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                content_equal=False,
                merged_pr=True,
                virtual_merge_fails=True,
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertEqual(record.measurements["worktree_landed_by"], "merged_pr")
            self.assertEqual(len(env.closed_commands), 1)
            self.assertEqual(len(env.removed_commands), 1)
            # Mutant proof: treating a failed virtual/content landing check as
            # final would leave the squash-merged #285 worktree behind.

    def test_squash_merge_pr_evidence_keeps_content_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, content_equal=False, merged_pr=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("branch changes are not included", record.actions_taken)
            self.assertNotIn("worktree_landed_by", record.measurements)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_squash_merge_override_requires_orca_verbs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                content_equal=False,
                merged_pr=True,
                virtual_merge_fails=True,
                orca_cleanup_supported=False,
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("virtual merge failed", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(env.legacy_removed_commands, [])

    def test_squash_merge_tip_mismatch_keeps_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                content_equal=False,
                merged_pr=True,
                virtual_merge_fails=True,
                merged_pr_head="older-tip",
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("virtual merge failed", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(env.legacy_removed_commands, [])
            # Mutant proof: deleting the headRefOid == branch tip comparison
            # would incorrectly reclaim a branch with local commits not pushed.

    def test_fork_pr_with_same_branch_name_keeps_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                content_equal=False,
                merged_pr=True,
                virtual_merge_fails=True,
                merged_pr_repository="fork/worker-reap",
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("virtual merge failed", record.actions_taken)
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(env.legacy_removed_commands, [])

    def test_squash_merge_uses_measured_default_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                content_equal=False,
                merged_pr=True,
                virtual_merge_fails=True,
                merged_pr_base="trunk",
                default_branch="trunk",
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertEqual(record.measurements["worktree_landed_by"], "merged_pr")
            self.assertEqual(len(env.removed_commands), 1)
            self.assertTrue(
                any(
                    cmd[-1] == "origin/trunk"
                    for cmd in env.merge_commands
                )
            )

    def test_missing_orca_verbs_use_legacy_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, orca_cleanup_supported=False)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("worktree_removed:", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(len(env.legacy_closed_commands), 1)
            self.assertEqual(len(env.legacy_removed_commands), 1)
            # Mutant proof: calling selector verbs without measured support
            # would fail on older hosts instead of using the existing path.

    def test_missing_terminal_id_keeps_legacy_cleanup_message_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp, orca_cleanup_supported=False, no_terminal_id=True
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("worktree_removed:", record.actions_taken)
            self.assertEqual(len(env.legacy_removed_commands), 1)

    def test_legacy_absent_terminal_checks_agent_process_before_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp,
                orca_cleanup_supported=False,
                no_terminal_id=True,
                agent_pid="4242",
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("agent_process:4242:claude", record.actions_taken)
            self.assertEqual(env.legacy_removed_commands, [])

    def test_merged_pr_for_another_base_does_not_prove_landing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp, content_equal=False, merged_pr=True, merged_pr_base="release"
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("branch changes are not included", record.actions_taken)
            self.assertEqual(env.removed_commands, [])

    def test_pr_measurement_failure_keeps_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, gh_pr_fails=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertEqual(record.measurements["worktree_pr_state"], "UNMEASURED")
            self.assertEqual(record.measurements["worktree_pr_reason"], "pr_state_unmeasured")
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(env.legacy_removed_commands, [])

    def test_open_pr_skips_orca_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, open_pr=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("pull request is open", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_selector_resolution_mismatch_refuses_worktree_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            other = str(Path(tmp) / "other")
            env = _SelectorEnvironment(tmp, resolved_worktree_path=other)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("resolved to", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            self.assertNotIn("--force", " ".join(" ".join(cmd) for cmd in env.commands))

    def test_unsupported_orca_host_keeps_legacy_content_landing_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp, orca_cleanup_supported=False, gh_pr_fails=True
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("worktree_removed:", record.actions_taken)
            self.assertEqual(
                {key for key in record.measurements if key.startswith("worktree_pr_")},
                set(),
            )
            self.assertEqual(len(env.legacy_closed_commands), 1)
            self.assertEqual(len(env.legacy_removed_commands), 1)

    def test_selector_dirty_worktree_keeps_resources_with_merged_pr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, dirty=True, merged_pr=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("Worktree has uncommitted changes", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_selector_cleanup_never_passes_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp)
            WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertTrue(env.removed_commands)
            self.assertTrue(all("--force" not in cmd for cmd in env.removed_commands))

    def test_pr_list_size_guard_is_unmeasured(self) -> None:
        commands: list[list[str]] = []

        def runner(cmd: list[str]) -> tuple[int, str, str]:
            commands.append(cmd)
            return 0, json.dumps([{} for _ in range(100)]), ""

        self.assertIsNone(
            WorkerReaper(orca_runner=runner)._pull_requests_for_branch(
                "feature-x", "github.com/example/worker-reap"
            )
        )
        self.assertIn("--limit", commands[0])
        self.assertEqual(commands[0][commands[0].index("--limit") + 1], "100")

    def test_selector_reports_orca_branch_warning_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, remove_warning=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn(
                'warning: local branch "feature-x" was kept because Git could not safely delete it',
                record.actions_taken,
            )

    def test_selector_refuses_content_difference_and_names_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, content_equal=False)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("differing paths: src/worker.py", record.actions_taken)
            self.assertEqual(env.removed_commands, [])
            self.assertEqual(env.quiet_commands[0][-2:], ["--", "src/worker.py"])
            # Mutant proof: removing the path-scoped `git diff --quiet` check
            # would delete a branch whose changed file still differs.

    def test_selector_ignores_matching_title_in_another_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, include_title_decoy=True)
            WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            close_command = env.closed_commands[0]
            self.assertEqual(close_command[3:5], ["--worktree", "id:repo:target"])
            self.assertNotIn("term-decoy", " ".join(close_command))
            # Mutant proof: selecting by title would close the decoy pane.

    def test_selector_refuses_a_busy_pane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, pane_state="working")
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("pane_not_idle:term-target:working", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            # Mutant proof: treating every pane as idle would close a live
            # worker and remove its worktree.

    def test_selector_refuses_a_worktree_reused_by_dispatched_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, reused_by="ctx-newer")
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("reused_by:ctx-newer", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            # Mutant proof: dropping the worktree-level reuse guard closes all
            # panes belonging to the newer dispatch.

    def test_selector_refuses_reuse_in_current_worker_list_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(
                tmp, reused_by="ctx-newer", worker_list_shape="current"
            )
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("reused_by:ctx-newer", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_selector_does_not_close_before_unmerged_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, content_equal=False)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("branch changes are not included", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            # Mutant proof: closing before the landing check loses the session
            # needed to resume this unfinished dispatch.

    def test_selector_without_worktree_path_is_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, no_worktree_path=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("worktree_path_unmeasured", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_selector_refuses_nonzero_sweep_with_parsed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, sweep_fails=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("pane_state_unmeasured", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])

    def test_selector_records_partial_cleanup_when_worktree_remove_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, remove_fails=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn(
                "cleanup_partial:terminals_closed:worktree_remove_failed",
                record.actions_taken,
            )
            self.assertEqual(len(env.closed_commands), 1)
            self.assertEqual(len(env.removed_commands), 1)

    def test_selector_checks_agent_process_when_no_panes_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, no_panes=True, agent_pid="4242")
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("agent_process:4242:claude", record.actions_taken)
            self.assertEqual(env.removed_commands, [])

    def test_selector_checks_worktree_reuse_when_no_panes_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, no_panes=True, reused_by="ctx-newer")
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("reused_by:ctx-newer", record.actions_taken)
            self.assertEqual(env.removed_commands, [])

    def test_selector_refuses_no_panes_when_agent_process_scan_is_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, no_panes=True, ps_fails=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("agent_process_unmeasured", record.actions_taken)
            self.assertEqual(env.removed_commands, [])

    def test_selector_does_not_claim_terminals_closed_when_no_pane_was_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, no_panes=True, remove_fails=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("cleanup_partial:terminals_not_closed:worktree_remove_failed", record.actions_taken)
            self.assertNotIn("cleanup_partial:terminals_closed", record.actions_taken)

    def test_selector_refuses_unmeasured_pane_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp, missing_handle=True)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=True)

            self.assertIn("worktree_membership_unmeasured", record.actions_taken)
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])
            # Mutant proof: filtering missing handles and treating the list as
            # empty would remove a worktree without measuring its pane.

    def test_selector_dry_run_reports_content_landing_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SelectorEnvironment(tmp)
            record = WorkerReaper(orca_runner=env).reap(task_id="t1", execute=False)

            self.assertIn("landed_by:content", record.actions_taken)
            self.assertEqual(record.measurements["worktree_landed_by"], "content")
            self.assertEqual(env.closed_commands, [])
            self.assertEqual(env.removed_commands, [])


class _SelectorEnvironment:
    def __init__(
        self,
        worktree_path: str,
        *,
        content_equal: bool = True,
        pane_state: str = "idle",
        include_title_decoy: bool = False,
        missing_handle: bool = False,
        reused_by: str | None = None,
        sweep_fails: bool = False,
        remove_fails: bool = False,
        no_panes: bool = False,
        no_worktree_path: bool = False,
        worker_list_shape: str = "legacy",
        orca_cleanup_supported: bool = True,
        merged_pr: bool = False,
        merged_pr_base: str = "main",
        merged_pr_head: str = "tip",
        merged_pr_repository: str = "example/worker-reap",
        default_branch: str = "main",
        virtual_merge_fails: bool = False,
        gh_pr_fails: bool = False,
        open_pr: bool = False,
        remove_warning: bool = False,
        no_terminal_id: bool = False,
        agent_pid: str | None = None,
        ps_fails: bool = False,
        resolved_worktree_path: str | None = None,
        dirty: bool = False,
    ) -> None:
        self.worktree_path = worktree_path
        self.content_equal = content_equal
        self.pane_state = pane_state
        self.include_title_decoy = include_title_decoy
        self.missing_handle = missing_handle
        self.reused_by = reused_by
        self.sweep_fails = sweep_fails
        self.remove_fails = remove_fails
        self.no_panes = no_panes
        self.no_worktree_path = no_worktree_path
        self.worker_list_shape = worker_list_shape
        self.orca_cleanup_supported = orca_cleanup_supported
        self.merged_pr = merged_pr
        self.merged_pr_base = merged_pr_base
        self.merged_pr_head = merged_pr_head
        self.merged_pr_repository = merged_pr_repository
        self.default_branch = default_branch
        self.virtual_merge_fails = virtual_merge_fails
        self.branch_show_calls = 0
        self.gh_pr_fails = gh_pr_fails
        self.open_pr = open_pr
        self.remove_warning = remove_warning
        self.no_terminal_id = no_terminal_id
        self.agent_pid = agent_pid
        self.ps_fails = ps_fails
        self.resolved_worktree_path = resolved_worktree_path or worktree_path
        self.dirty = dirty
        self.commands: list[list[str]] = []
        self.closed_commands: list[list[str]] = []
        self.removed_commands: list[list[str]] = []
        self.legacy_closed_commands: list[list[str]] = []
        self.legacy_removed_commands: list[list[str]] = []
        self.quiet_commands: list[list[str]] = []
        self.merge_commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        self.commands.append(cmd)
        if cmd == ["orca", "terminal", "close", "--help"]:
            if self.orca_cleanup_supported:
                return 0, "Usage: orca terminal close --worktree <selector> --all\n", ""
            return 0, "usage: orca terminal close\n", ""
        if cmd == ["orca", "worktree", "rm", "--help"]:
            if self.orca_cleanup_supported:
                return 0, "Usage: orca worktree rm --worktree <selector> --delete-branch\n", ""
            return 0, "usage: orca worktree rm\n", ""
        if cmd[:4] == ["orca", "worktree", "list", "--json"]:
            return 0, json.dumps(
                {
                    "result": {
                        "worktrees": [
                            {
                                "worktreeId": "repo:target",
                                "worktreePath": self.resolved_worktree_path,
                            }
                        ]
                    }
                }
            ), ""
        if cmd[:3] == ["gh", "repo", "view"]:
            return 0, json.dumps({"defaultBranchRef": {"name": self.default_branch}}), ""
        if "dispatch-show" in cmd:
            dispatch = {
                "dispatch_id": "d1",
                "task_id": "t1",
                "terminal_id": "term-target",
                "status": "COMPLETED",
                "worktree_path": self.worktree_path,
                "worktree_selector": "id:repo:target",
            }
            if self.no_worktree_path:
                dispatch.pop("worktree_path")
            if self.no_terminal_id:
                dispatch.pop("terminal_id")
            return 0, json.dumps(dispatch), ""
        if cmd[:4] == ["orca", "terminal", "list", "--json"]:
            target = {
                "worktreeId": "repo:target",
                "worktreePath": self.worktree_path,
                "title": "same title",
            }
            if not self.missing_handle:
                target["handle"] = "term-target"
            terminals = [] if self.no_panes else [target]
            if self.include_title_decoy:
                terminals.append(
                    {
                        "handle": "term-decoy",
                        "worktreeId": "repo:other",
                        "worktreePath": str(Path(self.worktree_path).parent / "other"),
                        "title": "same title",
                    }
                )
            return 0, json.dumps({"result": {"terminals": terminals}}), ""
        if cmd[:4] == ["orca", "orchestration", "worker-list", "--limit"]:
            workers = []
            if self.reused_by:
                if self.worker_list_shape == "current":
                    workers.append(
                        {
                            "id": self.reused_by,
                            "outcome": "in_progress",
                            "terminal": "term-target",
                        }
                    )
                else:
                    workers.append(
                        {
                            "dispatchId": self.reused_by,
                            "dispatchStatus": "dispatched",
                            "worktreeId": "repo:target",
                        }
                    )
            if self.worker_list_shape == "current":
                return 0, json.dumps({"result": {"workers": workers, "nextCursor": ""}}), ""
            return 0, json.dumps({"result": {"workers": workers, "page": {"hasMore": False}}}), ""
        if cmd and cmd[0].endswith("worker-pane-sweep"):
            return (1 if self.sweep_fails else 0), (
                f"ok {self.pane_state} term-target worker\n"
            ), ""
        if cmd[:2] == ["ps", "-axo"]:
            if self.ps_fails:
                return 1, "", "ps unavailable"
            if self.agent_pid:
                return 0, f"{self.agent_pid} claude\n", ""
            return 0, "", ""
        if cmd[:2] == ["lsof", "-a"] and self.agent_pid:
            return 0, f"p{self.agent_pid}\nfcwd\nn{self.worktree_path}\n", ""
        if cmd[:5] == ["orca", "terminal", "close", "--worktree", "id:repo:target"]:
            self.closed_commands.append(cmd)
            return 0, "", ""
        if cmd[:5] == ["orca", "worktree", "rm", "--worktree", "id:repo:target"]:
            self.removed_commands.append(cmd)
            if self.remove_fails:
                return 1, "", "remove failed"
            if self.remove_warning:
                return 0, (
                    'warning: local branch "feature-x" was kept because Git could not safely delete it\n'
                ), ""
            return 0, "", ""
        if cmd[:4] == ["orca", "terminal", "close", "--terminal"]:
            self.legacy_closed_commands.append(cmd)
            return 0, "", ""
        if "git" in cmd and "status" in cmd:
            return 0, (" M src/worker.py\n" if self.dirty else ""), ""
        if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
            self.branch_show_calls += 1
            if self.virtual_merge_fails and self.branch_show_calls == 2:
                return 1, "", "branch measurement failed"
            return 0, "feature-x\n", ""
        if "git" in cmd and cmd[3:5] == ["rev-parse", "HEAD"]:
            return 0, "tip\n", ""
        if "git" in cmd and "--git-common-dir" in cmd:
            return 0, "/repo/.git\n", ""
        if "git" in cmd and cmd[3:] == ["remote", "get-url", "origin"]:
            return 0, "https://github.com/example/worker-reap.git\n", ""
        if "git" in cmd and "branch" in cmd and "--merged" in cmd:
            self.merge_commands.append(cmd)
            return 0, "* main\n", ""
        if "git" in cmd and "merge-base" in cmd:
            return 0, "base\n", ""
        if self.virtual_merge_fails and "merge-tree" in cmd:
            return 1, "", "virtual merge failed"
        if "git" in cmd and "--name-only" in cmd:
            return 0, "src/worker.py\0", ""
        if "git" in cmd and "--quiet" in cmd:
            self.quiet_commands.append(cmd)
            if "--" not in cmd or cmd[cmd.index("--") + 1 :] != ["src/worker.py"]:
                return 2, "", "path scope missing"
            return (0 if self.content_equal else 1), "", ""
        if (
            cmd
            and cmd[0] == "git"
            and any(arg.startswith("--git-dir=") for arg in cmd[1:])
            and "worktree" in cmd
            and "remove" in cmd
        ):
            self.legacy_removed_commands.append(cmd)
            return 0, "", ""
        if cmd and cmd[0] == "gh" and cmd[1:3] == ["pr", "list"]:
            if self.gh_pr_fails:
                return 1, "", "gh unavailable"
            if self.open_pr:
                return 0, json.dumps(
                    [{
                        "state": "OPEN",
                        "headRefOid": "tip",
                        "baseRefName": self.merged_pr_base,
                        "headRepositoryOwner": {"login": self.merged_pr_repository.split("/", 1)[0]},
                        "headRepository": {"name": self.merged_pr_repository.split("/", 1)[1]},
                    }]
                ), ""
            if self.merged_pr:
                return 0, json.dumps(
                    [{
                        "state": "MERGED",
                        "headRefOid": self.merged_pr_head,
                        "baseRefName": self.merged_pr_base,
                        "headRepositoryOwner": {"login": self.merged_pr_repository.split("/", 1)[0]},
                        "headRepository": {"name": self.merged_pr_repository.split("/", 1)[1]},
                    }]
                ), ""
            return 0, "[]", ""
        return 0, "", ""


class _FakeRunner:
    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        return 0, "", ""


FAKE_GIT_COMMON_DIR = "/repo/.git"


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
        if "git" in cmd and cmd[3:] == ["remote", "get-url", "origin"]:
            return 0, "https://github.com/example/worker-reap.git\n", ""
        if "git" in cmd and "branch" in cmd and "--merged" in cmd:
            return 0, merged_branches, ""
        if "git" in cmd and "rev-parse" in cmd and "--git-common-dir" in cmd:
            return 0, f"{FAKE_GIT_COMMON_DIR}\n", ""
        if "git" in cmd and "rev-parse" in cmd and origin_main_tree is not None:
            return 0, f"{origin_main_tree}\n", ""
        if "git" in cmd and "merge-tree" in cmd and virtual_merge_tree is not None:
            return 0, f"{virtual_merge_tree}\n", ""
        if "git" in cmd and "worktree" in cmd and "remove" in cmd:
            removed_paths.append(cmd[-1])
            return 0, "", ""
        if cmd[:4] == ["orca", "terminal", "list", "--json"]:
            return 0, json.dumps({"result": {"terminals": [{"handle": "term1"}]}}), ""
        if cmd[:4] == ["orca", "orchestration", "worker-list", "--limit"]:
            return 0, json.dumps({"result": {"workers": [], "page": {"hasMore": False}}}), ""
        if cmd[:2] == ["ps", "-axo"]:
            return 0, "", ""
        if "terminal" in cmd and "close" in cmd:
            return 0, "", ""
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, "[]", ""
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
