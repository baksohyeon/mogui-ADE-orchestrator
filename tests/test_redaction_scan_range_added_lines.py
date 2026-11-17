"""Range mode judges added lines (issue #331, item 1).

Before this fix, `--range` scanned the whole file and flagged any line on it,
so a finding already on the range's base blocked a change that added none of
its own. Measured case: a seat's lineage file carried 114-115 pre-existing
findings and blocked an append that added zero new ones.

Full-file and staged modes are not touched: they never read the added-lines
map built here, so every finding in them keeps blocking exactly as before.
"""

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
pytestmark = skip_windows_exec_surface


def _scan(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    env["HOME"] = str(repo.parent / "test-home")
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@requires_gitleaks
def test_range_mode_blocks_a_newly_added_secret_line(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "report.md").write_text("clean base line\n", encoding="utf-8")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add report")
    base = _head(repo)

    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write(f"{LEAK}\n")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add a secret")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "aws_access_key" in output, output
    assert "pre-existing" not in result.stdout, output


@requires_gitleaks
def test_range_mode_downgrades_a_pre_existing_secret_to_a_warning(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "report.md").write_text(f"{LEAK}\nclean base line\n", encoding="utf-8")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add report with an old secret")
    base = _head(repo)

    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write("a new clean append\n")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "append a clean line")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    # The default ruleset's own aws-access-token rule and this repo's
    # aws_access_key rule both match the same line, so one pre-existing
    # secret prints as two pre-existing findings.
    assert "pre-existing=2" in result.stdout, output
    assert "aws_access_key" in output, output
    assert "report.md" in output, output


@requires_gitleaks
def test_full_file_mode_still_blocks_the_same_pre_existing_secret(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "report.md").write_text(f"{LEAK}\nclean base line\n", encoding="utf-8")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add report with an old secret")
    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write("a new clean append\n")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "append a clean line")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "aws_access_key" in output, output


@requires_gitleaks
def test_range_mode_fails_closed_on_an_unreadable_binary_diff(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "blob.bin").write_bytes(b"AAAA\x00BBBB")
    _git(repo, "add", "blob.bin")
    _git(repo, "commit", "-q", "-m", "add binary")
    base = _head(repo)

    (repo / "blob.bin").write_bytes(b"CCCC\x00DDDD\x00EE")
    _git(repo, "add", "blob.bin")
    _git(repo, "commit", "-q", "-m", "change binary")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 2, output
    assert "blob.bin" in output, output


@requires_gitleaks
def test_range_mode_treats_a_pure_rename_as_fully_added_not_pre_existing(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "old_name.md").write_text(f"{LEAK}\n", encoding="utf-8")
    _git(repo, "add", "old_name.md")
    _git(repo, "commit", "-q", "-m", "add the old name with a secret")
    base = _head(repo)

    _git(repo, "mv", "old_name.md", "new_name.md")
    _git(repo, "commit", "-q", "-m", "rename only")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "new_name.md" in output, output
    assert "pre-existing" not in result.stdout, output


@requires_gitleaks
def test_range_mode_with_no_changed_files_stays_clean(tmp_path: Path) -> None:
    """A range that touches no files is not the same bug as an unreadable
    diff for a file the range does list: it must keep today's clean result,
    not fail closed over nothing to judge.
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    head = _head(repo)

    result = _scan(repo, "--range", f"{head}..{head}")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "files=0" in result.stdout, output


@requires_gitleaks
def test_range_mode_leaves_a_file_fully_blocking_when_the_tip_does_not_match_disk(
    tmp_path: Path,
) -> None:
    """gitleaks scans the file on disk, but the range's line numbers are
    computed against the range's own tip commit. An uncommitted edit made
    after that tip means a line number from the diff would not point at
    what gitleaks just read, so the file must get no entry in the
    added-lines map at all: every finding in it stays blocking, the same as
    outside range mode, instead of a judgment built on a mismatch (this is
    the only path that silently omits a file from the map, so it must never
    read as safe).
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "report.md").write_text(f"{LEAK}\nclean base line\n", encoding="utf-8")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add report with an old secret")
    base = _head(repo)

    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write("a new clean append\n")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "append a clean line")
    tip = _head(repo)

    # Uncommitted edit after the range's own tip: the working tree no
    # longer matches what "tip" names for this file.
    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write("an uncommitted edit after the tip\n")

    result = _scan(repo, "--range", f"{base}..{tip}")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "aws_access_key" in output, output
    assert "pre-existing" not in result.stdout, output


@requires_gitleaks
def test_range_mode_blocks_a_newly_added_secret_even_with_color_ui_always(
    tmp_path: Path,
) -> None:
    """The added-lines diff parser matches a hunk header at the start of a
    line; `color.ui always` prefixes it with an ANSI escape instead, which
    broke that match and left the file out of the added-lines map entirely,
    letting a newly added secret downgrade to a non-blocking warning
    (caught in review; confirmed with `git config color.ui always`).
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "report.md").write_text("clean base line\n", encoding="utf-8")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add report")
    base = _head(repo)
    _git(repo, "config", "color.ui", "always")

    with open(repo / "report.md", "a", encoding="utf-8") as handle:
        handle.write(f"{LEAK}\n")
    _git(repo, "add", "report.md")
    _git(repo, "commit", "-q", "-m", "add a secret")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "aws_access_key" in output, output
    assert "pre-existing" not in result.stdout, output


@requires_gitleaks
def test_range_mode_binary_marker_check_is_line_anchored(tmp_path: Path) -> None:
    """The binary-diff guard must match the marker line itself, not do an
    unanchored substring search over the whole diff text: this exact file's
    own source contains the words "Binary files " and " differ" nearby (as
    this docstring now does too), which previously made the check see its
    own diff as a binary file and fail closed on every range-mode run of
    this very commit (caught in review, reproduced with
    `scripts/redaction-scan.sh --range origin/main..HEAD` on this repo).
    This fixture pins a plain-text change that merely mentions both words
    without an actual binary marker line, and must still be judged normally.
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        "a note about diff output: Binary files can print a line ending in"
        " the word differ, but this is not that marker line\n",
        encoding="utf-8",
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "add report")
    base = _head(repo)

    with open(repo / "notes.md", "a", encoding="utf-8") as handle:
        handle.write(f"{LEAK}\n")
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "add a secret")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "aws_access_key" in output, output
