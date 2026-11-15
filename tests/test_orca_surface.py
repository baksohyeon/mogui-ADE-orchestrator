"""Tests for the Orca surface baseline minimum-version finding."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from windows_exec_surface import skip_windows_exec_surface

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_CHECK = REPO_ROOT / "master-ops" / "scripts" / "orca-surface-check.sh"
pytestmark = skip_windows_exec_surface


def _fake_orca(path: Path, app_version: str) -> None:
    path.write_text(
        f'''#!/usr/bin/env bash
case "$*" in
  "status --json") printf '%s\\n' '{{"result":{{"runtime":{{"appVersion":"{app_version}"}}}}}}' ;;
  "agent-context --json") printf '%s\\n' '{{"schemaVersion":1,"commandCount":0,"commands":[]}}' ;;
  *) exit 1 ;;
esac
''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_surface_check_reports_below_minimum_separately_from_drift(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "1.4.257")
    baseline = {
        "appVersion": "1.4.258",
        "minimumAppVersion": "1.4.258",
        "schemaVersion": 1,
        "commandCount": 0,
        "watchedCommands": [],
        "commandDigests": {},
        "generatedAt": "2026-11-14T00:00:00Z",
    }
    baseline_path = tmp_path / "orca-surface-baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["BASELINE_FILE"] = str(baseline_path)
    result = subprocess.run(
        ["bash", str(SURFACE_CHECK), "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BELOW-MINIMUM" in result.stderr, result.stderr
    assert "DRIFT:" in result.stderr, result.stderr
    assert "appVersion 1.4.258 -> 1.4.257" in result.stderr, result.stderr
