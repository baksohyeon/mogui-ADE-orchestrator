from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).parents[1] / "scripts" / "cursor-worker-pretrust"


def run_pretrust(
    worktree_path: str,
    projects_dir: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), worktree_path, "--projects-dir", str(projects_dir)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def trusted_file(projects_dir: Path, worktree_path: str) -> Path:
    key = worktree_path.removeprefix("/").replace("/", "-").replace(".", "")
    return projects_dir / key / ".workspace-trusted"


def test_fresh_add_writes_dot_stripped_project_key(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / ".orca" / "worktrees" / "repo" / "feature.with.dot"
    workspace.mkdir(parents=True)

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 0, result.stderr
    assert "trusted (added)" in result.stdout
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    trust_path = trusted_file(projects_dir, str(workspace))
    marker = json.loads(trust_path.read_text(encoding="utf-8"))
    assert marker["workspacePath"] == str(workspace)
    assert isinstance(marker["trustedAt"], str) and marker["trustedAt"]


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / ".orca" / "worktrees" / "repo" / "branch"
    workspace.mkdir(parents=True)

    first = run_pretrust(str(workspace), projects_dir)
    trust_path = trusted_file(projects_dir, str(workspace))
    after_first = trust_path.read_bytes()
    second = run_pretrust(str(workspace), projects_dir)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert trust_path.read_bytes() == after_first
    assert "already trusted" in second.stdout
    assert "Summary: 0 added, 0 updated, 1 already trusted" in second.stdout


def test_existing_marker_missing_trusted_at_is_updated(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    trust_path = trusted_file(projects_dir, str(workspace))
    trust_path.parent.mkdir(parents=True)
    trust_path.write_text(
        json.dumps({"workspacePath": str(workspace)}, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 0, result.stderr
    assert "trusted (updated)" in result.stdout
    assert "Summary: 0 added, 1 updated, 0 already trusted" in result.stdout
    marker = json.loads(trust_path.read_text(encoding="utf-8"))
    assert marker["workspacePath"] == str(workspace)
    assert isinstance(marker["trustedAt"], str) and marker["trustedAt"]


def test_missing_worktree_path_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing-worktree"
    projects_dir = tmp_path / "projects"

    result = run_pretrust(str(missing), projects_dir)

    assert result.returncode == 2
    assert "worktree path does not exist" in result.stderr
    assert not trusted_file(projects_dir, str(missing)).exists()


def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust("relative/worktree", tmp_path / "projects")

    assert result.returncode == 2
    assert "worktree path must be absolute" in result.stderr


def test_malformed_marker_aborts_without_writing(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    trust_path = trusted_file(projects_dir, str(workspace))
    trust_path.parent.mkdir(parents=True)
    original = "{\n"
    trust_path.write_text(original, encoding="utf-8")

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert f"ERROR {trust_path}: cannot parse trust marker JSON" in result.stderr
    assert trust_path.read_text(encoding="utf-8") == original


def test_workspace_path_mismatch_aborts_without_writing(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    trust_path = trusted_file(projects_dir, str(workspace))
    trust_path.parent.mkdir(parents=True)
    original = {
        "trustedAt": "2026-08-03T13:26:25.108Z",
        "workspacePath": str(tmp_path / "different-worktree"),
    }
    trust_path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert "workspacePath mismatch in existing trust marker" in result.stderr
    assert json.loads(trust_path.read_text(encoding="utf-8")) == original


def test_no_python_interpreter_skips_without_writing(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    (shim_bin / "bash").symlink_to("/bin/bash")
    env = os.environ.copy()
    env["PATH"] = str(shim_bin)

    result = run_pretrust(str(workspace), projects_dir, env=env)

    assert result.returncode == 0
    assert "SKIP no Python 3 interpreter with json support found" in result.stdout
    assert "SKIP no Python 3 interpreter with json support found" in result.stderr
    assert "Summary: skipped — 0 added, 0 updated, 0 already trusted" in result.stdout
    assert not trusted_file(projects_dir, str(workspace)).exists()
