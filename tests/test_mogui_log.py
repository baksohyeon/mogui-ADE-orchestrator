"""Regression coverage for master-ops/scripts/mogui_log.py's `_session_kind`.

mogui_log.py is self-contained stdlib-only (no local imports of its own), so
it is imported directly off sys.path rather than via runpy, unlike
worker-wait (which forks argparse/module-level constants that runpy's
snapshot semantics would otherwise fight).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "master-ops" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import mogui_log  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MOGUI_SEAT_ROOT", raising=False)
    monkeypatch.delenv("ORCA_TASK_ID", raising=False)
    # _session_kind() caches its result at module level for the life of a
    # process; each test is its own "process" here, so start uncached.
    monkeypatch.setattr(mogui_log, "_SESSION_KIND_CACHE", None)


def test_seat_root_env_var_match_is_master(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOGUI_SEAT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert mogui_log._session_kind() == "master"
    # Failability: a cwd that does not match the seat root must not be master.
    # (Reset the per-process cache: a real process never changes cwd mid-run,
    # but this test does, across what the cache treats as one process.)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setattr(mogui_log, "_SESSION_KIND_CACHE", None)
    assert mogui_log._session_kind() == "unknown"


def test_descriptor_workspace_root_match_is_master(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "workspace-descriptor.json").write_text(
        json.dumps({"workspace_root": str(tmp_path)}), encoding="utf-8"
    )
    monkeypatch.setattr(mogui_log, "_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert mogui_log._session_kind() == "master"
    # Failability: a descriptor naming a different root must not read master here.
    (tmp_path / "config" / "workspace-descriptor.json").write_text(
        json.dumps({"workspace_root": str(tmp_path / "not-here")}), encoding="utf-8"
    )
    monkeypatch.setattr(mogui_log, "_SESSION_KIND_CACHE", None)
    assert mogui_log._session_kind() == "unknown"


def test_descriptor_is_found_via_runtime_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    """The descriptor lives next to the script (its runtime root), not in
    the caller's cwd — a master running from a different directory than the
    ops/runtime repo must still be classified correctly."""
    runtime_root = tmp_path / "ops-repo"
    (runtime_root / "config").mkdir(parents=True)
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (runtime_root / "config" / "workspace-descriptor.json").write_text(
        json.dumps({"workspace_root": str(workspace_root)}), encoding="utf-8"
    )
    monkeypatch.setattr(mogui_log, "_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.chdir(workspace_root)

    assert mogui_log._session_kind() == "master"
    # Failability: a version that read <cwd>/config/... instead of the
    # runtime root would find nothing under workspace_root and fall through
    # to "unknown" here.


def test_worker_cwd_without_seat_match_is_worker(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "repo" / ".orca" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    monkeypatch.chdir(worktree)
    assert mogui_log._session_kind() == "worker"


def test_orca_task_id_env_var_is_worker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORCA_TASK_ID", "task_x")
    assert mogui_log._session_kind() == "worker"


def test_no_seat_match_and_no_worker_signal_is_unknown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert mogui_log._session_kind() == "unknown"


def test_malformed_descriptor_is_swallowed_not_raised(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "workspace-descriptor.json").write_text(
        "not json", encoding="utf-8"
    )
    monkeypatch.setattr(mogui_log, "_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert mogui_log._session_kind() == "unknown"


def test_emit_stamps_session_kind_from_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mogui_log, "LOG_DIR", str(tmp_path))
    monkeypatch.setenv("MOGUI_SEAT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    line = mogui_log.emit("info", "test_event", "pass")
    assert line["session_kind"] == "master"
