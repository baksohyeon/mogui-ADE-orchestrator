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


def _run_surface(
    tmp_path: Path, bin_dir: Path, baseline_path: Path
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["BASELINE_FILE"] = str(baseline_path)
    return subprocess.run(
        ["bash", str(SURFACE_CHECK), "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _baseline(tmp_path: Path, *, app_version: str, minimum: str) -> Path:
    baseline = {
        "appVersion": app_version,
        "minimumAppVersion": minimum,
        "schemaVersion": 1,
        "commandCount": 0,
        "watchedCommands": [],
        "commandDigests": {},
        "generatedAt": "2026-11-14T00:00:00Z",
    }
    path = tmp_path / "orca-surface-baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    return path


def test_surface_check_reports_below_minimum_alongside_drift(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "1.4.257")
    baseline_path = _baseline(
        tmp_path, app_version="1.4.258", minimum="1.4.258"
    )
    result = _run_surface(tmp_path, bin_dir, baseline_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BELOW-MINIMUM" in result.stderr, result.stderr
    assert "DRIFT:" in result.stderr, result.stderr
    assert "appVersion 1.4.258 -> 1.4.257" in result.stderr, result.stderr


def test_surface_check_isolates_below_minimum_from_drift(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "1.4.257")
    baseline_path = _baseline(
        tmp_path, app_version="1.4.257", minimum="1.4.258"
    )
    result = _run_surface(tmp_path, bin_dir, baseline_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BELOW-MINIMUM" in result.stderr, result.stderr
    assert "DRIFT:" not in result.stderr, result.stderr


def test_surface_check_passes_at_minimum(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "1.4.258")
    baseline_path = _baseline(
        tmp_path, app_version="1.4.258", minimum="1.4.258"
    )
    result = _run_surface(tmp_path, bin_dir, baseline_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "BELOW-MINIMUM" not in result.stderr, result.stderr
    assert "DRIFT:" not in result.stderr, result.stderr


def test_surface_check_reports_unparsable_version_as_drift(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "version unavailable")
    baseline_path = _baseline(
        tmp_path, app_version="1.4.258", minimum="1.4.258"
    )
    result = _run_surface(tmp_path, bin_dir, baseline_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "DRIFT:" in result.stderr, result.stderr
    assert "installed appVersion is unparsable" in result.stderr, result.stderr


def test_surface_check_explains_missing_minimum_version(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_orca(bin_dir / "orca", "1.4.258")
    baseline_path = tmp_path / "orca-surface-baseline.json"
    baseline_path.write_text(
        json.dumps({"appVersion": "1.4.258"}), encoding="utf-8"
    )
    result = _run_surface(tmp_path, bin_dir, baseline_path)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "baseline missing minimumAppVersion" in result.stderr, result.stderr
