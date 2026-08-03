"""The organization rules must compile in the engine that runs them.

The translator validated regexes with Python's re, and Python is not the
engine. gitleaks compiles RE2, which rejects lookarounds by panicking at
config load, and every scan under a panicking config found nothing — measured
live: two organization rules using lookbehind turned every org-rules scan into
a green no-op from the moment the engine was swapped. These tests pin the two
halves of the fix: the merged config is proven against the actual engine
before anything is scanned, and an engine failure during a scan is exit 2
rather than silence.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from test_redaction_scan_commit_messages import _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface

REPO_ROOT = Path(__file__).resolve().parents[1]


def _scan_with_extra(repo: Path, extra: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "REDACTION_EXTRA_PATTERNS": str(extra)}
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks is the engine under test",
)


@requires_gitleaks
def test_lookbehind_rule_fails_closed_and_names_the_rule(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["one commit"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "good_rule|plain token|ZZPROBEZZ[0-9]+\n"
        "bad_lookbehind|regex only python accepts|(?<![A-Za-z0-9_])probe(?![A-Za-z0-9_])\n",
        encoding="utf-8",
    )

    result = _scan_with_extra(repo, extra)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "crashes the engine" in result.stderr
    assert "bad_lookbehind" in result.stderr
    assert "good_rule" not in result.stderr.split("RE2:")[1], result.stderr
    # The pattern itself is what the rules file protects; ids only.
    assert "(?<!" not in result.stderr


def test_engine_failure_during_scan_is_exit_2_not_silence(tmp_path: Path) -> None:
    """--exit-code 0 makes findings exit 0, so nonzero from gitleaks is the
    engine failing, and a failed engine must not read as a clean file."""

    repo = _repo_with_commits(tmp_path, ["one commit"])
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    shim = shim_bin / "gitleaks"
    # Healthy for the version banner, dead for every actual scan.
    shim.write_text(
        '#!/bin/sh\ncase "$1" in version) echo shim-1.0; exit 0 ;; esac\nexit 2\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{shim_bin}:{os.environ['PATH']}"}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)

    result = subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "engine error, not a finding" in result.stderr
    assert "OK — 0 findings" not in result.stdout


def test_unresolvable_range_is_exit_2_not_a_clean_scan(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["one commit"])
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)

    result = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "redaction-scan.sh"),
            "--range",
            "0000000000000000000000000000000000000000..HEAD",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "range does not resolve" in result.stderr
    assert "OK" not in result.stdout
