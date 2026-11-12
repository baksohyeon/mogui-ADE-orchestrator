"""Workspace-root organization rules and profile behaviour."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_redaction_scan_commit_messages import LEAK, _git, _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface

requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks is not installed; the scanner requires it for real runs",
)
pytestmark = [requires_gitleaks, skip_windows_exec_surface]

SCAN_NAME = "scripts/redaction-scan.sh"


def _scan(
    repo: Path,
    *,
    env_extra: dict[str, str] | None = None,
    args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    for key in (
        "REDACTION_EXTRA_PATTERNS",
        "REDACTION_REQUIRE_EXTRA",
        "REDACTION_PROFILE",
        "REDACTION_REPO_ROOT",
        "REDACTION_WORKSPACE_ROOT",
    ):
        env.pop(key, None)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(repo / SCAN_NAME), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_workspace_root_rules_load_without_environment_override(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    (tmp_path / ".redaction-extra.txt").write_text(
        "org_workspace|workspace marker|WORKSPACE_MARKER\n", encoding="utf-8"
    )

    result = _scan(repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "org-rules=1" in result.stdout
    assert "org-rules-source=workspace-root" in result.stdout
    assert "profile=export" in result.stdout
    assert "export-only-skipped=0" in result.stdout


def test_help_includes_the_complete_exemptions_paragraph(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])

    result = _scan(repo, args=("--help",))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Exemptions use gitleaks' own mechanisms" in result.stdout
    assert result.stdout.rstrip().endswith(
        "finding, or config/gitleaks.toml for a whole class."
    )


def test_legacy_home_rules_remain_the_fallback(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".config" / "redaction-extra.txt").write_text(
        "org_legacy|legacy marker|LEGACY_MARKER\n", encoding="utf-8"
    )

    result = _scan(repo, env_extra={"HOME": str(home)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "org-rules=1" in result.stdout
    assert "org-rules-source=legacy-home" in result.stdout


def test_linked_worktree_uses_the_main_checkout_workspace_root(tmp_path: Path) -> None:
    main = _repo_with_commits(tmp_path, ["plain change"])
    linked = tmp_path / ".orca" / "worktrees" / "linked"
    linked.parent.mkdir(parents=True)
    _git(main, "worktree", "add", "--detach", str(linked), "HEAD")
    (tmp_path / ".redaction-extra.txt").write_text(
        "org_linked|linked marker|LINKED_MARKER\n", encoding="utf-8"
    )

    result = _scan(main, env_extra={"REDACTION_REPO_ROOT": str(linked)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "org-rules=1" in result.stdout
    assert "org-rules-source=workspace-root" in result.stdout


def test_explicit_workspace_root_overrides_git_layout(tmp_path: Path) -> None:
    main = _repo_with_commits(tmp_path, ["plain change"])
    linked = tmp_path / ".orca" / "worktrees" / "linked"
    linked.parent.mkdir(parents=True)
    _git(main, "worktree", "add", "--detach", str(linked), "HEAD")
    declared_root = tmp_path / "declared-workspace"
    declared_root.mkdir()
    (declared_root / ".redaction-extra.txt").write_text(
        "org_override|override marker|OVERRIDE_MARKER\n", encoding="utf-8"
    )

    result = _scan(
        main,
        env_extra={
            "REDACTION_REPO_ROOT": str(linked),
            "REDACTION_WORKSPACE_ROOT": str(declared_root),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "org-rules=1" in result.stdout
    assert "org-rules-source=workspace-root" in result.stdout


def test_environment_rules_win_over_workspace_root(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    (tmp_path / ".redaction-extra.txt").write_text(
        "workspace_rule|workspace marker|WORKSPACE_MARKER\n"
        "workspace_second|second marker|SECOND_MARKER\n",
        encoding="utf-8",
    )
    env_rules = tmp_path / "env-rules.txt"
    env_rules.write_text("env_rule|environment marker|ENV_MARKER\n", encoding="utf-8")

    result = _scan(repo, env_extra={"REDACTION_EXTRA_PATTERNS": str(env_rules)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "org-rules=1" in result.stdout
    assert "org-rules-source=env" in result.stdout


def test_internal_profile_skips_workspace_rules_and_export_loads_them(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    marker = repo / "marker.txt"
    marker.write_text("WORKSPACE_MARKER\n", encoding="utf-8")
    _git(repo, "add", "marker.txt")
    _git(repo, "commit", "-q", "-m", "marker")
    (tmp_path / ".redaction-extra.txt").write_text(
        "workspace_rule|workspace marker|WORKSPACE_MARKER\n", encoding="utf-8"
    )

    internal = _scan(repo, env_extra={"REDACTION_PROFILE": "internal"}, args=("-v",))
    export = _scan(repo, env_extra={"REDACTION_PROFILE": "export"}, args=("-v",))
    default = _scan(repo, args=("-v",))

    assert internal.returncode == 0, internal.stdout + internal.stderr
    assert "org-rules=0" in internal.stdout
    assert "export-only-skipped=1" in internal.stdout
    assert "profile=internal" in internal.stdout
    assert export.returncode == 1, export.stdout + export.stderr
    assert "workspace_rule" in export.stderr
    assert "profile=export" in export.stdout
    assert default.returncode == 1, default.stdout + default.stderr
    assert "workspace_rule" in default.stderr


def test_generic_and_credential_findings_fail_in_both_profiles(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    marker = repo / "marker.txt"
    marker.write_text(f"WORKSPACE_MARKER {LEAK}\n", encoding="utf-8")
    _git(repo, "add", "marker.txt")
    _git(repo, "commit", "-q", "-m", "marker")
    (tmp_path / ".redaction-extra.txt").write_text(
        "workspace_rule|workspace marker|WORKSPACE_MARKER\n", encoding="utf-8"
    )

    for profile in ("internal", "export"):
        result = _scan(repo, env_extra={"REDACTION_PROFILE": profile})
        assert result.returncode == 1, result.stdout + result.stderr
        assert "aws_access_key" in result.stderr


def test_missing_rules_warning_names_both_default_paths(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    home = tmp_path / "home"

    result = _scan(
        repo,
        env_extra={
            "HOME": str(home),
            "REDACTION_REQUIRE_EXTRA": "1",
        },
    )

    output = result.stdout + result.stderr
    assert result.returncode == 2, output
    assert str(tmp_path / ".redaction-extra.txt") in output
    assert str(home / ".config" / "redaction-extra.txt") in output
