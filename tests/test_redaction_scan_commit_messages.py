"""Commit-message scope tests for scripts/redaction-scan.sh.

The file scan never saw commit messages, which are content this repository
publishes. An internal name sat in four of them while the gate stayed green and a
person found it by eye. These tests pin both halves: messages are scanned when a
range is given, and the summary says so when they were not.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN = REPO_ROOT / "scripts" / "redaction-scan.sh"
CONFIG = REPO_ROOT / "config" / "gitleaks.toml"

# Matches the scanner's own aws_access_key rule. The canonical
# AKIAIOSFODNN7EXAMPLE cannot be used because the placeholder list excuses it on
# purpose, and a whole literal here would be a finding in this file: joined at
# runtime so the fixture needs no allowlist entry to silence it.
LEAK = "AKIA" + "2QJZ7NVXH4KDPLMB"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, env=env, capture_output=True, text=True
    )


def _repo_with_commits(tmp_path: Path, messages: list[str]) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    _git(repo, "init", "-q")
    # The scanner resolves its repository from its own location and cd's there, so
    # a test repository has to carry a copy of the script. That is also the shape a
    # real installation has. The scanner skips itself and its allowlist.
    (repo / "scripts" / "redaction-scan.sh").write_text(
        SCAN.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / "scripts" / "redaction-allowlist.txt").write_text("", encoding="utf-8")
    # The wrapper reads its gitleaks config from the repository it lives in.
    (repo / "config").mkdir()
    (repo / "config" / "gitleaks.toml").write_text(
        CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git(repo, "add", "scripts", "config")
    _git(repo, "commit", "-q", "-m", "carry the scanner")
    for index, message in enumerate(messages):
        (repo / f"f{index}.md").write_text(f"file {index}\n", encoding="utf-8")
        _git(repo, "add", f"f{index}.md")
        _git(repo, "commit", "-q", "-m", message)
    return repo


def _scan(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_tracked_mode_says_commit_messages_were_not_scanned(tmp_path: Path) -> None:
    """A green line must name what it did not look at."""

    repo = _repo_with_commits(tmp_path, ["first commit", "second commit"])
    result = _scan(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "commit-messages=not-scanned" in result.stdout


def test_range_mode_scans_commit_messages_and_finds_a_leak(tmp_path: Path) -> None:
    repo = _repo_with_commits(
        tmp_path, ["clean first", f"add key {LEAK} by mistake", "clean third"]
    )
    result = _scan(repo, "--range", "HEAD~2..HEAD")
    output = result.stdout + result.stderr
    # Findings print to stderr; the summary lines print to stdout.
    assert result.returncode != 0, output
    assert "commit:" in output, output
    assert "aws_access_key" in output, output


def test_commit_messages_flag_works_outside_range_mode(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["clean", f"leak {LEAK} here"])
    result = _scan(repo, "--commit-messages", "HEAD~1..HEAD")
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "commit:" in output, output


def test_clean_commit_messages_report_the_count_scanned(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["clean one", "clean two", "clean three"])
    result = _scan(repo, "--range", "HEAD~2..HEAD")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "commit-messages=2" in result.stdout


def test_commit_messages_flag_requires_a_range(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["only commit"])
    result = _scan(repo, "--commit-messages")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "requires a git range" in result.stderr
