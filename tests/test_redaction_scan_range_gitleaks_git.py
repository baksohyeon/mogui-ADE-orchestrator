"""Range mode uses gitleaks git history as its blocking set.

The range scan deliberately keeps the tip file scan for warnings, but it no
longer joins tip line numbers to a separately parsed diff. That lets it catch a
finding added and deleted inside the range and avoids path, filter, and index
representations disagreeing about which line was added.
"""

from __future__ import annotations

import base64
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from test_redaction_scan_commit_messages import _git, _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface

requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks is not installed; the scanner requires it for real runs",
)
pytestmark = skip_windows_exec_surface


def _scan(
    repo: Path, *args: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    env["HOME"] = str(repo.parent / "test-home")
    if extra_env:
        env.update(extra_env)
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


def _aws_key() -> str:
    # The tail is generated from base32 bytes at test time, so no literal key
    # is stored in this public test file. Repeated bytes keep gitleaks' default
    # AWS rule from duplicating the repository-specific aws_access_key finding.
    tail = base64.b32encode(b"\0" * 10).decode("ascii").rstrip("=")
    assert len(tail) == 16
    return "AKIA" + tail


@requires_gitleaks
def test_range_mode_matches_the_gitleaks_git_measured_table(tmp_path: Path) -> None:
    """Pre-existing, added, crafted-name, and add-then-delete cases diverge."""
    repo = _repo_with_commits(tmp_path, ["base"])
    key = _aws_key()

    (repo / "a.txt").write_text(f"{key}\nbase line\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "add pre-existing key")
    base = _head(repo)

    with (repo / "a.txt").open("a", encoding="utf-8") as handle:
        handle.write("clean append\n")
    (repo / "b.txt").write_text(f"{key}\n", encoding="utf-8")
    crafted_dir = repo / "d"
    crafted_dir.mkdir()
    crafted = crafted_dir / ":(exclude)*notes"
    crafted.write_text(f"clean line\n{key}\n", encoding="utf-8")
    _git(repo, "add", "--", "a.txt", "b.txt", str(crafted.relative_to(repo)))
    _git(repo, "commit", "-q", "-m", "add current keys")

    (repo / "c.txt").write_text(f"{key}\n", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-q", "-m", "add then delete key")
    _git(repo, "rm", "-q", "c.txt")
    _git(repo, "commit", "-q", "-m", "delete key from tip")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "pre-existing=1" in output, output
    assert "a.txt" in output, output
    assert "b.txt" in output, output
    assert crafted.name in output, output
    assert "c.txt" in output, output
    assert "aws_access_key" in output, output


@requires_gitleaks
def test_range_mode_keeps_a_pre_existing_finding_as_a_warning_in_an_edited_file(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    key = _aws_key()
    (repo / "a.txt").write_text(f"{key}\nbase line\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "add old key")
    base = _head(repo)

    with (repo / "a.txt").open("a", encoding="utf-8") as handle:
        handle.write("clean append\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "edit old-key file")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "pre-existing=1" in result.stdout, output
    assert "a.txt" in output, output


@requires_gitleaks
def test_range_mode_blocks_tip_content_on_a_named_filter_path(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    key = _aws_key()
    store = repo / "filter-store"
    store.mkdir()
    filters_dir = repo / ".git" / "filters"
    filters_dir.mkdir()
    (filters_dir / "clean.sh").write_text(
        "#!/bin/bash\nwc -c | awk '{print \"oid:\" $1}'\n", encoding="utf-8"
    )
    (filters_dir / "smudge.sh").write_text(
        "#!/bin/bash\nread -r line\noid=\"${line#oid:}\"\n"
        f'cat "{store}/$oid"\n',
        encoding="utf-8",
    )
    (filters_dir / "clean.sh").chmod(0o755)
    (filters_dir / "smudge.sh").chmod(0o755)
    _git(repo, "config", "filter.toy.clean", str(filters_dir / "clean.sh"))
    _git(repo, "config", "filter.toy.smudge", str(filters_dir / "smudge.sh"))
    _git(repo, "config", "filter.toy.required", "true")
    (repo / ".gitattributes").write_text("filtered.dat filter=toy\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-q", "-m", "add filter attribute")

    old_content = "safe one\nsafe two\n"
    (store / str(len(old_content))).write_text(old_content, encoding="utf-8")
    (repo / "filtered.dat").write_text(old_content, encoding="utf-8")
    _git(repo, "add", "filtered.dat")
    _git(repo, "commit", "-q", "-m", "add filtered file")
    base = _head(repo)

    new_content = f"safe one\nsafe two\n{key}\n"
    (store / str(len(new_content))).write_text(new_content, encoding="utf-8")
    (repo / "filtered.dat").unlink()
    (repo / "filtered.dat").write_text(new_content, encoding="utf-8")
    _git(repo, "add", "filtered.dat")
    _git(repo, "commit", "-q", "-m", "update filtered file")
    (repo / "filtered.dat").unlink()
    _git(repo, "checkout", "-q", "--", "filtered.dat")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "filtered.dat" in output, output
    assert "pre-existing" not in result.stdout, output


@requires_gitleaks
def test_range_mode_honours_a_file_rule_line_gitleaksignore_exemption(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    key = _aws_key()
    (repo / ".gitleaksignore").write_text(
        "b.txt:aws_access_key:1\n", encoding="utf-8"
    )
    _git(repo, "add", ".gitleaksignore")
    _git(repo, "commit", "-q", "-m", "configure finding exemption")
    base = _head(repo)

    (repo / "b.txt").write_text(f"{key}\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "add exempted key")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "findings" in result.stdout
    assert "b.txt" not in output, output


@requires_gitleaks
def test_range_mode_missing_commit_fails_with_a_named_reason(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    result = _scan(repo, "--range", "missing-range-commit..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 2, output
    assert "range does not resolve" in output, output


@requires_gitleaks
def test_range_mode_with_no_changed_files_stays_clean(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    head = _head(repo)

    result = _scan(repo, "--range", f"{head}..{head}")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "files=0" in result.stdout, output


@requires_gitleaks
def test_range_mode_includes_a_merge_commit_resolution_diff(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "shared.txt")
    _git(repo, "commit", "-q", "-m", "add shared file")
    base = _head(repo)
    main_branch = _git(repo, "branch", "--show-current").stdout.strip()

    _git(repo, "switch", "-c", "feature")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-q", "-m", "add feature file")

    _git(repo, "switch", main_branch)
    (repo / "main.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "add", "main.txt")
    _git(repo, "commit", "-q", "-m", "add main file")
    _git(repo, "merge", "--no-ff", "--no-commit", "feature")
    (repo / "merge-resolution.txt").write_text(
        f"{_aws_key()}\n", encoding="utf-8"
    )
    _git(repo, "add", "merge-resolution.txt")
    _git(repo, "commit", "-q", "-m", "resolve merge")

    result = _scan(repo, "--range", f"{base}..HEAD")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "merge-resolution.txt" in output, output
    assert "aws_access_key" in output, output


@requires_gitleaks
def test_range_mode_fails_closed_on_a_malformed_range_report(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "changed.txt").write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "changed.txt")
    _git(repo, "commit", "-q", "-m", "change file")
    base = _head(repo)

    real_gitleaks = shutil.which("gitleaks")
    assert real_gitleaks is not None
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_gitleaks = fake_bin / "gitleaks"
    fake_gitleaks.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "git" ]; then\n'
        '  previous=""\n'
        '  for arg in "$@"; do\n'
        '    if [ "$previous" = "--report-path" ]; then\n'
        '      printf "%s" "malformed" > "$arg"\n'
        "      exit 0\n"
        "    fi\n"
        '    previous="$arg"\n'
        "  done\n"
        "fi\n"
        f"exec {shlex.quote(real_gitleaks)} \"$@\"\n",
        encoding="utf-8",
    )
    fake_gitleaks.chmod(0o755)

    result = _scan(
        repo,
        "--range",
        f"{base}..HEAD",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )
    output = result.stdout + result.stderr

    assert result.returncode == 2, output
    assert "could not classify range findings" in output, output
    assert "could not parse range gitleaks report" in output, output
