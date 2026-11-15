from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stderr
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
