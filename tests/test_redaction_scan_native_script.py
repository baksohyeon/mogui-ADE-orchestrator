"""Romanization only organization rules get a warning.

A rule set that spells an identifier only in its romanized form misses the
same identifier in its native spelling; measured live when a Korean name
passed a scan whose rules only knew its romanization. The scan cannot know
the missing name, but it can see that no loaded rule contains a single
character outside ASCII and say so.

The detector reads literal characters only, and that is not a shortcut: no
escape spelling of a native codepoint survives this pipeline. The loader's
`re.compile` gate drops RE2's brace and property forms as unusable, and the
engine canary exits 2 on Python's backslash-u form before anything scans.
Two tests below pin those exclusions so a future escape-detection "fix"
has to reckon with them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_redaction_scan_commit_messages import _repo_with_commits

from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface

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
    assert result.returncode == 0
    assert WARNING in result.stderr


def test_native_script_rule_silences_warning(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x|Personal identifier|(?i)romanizedname\n"
        "person_x_ko|Personal identifier native|가나다\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert result.returncode == 0
    assert WARNING not in result.stderr


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
    assert result.returncode == 0
    assert WARNING not in result.stderr


def test_python_u_escape_rule_dies_at_the_engine_canary(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x_native|Personal identifier native|[\\uac00-\\ud7af]{2,4}\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert result.returncode == 2
    assert "not supported by RE2" in result.stderr
    assert "person_x_native" in result.stderr


def test_property_class_rule_is_dropped_as_unusable(tmp_path: Path) -> None:
    repo = _repo_with_commits(tmp_path, ["plain change"])
    extra = tmp_path / "extra.txt"
    extra.write_text(
        "person_x|Personal identifier|(?i)romanizedname\n"
        "person_x_native|Personal identifier native|\\p{Hangul}{2,4}\n",
        encoding="utf-8",
    )
    result = _scan_with_extra(repo, extra)
    assert result.returncode == 0
    assert "1 of 2 organization rule lines are unusable" in result.stderr
    assert WARNING in result.stderr
