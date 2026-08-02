"""Tests for scripts/redaction-inventory.

The script had none, which is the defect it exists to prevent: a green result
that cannot be told apart from having read nothing. Each case below drives the
real script in a temporary git repository and asserts the exit code, because the
exit code is what the publish gate consumes.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY = REPO_ROOT / "scripts" / "redaction-inventory"

GOOD_RULE = "acme|Acme internal name|acme-[a-z]+"


def _git_repo(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    for name, body in (files or {}).items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=repo, check=True, env=env)
    return repo


def _rules(tmp_path: Path, *lines: str, name: str = "rules.txt") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(repo: Path, rules: Path | None, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ}
    env.pop("REDACTION_EXTRA_PATTERNS", None)
    if rules is not None:
        env["REDACTION_EXTRA_PATTERNS"] = str(rules)
    return subprocess.run(
        ["python3", str(INVENTORY), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_unset_pattern_file_cannot_decide(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "nothing here\n"})
    result = _run(repo, None)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REDACTION_EXTRA_PATTERNS is unset" in result.stderr


def test_pattern_file_with_no_usable_rule_cannot_decide(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "nothing here\n"})
    rules = _rules(tmp_path, "# only a comment", "")
    result = _run(repo, rules)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No rules could be read" in result.stderr


def test_unusable_rule_lines_are_reported_not_dropped_in_silence(
    tmp_path: Path,
) -> None:
    """A narrowed rule set must say it narrowed."""

    repo = _git_repo(tmp_path, {"a.md": "plain prose\n"})
    rules = _rules(
        tmp_path,
        GOOD_RULE,
        "broken|missing regex field",
        "bad|uncompilable|abc(unclosed",
    )
    result = _run(repo, rules)
    assert "1 rules" in result.stdout, result.stdout
    assert "2 unusable of 3 rule lines" in result.stdout, result.stdout


def test_repository_with_no_tracked_files_cannot_decide(tmp_path: Path) -> None:
    """Reading nothing is not a clean result."""

    repo = _git_repo(tmp_path)
    rules = _rules(tmp_path, GOOD_RULE)
    result = _run(repo, rules)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No tracked files" in result.stderr


def test_outside_a_git_repository_cannot_decide(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    rules = _rules(tmp_path, GOOD_RULE)
    result = _run(outside, rules)
    assert result.returncode == 2, result.stdout + result.stderr


def test_uncovered_candidate_is_reported_with_exit_one(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "the widget-factory ships today\n"})
    rules = _rules(tmp_path, GOOD_RULE)
    result = _run(repo, rules)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "widget-factory" in result.stdout


def test_a_rule_that_covers_the_token_clears_it(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "the widget-factory ships today\n"})
    rules = _rules(tmp_path, "widget|internal product|widget-[a-z]+")
    result = _run(repo, rules)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 uncovered candidates" in result.stdout


def test_baseline_suppresses_a_reviewed_token(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "the widget-factory ships today\n"})
    (repo / "baseline.txt").write_text("widget-factory\n", encoding="utf-8")
    rules = _rules(tmp_path, GOOD_RULE)
    result = _run(repo, rules, "--baseline", "baseline.txt")
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_output_carries_the_scope_it_measured(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {"a.md": "the widget-factory ships today\n"})
    rules = _rules(tmp_path, GOOD_RULE, "broken|missing regex field")
    result = _run(repo, rules, "--json")
    payload = json.loads(result.stdout)
    assert payload["rules"] == 1
    assert payload["rules_unusable"] == 1
    assert payload["rules_considered"] == 2
    assert payload["tracked_files"] == 1
    assert payload["uncovered_total"] >= 1
