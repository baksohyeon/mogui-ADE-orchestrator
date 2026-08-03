"""Romanized-only organization rules get a warning.

A rule set that spells an identifier only in its romanized form misses the
same identifier in its native spelling; measured live when a Korean name
passed a scan whose rules only knew its romanization. The scan cannot know
the missing name, but it can see that no loaded rule contains a single
character outside ASCII and say so.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_redaction_scan_commit_messages import _repo_with_commits

WARNING = "organization rules contain no native script pattern"


def _scan_with_extra(repo: Path, extra: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "REDACTION_EXTRA_PATTERNS": str(extra)}
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    return subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_romanized_only_rules_warn(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x|Personal identifier|(?i)romanizedname\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert WARNING in result.stderr
    assert result.returncode == 0


def test_native_script_rule_silences_warning(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x|Personal identifier|(?i)romanizedname\n"
        "person_x_ko|Personal identifier native|가나다\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert WARNING not in result.stderr
    assert result.returncode == 0


def test_no_org_rules_means_no_native_warning(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    env.pop("REDACTION_REQUIRE_EXTRA", None)
    result = subprocess.run(
        ["bash", str(repo / "scripts" / "redaction-scan.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert WARNING not in result.stderr


def test_escaped_native_range_silences_warning(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x|Personal identifier|(?i)romanizedname\n"
        "person_x_native|Personal identifier native|[\\uac00-\\ud7af]{2,4}\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert WARNING not in result.stderr
