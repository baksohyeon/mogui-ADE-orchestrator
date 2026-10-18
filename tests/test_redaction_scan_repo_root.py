"""`--repo-root` / `REDACTION_REPO_ROOT` scope scripts/redaction-scan.sh to a target.

The script fixed its working directory to its own repository (`SCRIPT_DIR/..`,
then `cd`), so a caller in another repository running it with `--staged` scanned
this repository's index, which is empty, and read `clean` with `files=0`.
Measured 2026-10-18 by the peer seat: its gate wired this script as its staged
credential lane and that lane scanned nothing since; gitleaks run directly on the
same staged file found the planted key. These tests pin the fix: an explicit
target, the rules still resolved against the script's own repository, and the
target named in the summary line's `root=`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_redaction_scan_commit_messages import LEAK, _git, _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface


def _toplevel(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _target_repo_with_staged_key(tmp_path: Path) -> Path:
    """A plain git repository, no scanner of its own, with a staged secret."""

    target = tmp_path / "target"
    target.mkdir()
    _git(target, "init", "-q")
    (target / "notes.txt").write_text("nothing here\n", encoding="utf-8")
    _git(target, "add", "notes.txt")
    _git(target, "commit", "-q", "-m", "seed")
    (target / "secret.txt").write_text(f"token {LEAK}\n", encoding="utf-8")
    _git(target, "add", "secret.txt")
    return target


def _scan(repo: Path, args: list[str], *, env_extra: dict[str, str] | None = None):
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    env.pop("REDACTION_REPO_ROOT", None)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_repo_root_flag_scans_the_named_target(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    target = _target_repo_with_staged_key(tmp_path)
    result = _scan(repo, ["--staged", "--repo-root", str(target)])
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "secret.txt" in output, output
    assert f"root={_toplevel(target)}" in output, output


def test_repo_root_env_var_scans_the_named_target(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    target = _target_repo_with_staged_key(tmp_path)
    result = _scan(
        repo, ["--staged"], env_extra={"REDACTION_REPO_ROOT": str(target)}
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "secret.txt" in output, output
    assert f"root={_toplevel(target)}" in output, output


def test_repo_root_flag_wins_over_env_var(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    target = _target_repo_with_staged_key(tmp_path)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _git(decoy, "init", "-q")
    (decoy / "f.txt").write_text("plain\n", encoding="utf-8")
    _git(decoy, "add", "f.txt")
    _git(decoy, "commit", "-q", "-m", "seed")
    result = _scan(
        repo,
        ["--staged", "--repo-root", str(target)],
        env_extra={"REDACTION_REPO_ROOT": str(decoy)},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert f"root={_toplevel(target)}" in output, output


def test_repo_root_pointing_at_the_scanners_own_repository_is_old_behaviour(
    tmp_path: Path,
) -> None:
    """Explicitly naming the scanner's own repository as the target is a no-op."""

    repo = _repo_with_commits(tmp_path, ["plain change"])
    result = _scan(repo, ["--staged", "--repo-root", str(repo)])
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "files=0" in output, output
    assert f"root={_toplevel(repo)}" in output, output


def test_no_flag_no_variable_scans_the_scripts_own_repository(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    result = _scan(repo, [])
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert f"root={_toplevel(repo)}" in output, output


def test_repo_root_outside_a_git_work_tree_exits_2_before_any_scan(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    outside = tmp_path / "plain-dir"
    outside.mkdir()
    result = _scan(repo, ["--repo-root", str(outside)])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert "--repo-root" in result.stderr
    assert str(outside) in result.stderr
