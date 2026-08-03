from __future__ import annotations

from windows_exec_surface import skip_windows_exec_surface
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


def resolved_tmp(tmp_path: Path) -> Path:
    """Use the real path so symlink ancestors (macOS /var -> /private/var) do not trip hardening."""
    return tmp_path.resolve()


def test_trusted_file_matches_measured_literal_key_shape() -> None:
    projects_dir = Path("/tmp/projects-root")
    assert trusted_file(
        projects_dir,
        "/tmp/.orca/worktrees/repo/feature.with.dot",
    ) == Path(
        "/tmp/projects-root/tmp-orca-worktrees-repo-featurewithdot/.workspace-trusted"
    )


@skip_windows_exec_surface
def test_fresh_add_writes_dot_stripped_project_key(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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


@skip_windows_exec_surface
def test_second_run_is_idempotent(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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


@skip_windows_exec_surface
def test_existing_marker_missing_trusted_at_is_updated(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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


@skip_windows_exec_surface
def test_missing_worktree_path_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    missing = tmp_path / "missing-worktree"
    projects_dir = tmp_path / "projects"

    result = run_pretrust(str(missing), projects_dir)

    assert result.returncode == 2
    assert "worktree path does not exist" in result.stderr
    assert not trusted_file(projects_dir, str(missing)).exists()


@skip_windows_exec_surface
def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    result = run_pretrust("relative/worktree", tmp_path / "projects")

    assert result.returncode == 2
    assert "worktree path must be absolute" in result.stderr


@skip_windows_exec_surface
def test_malformed_marker_aborts_without_writing(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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


@skip_windows_exec_surface
def test_workspace_path_mismatch_aborts_without_writing(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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


@skip_windows_exec_surface
def test_symlinked_project_path_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / ".orca" / "worktrees" / "repo" / "branch"
    workspace.mkdir(parents=True)
    key = str(workspace).removeprefix("/").replace("/", "-").replace(".", "")
    target = tmp_path / "outside"
    target.mkdir()
    projects_dir.mkdir()
    (projects_dir / key).symlink_to(target, target_is_directory=True)

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert "trust marker path must not use symlinks" in result.stderr
    assert not (target / ".workspace-trusted").exists()


@skip_windows_exec_surface
def test_symlinked_projects_dir_ancestor_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    projects_dir = linked_root / "projects"

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert "trust marker path must not use symlinks" in result.stderr
    assert not (real_root / "projects").exists()


@skip_windows_exec_surface
def test_symlinked_projects_dir_with_trailing_slash_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    real_root = tmp_path / "real-projects"
    real_root.mkdir()
    linked = tmp_path / "linked-projects"
    linked.symlink_to(real_root, target_is_directory=True)
    projects_dir = Path(str(linked) + "/")

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert "trust marker path must not use symlinks" in result.stderr
    assert not any(real_root.rglob(".workspace-trusted"))


@skip_windows_exec_surface
def test_non_regular_marker_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    trust_path = trusted_file(projects_dir, str(workspace))
    trust_path.parent.mkdir(parents=True)
    trust_path.mkdir()

    result = run_pretrust(str(workspace), projects_dir)

    assert result.returncode == 2
    assert "trust marker is not a regular file" in result.stderr
    assert trust_path.is_dir()


@skip_windows_exec_surface
def test_versioned_python_candidate_is_accepted(tmp_path: Path) -> None:
    import sys

    tmp_path = resolved_tmp(tmp_path)
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    probe_log = tmp_path / "probes.log"
    (shim_bin / "bash").symlink_to("/bin/bash")

    for disqualified in ("python3", "python3.14", "python3.13"):
        failing = shim_bin / disqualified
        failing.write_text(
            f'#!/bin/sh\necho {disqualified} >> "{probe_log}"\nexit 1\n',
            encoding="utf-8",
        )
        failing.chmod(0o755)

    qualifying = shim_bin / "python3.12"
    qualifying.write_text(
        f'#!/bin/sh\necho python3.12 >> "{probe_log}"\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    qualifying.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(shim_bin)

    result = run_pretrust(str(workspace), projects_dir, env=env)

    assert result.returncode == 0, result.stderr
    assert "trusted (added)" in result.stdout
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    probes = probe_log.read_text(encoding="utf-8").split()
    assert probes[:4] == ["python3", "python3.14", "python3.13", "python3.12"]


@skip_windows_exec_surface
def test_only_python310_candidate_is_accepted(tmp_path: Path) -> None:
    import sys

    tmp_path = resolved_tmp(tmp_path)
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    probe_log = tmp_path / "probes.log"
    (shim_bin / "bash").symlink_to("/bin/bash")

    for disqualified in (
        "python3",
        "python3.14",
        "python3.13",
        "python3.12",
        "python3.11",
    ):
        failing = shim_bin / disqualified
        failing.write_text(
            f'#!/bin/sh\necho {disqualified} >> "{probe_log}"\nexit 1\n',
            encoding="utf-8",
        )
        failing.chmod(0o755)

    qualifying = shim_bin / "python3.10"
    qualifying.write_text(
        f'#!/bin/sh\necho python3.10 >> "{probe_log}"\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    qualifying.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(shim_bin)

    result = run_pretrust(str(workspace), projects_dir, env=env)

    assert result.returncode == 0, result.stderr
    assert "trusted (added)" in result.stdout
    probes = probe_log.read_text(encoding="utf-8").split()
    assert probes[-1] == "python3.10"
    assert "python3.10" in probes


@skip_windows_exec_surface
def test_no_python_interpreter_skips_without_writing(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
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
    assert "SKIP no Python 3.6+ interpreter with json support found" in result.stdout
    assert "SKIP no Python 3.6+ interpreter with json support found" in result.stderr
    assert "Summary: skipped — 0 added, 0 updated, 0 already trusted" in result.stdout
    assert not trusted_file(projects_dir, str(workspace)).exists()


@skip_windows_exec_surface
def test_python_candidate_below_minimum_is_rejected(tmp_path: Path) -> None:
    tmp_path = resolved_tmp(tmp_path)
    projects_dir = tmp_path / "projects"
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    (shim_bin / "bash").symlink_to("/bin/bash")
    python_shim = shim_bin / "python"
    # Accept major version 3 + json but fail the minimum capability probe.
    python_shim.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        "  case \"$2\" in\n"
        "    *\"sys.version_info >= (3, 6)\"*) exit 1 ;;\n"
        "    *\"version_info[0] >= 3\"*) exit 0 ;;\n"
        "  esac\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    python_shim.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(shim_bin)

    result = run_pretrust(str(workspace), projects_dir, env=env)

    assert result.returncode == 0
    assert "SKIP no Python 3.6+ interpreter with json support found" in result.stdout
    assert "Summary: skipped — 0 added, 0 updated, 0 already trusted" in result.stdout
    assert not trusted_file(projects_dir, str(workspace)).exists()
