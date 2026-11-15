from __future__ import annotations

import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_cli():
    path = Path(__file__).parents[1] / "scripts" / "worker-reap"
    loader = SourceFileLoader("worker_reap_cli_round5", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deprecation_notice_prints_once_without_changing_exit_code(monkeypatch) -> None:
    module = _load_cli()

    class Reaper:
        def __init__(self, **_kwargs):
            pass

        def reap(self, **_kwargs):
            raise module.ReapError("dispatch is not settled", 3)

    monkeypatch.setattr(module, "WorkerReaper", Reaper)
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = module.main(["--task-id", "task-test"])

    assert exit_code == 3
    assert stderr.getvalue().count("DEPRECATED:") == 1
    assert "orca terminal close --worktree <sel> --all" in stderr.getvalue()
    assert "orca worktree rm --worktree <sel> --delete-branch" in stderr.getvalue()


def test_legacy_fallback_cli_keeps_json_exit_and_measurements(monkeypatch) -> None:
    module = _load_cli()
    real_worker_reaper = module.WorkerReaper

    with tempfile.TemporaryDirectory() as tmp:
        def runner(cmd: list[str]) -> tuple[int, str, str]:
            if "dispatch-show" in cmd:
                return 0, json.dumps({
                    "dispatch_id": "d1",
                    "task_id": "t1",
                    "terminal_id": "term1",
                    "status": "COMPLETED",
                    "worktree_path": tmp,
                }), ""
            if cmd[:4] == ["orca", "terminal", "list", "--json"]:
                return 0, json.dumps({"result": {"terminals": [{"handle": "term1"}]}}), ""
            if cmd[:4] == ["orca", "orchestration", "worker-list", "--limit"]:
                return 0, json.dumps({"result": {"workers": [], "page": {"hasMore": False}}}), ""
            if cmd[:2] == ["ps", "-axo"]:
                return 0, "", ""
            if "git" in cmd and "status" in cmd:
                return 0, "", ""
            if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
                return 0, "main\n", ""
            if "git" in cmd and "branch" in cmd and "--merged" in cmd:
                return 0, "* main\n", ""
            if "git" in cmd and "rev-parse" in cmd and "HEAD" in cmd:
                return 0, "tip\n", ""
            if "git" in cmd and "--git-common-dir" in cmd:
                return 0, "/repo/.git\n", ""
            if "git" in cmd and "worktree" in cmd and "remove" in cmd:
                return 0, "", ""
            return 0, "", ""

        class LegacyReaper:
            def __init__(self, **_kwargs):
                self.reaper = real_worker_reaper(orca_runner=runner)

            def reap(self, **kwargs):
                return self.reaper.reap(**kwargs)

        monkeypatch.setattr(module, "WorkerReaper", LegacyReaper)
        monkeypatch.setattr(module, "mogui_emit", lambda *_args, **_kwargs: None)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = module.main(["--task-id", "t1", "--json"])

        payload = json.loads(stdout.getvalue())
        assert exit_code == 0
        assert "worktree_removed:" in payload["record"]["actions_taken"]
        assert not any(
            key.startswith("worktree_pr_") for key in payload["record"]["measurements"]
        )
