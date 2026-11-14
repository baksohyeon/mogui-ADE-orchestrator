from __future__ import annotations

import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

from master_runtime.core.worker_reap import WorkerReaper


def _load_cli():
    script_path = Path(__file__).parents[1] / "scripts" / "worker-reap"
    loader = SourceFileLoader("worker_reap_cli", str(script_path))
    spec = importlib.util.spec_from_loader("worker_reap_cli", loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deprecation_notice_is_printed_once_and_exit_code_is_preserved(monkeypatch) -> None:
    module = _load_cli()

    class FailingReaper:
        def __init__(self, **_kwargs):
            pass

        def reap(self, **_kwargs):
            raise module.ReapError("dispatch is not settled", 3)

    monkeypatch.setattr(module, "WorkerReaper", FailingReaper)
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = module.main(["--task-id", "task-test"])

    assert exit_code == 3
    assert stderr.getvalue().count("DEPRECATED:") == 1
    assert "orca terminal close --worktree <selector> --all" in stderr.getvalue()
    assert "orca worktree rm --worktree <selector> --delete-branch" in stderr.getvalue()


def test_legacy_agent_process_refusal_keeps_message_and_success_exit(monkeypatch) -> None:
    module = _load_cli()

    with tempfile.TemporaryDirectory() as tmp:
        def runner(cmd: list[str]) -> tuple[int, str, str]:
            if "dispatch-show" in cmd:
                return 0, json.dumps(
                    {
                        "dispatch_id": "d1",
                        "task_id": "t1",
                        "terminal_id": "term1",
                        "status": "COMPLETED",
                        "worktree_path": tmp,
                    }
                ), ""
            if cmd[:4] == ["orca", "terminal", "list", "--json"]:
                return 0, json.dumps({"result": {"terminals": [{"handle": "term1"}]}}), ""
            if cmd[:3] == ["orca", "orchestration", "worker-list"]:
                return 0, json.dumps({"result": {"workers": [], "page": {"hasMore": False}}}), ""
            if cmd[:2] == ["ps", "-axo"]:
                return 0, "4242 claude\n", ""
            if cmd[:2] == ["lsof", "-a"]:
                return 0, f"p4242\nfcwd\nn{tmp}\n", ""
            if "git" in cmd and "status" in cmd:
                return 0, "", ""
            if "git" in cmd and "branch" in cmd and "--show-current" in cmd:
                return 0, "main\n", ""
            if "git" in cmd and "branch" in cmd and "--merged" in cmd:
                return 0, "* main\n", ""
            if "git" in cmd and cmd[3:] == ["remote", "get-url", "origin"]:
                return 0, "https://github.com/example/worker-reap.git\n", ""
            if cmd[:3] == ["gh", "pr", "list"]:
                return 0, "[]", ""
            return 0, "", ""

        class LegacyReaper:
            def __init__(self, **_kwargs):
                self.reaper = WorkerReaper(orca_runner=runner)

            def reap(self, **kwargs):
                return self.reaper.reap(**kwargs)

        monkeypatch.setattr(module, "WorkerReaper", LegacyReaper)
        monkeypatch.setattr(module, "mogui_emit", lambda *_args, **_kwargs: None)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = module.main(["--task-id", "t1"])

        payload = json.loads(stdout.getvalue())
        assert exit_code == 0
        assert "terminal_left:term1:agent_process:4242:claude" in payload["record"]["actions_taken"]
