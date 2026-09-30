from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

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

        # Worktree cleanliness/merge scenarios (dirty, non-main branch, not
        # yet merged) are covered by the dedicated _clean_worktree_runner
        # fake below, not by this one: every _MeasuredEnvironment call site
        # only needs the worktree checks to clear, never to flip, so this
        # always reports a clean, merged main branch.
        if "git" in cmd and "status" in cmd:
            return 0, "", ""
        if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
            return 0, "main\n", ""
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
