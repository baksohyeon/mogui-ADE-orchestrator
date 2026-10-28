"""REDACTION_PYTHON lets a caller name the interpreter the scanner must use.

Every heredoc call site used a bare python3, so a Windows host whose python3
on PATH is the Microsoft Store stub popped an installer prompt instead of
running the scan. These tests pin both halves of the override: a working
interpreter is actually invoked at the call sites, and an interpreter that
cannot run fails closed with the scanner's own undecidable wording instead of
crashing later inside a heredoc.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from test_redaction_scan_commit_messages import _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface


def _scan_with_python_override(repo: Path, python_override: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "REDACTION_PYTHON": str(python_override)}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_shim(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_redaction_python_shim_is_invoked_and_scan_passes(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    log = tmp_path / "python-shim.log"
    log.write_text("", encoding="utf-8")
    shim = tmp_path / "python-shim.sh"
    _write_shim(
        shim,
        "#!/bin/sh\n"
        f'echo called >> "{log}"\n'
        f'exec "{sys.executable}" "$@"\n',
    )

    result = _scan_with_python_override(repo, shim)

    # A clean tracked-mode scan with no org rules and no commit range reaches
    # the resolved interpreter exactly twice: the runnability probe and the
    # unconditional findings merge. Fewer lines means one of those call
    # sites fell back to a bare python3 instead of the override.
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_unrunnable_redaction_python_exits_could_not_decide(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    shim = tmp_path / "bad-python-shim.sh"
    _write_shim(shim, "#!/bin/sh\nexit 7\n")

    result = _scan_with_python_override(repo, shim)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "could not decide" in result.stderr
