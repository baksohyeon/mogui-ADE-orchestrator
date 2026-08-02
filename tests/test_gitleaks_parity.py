"""Parity between the hand-written scanner and gitleaks with this repository's config.

The matching half of `scripts/redaction-scan.sh` is a reimplementation of what
gitleaks already does, and better: hundreds of maintained provider rules, entropy
checks, baselines, allowlists, and output redaction. The plan is to hand matching
to gitleaks and keep only what gitleaks does not do, which is commit-message
scanning and the inverse blind-spot inventory.

This test is the safety net for that swap. It runs both engines over the same
fixtures and requires them to agree, so the engine can be replaced without the
replacement quietly covering less. Two divergences were found and fixed while
writing it: synthetic home prefixes had been translated into gitleaks `paths`,
which skips files rather than content, and the placeholder list had been
translated into `stopwords`, which did not excuse anything here while `regexes`
does.

Zero findings on both sides proves nothing on its own, so every rule gets a
positive fixture that must be flagged and the excused classes get negatives.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "redaction-scan.sh"
CONFIG = REPO_ROOT / "config" / "gitleaks.toml"

# Every fixture is assembled at runtime. A whole literal here would be a finding in
# this file, and the honest fix is to leave the gate objecting to whole secrets
# everywhere rather than to add an exemption for the tests that check it.
AWS_KEY = "AKIA" + "2QJZ7NVXH4KDPLMB"

MUST_FLAG = {
    "private_key": "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
    "aws_access_key": f"aws {AWS_KEY} here",
    "github_token": "token " + "ghp_" + "A" * 24,
    "slack_token": "xoxb" + "-" + "1234567890abcdef",
    "openai_sk": "sk" + "-" + "B" * 24,
    "anthropic_key": "sk-ant" + "-" + "C" * 24,
    "bearer_token": "Authorization: " + "Bearer " + "D" * 30,
    "assignment_secret": 'api_key = "' + "s3cr3t" + 'v4lue"',
    "dotenv_export": "export " + "ANTHROPIC_API_KEY" + "=abc",
    "home_path": "/Users/" + "realperson/notes",
    "internal_ip": "host at " + "10." + "1.2.3 today",
    "jira_hf": "see " + "HF-" + "1234 for detail",
    "slack_url": "https://acme." + "slack.com" + "/archives/C1",
    "internal_host": "box." + "corp" + " is internal",
}

MUST_EXCUSE = {
    "placeholder_key": 'api_key = "' + "your_api" + '_key"',
    "synthetic_home": "/Users/" + "dev/workspace/thing",
    "canonical_aws": "AKIAIOSFODNN7" + "EXAMPLE",
}

requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks is not installed; the preflight requires it for real runs",
)


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "config").mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    shutil.copy(SCANNER, repo / "scripts" / "redaction-scan.sh")
    (repo / "scripts" / "redaction-allowlist.txt").write_text("", encoding="utf-8")
    shutil.copy(CONFIG, repo / "config" / "gitleaks.toml")
    for name, body in {**MUST_FLAG, **MUST_EXCUSE}.items():
        (repo / f"{name}.txt").write_text(body + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "fixtures"], cwd=repo, check=True, env=env)
    return repo


def _scanner_files(repo: Path) -> set[str]:
    env = {k: v for k, v in os.environ.items() if k != "REDACTION_EXTRA_PATTERNS"}
    result = subprocess.run(
        ["bash", "scripts/redaction-scan.sh", "-v"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    found = set()
    for line in (result.stdout + result.stderr).splitlines():
        line = line.strip()
        if "  [" in line and "]" in line:
            found.add(line.split(":")[0].removesuffix(".txt"))
    return found


def _gitleaks_files(repo: Path, tmp_path: Path) -> set[str]:
    report = tmp_path / "gitleaks.json"
    subprocess.run(
        [
            "gitleaks", "dir", ".",
            "--config", "config/gitleaks.toml",
            "--no-banner",
            "--report-format", "json",
            "--report-path", str(report),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if not report.exists():
        return set()
    return {
        Path(row["File"]).name.removesuffix(".txt")
        for row in json.loads(report.read_text(encoding="utf-8"))
    }


@requires_gitleaks
def test_both_engines_flag_every_positive_fixture(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    scanner = _scanner_files(repo)
    gitleaks = _gitleaks_files(repo, tmp_path)

    missed_by_scanner = sorted(set(MUST_FLAG) - scanner)
    missed_by_gitleaks = sorted(set(MUST_FLAG) - gitleaks)
    assert not missed_by_scanner, missed_by_scanner
    assert not missed_by_gitleaks, missed_by_gitleaks


@requires_gitleaks
def test_both_engines_excuse_placeholders_and_synthetic_paths(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    scanner = _scanner_files(repo)
    gitleaks = _gitleaks_files(repo, tmp_path)

    wrongly_flagged_by_scanner = sorted(set(MUST_EXCUSE) & scanner)
    wrongly_flagged_by_gitleaks = sorted(set(MUST_EXCUSE) & gitleaks)
    assert not wrongly_flagged_by_scanner, wrongly_flagged_by_scanner
    assert not wrongly_flagged_by_gitleaks, wrongly_flagged_by_gitleaks


@requires_gitleaks
def test_the_two_engines_do_not_diverge_on_any_fixture(tmp_path: Path) -> None:
    """The property the engine swap depends on."""

    repo = _fixture_repo(tmp_path)
    scanner = _scanner_files(repo)
    gitleaks = _gitleaks_files(repo, tmp_path)
    assert scanner == gitleaks, {
        "only_scanner": sorted(scanner - gitleaks),
        "only_gitleaks": sorted(gitleaks - scanner),
    }


@requires_gitleaks
def test_config_does_not_carry_organization_patterns(tmp_path: Path) -> None:
    """The committed config must stay publishable.

    Organization-specific patterns belong in a second config named by
    GITLEAKS_CONFIG and kept out of version control, because this repository is
    public and committing them would publish what they protect.
    """

    text = CONFIG.read_text(encoding="utf-8")
    assert "GITLEAKS_CONFIG" in text, "the config must say where org rules live"
    for marker in ("person_", "company_", "org_"):
        assert marker not in text, marker
