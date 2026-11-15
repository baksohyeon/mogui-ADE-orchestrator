from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

from master_runtime.core.worker_reap import ReapRecord


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "worker-reap"
LOADER = importlib.machinery.SourceFileLoader("worker_reap_cli", str(SCRIPT_PATH))
SPEC = importlib.util.spec_from_file_location("worker_reap_cli", SCRIPT_PATH, loader=LOADER)
assert SPEC is not None and SPEC.loader is not None
worker_reap_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker_reap_cli)


class _SuccessfulReaper:
    def __init__(self, **_kwargs: object) -> None:
        self.record = ReapRecord(
            task_id="t1",
            dispatch_id="d1",
            terminal_id="term1",
            worktree_path=None,
            actions_taken="",
            timestamp=0.0,
        )

    def reap(self, **_kwargs: object) -> object:
        return self.record


class _FailingReaper:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def reap(self, **_kwargs: object) -> object:
        raise worker_reap_cli.ReapError("failed", 7)


class WorkerReapCliTests(unittest.TestCase):
    def test_deprecation_line_prints_once_and_success_exit_is_unchanged(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(worker_reap_cli, "WorkerReaper", _SuccessfulReaper),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = worker_reap_cli.main(["--task-id", "t1", "--dry-run", "--json"])

        self.assertEqual(exit_code, 0)
        lines = stderr.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("deprecated", lines[0].lower())
        self.assertIn("orca terminal close --worktree <sel> --all", lines[0])
        self.assertIn("orca worktree rm --worktree <sel> --delete-branch", lines[0])
        self.assertNotIn("template", lines[0].lower())
        self.assertNotIn("minimum", lines[0].lower())

    def test_deprecation_line_does_not_change_failure_exit_code(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(worker_reap_cli, "WorkerReaper", _FailingReaper),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = worker_reap_cli.main(["--task-id", "t1"])

        self.assertEqual(exit_code, 7)
        self.assertEqual(len(stderr.getvalue().splitlines()), 2)
        self.assertIn("deprecated", stderr.getvalue().lower())
        self.assertIn("orca terminal close --worktree <sel> --all", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
