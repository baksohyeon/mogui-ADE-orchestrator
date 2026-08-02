"""Rule coverage for the redaction gate, now that gitleaks is the matching engine.

This began as a parity test between the hand-written scanner and gitleaks, and it
did its job: three translation errors surfaced before the engine was swapped.
Synthetic home prefixes had become gitleaks `paths`, which skips files rather than
content, so 18 fixtures turned into findings. The placeholder list had become
`stopwords`, which excused nothing here while `regexes` does. And the home-path
rule had been widened from /Users to /home, which added a false positive.

With the swap done, comparing the wrapper against gitleaks would compare gitleaks
with itself. What remains worth pinning is coverage: every rule keeps a positive
fixture that must be flagged, and the excused classes keep negatives that must
not. Zero findings proves nothing on its own, which is why the positives exist.
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
    # The gate reads config from the repository it lives in, so the fixture repo
    # carries both, which is the shape an installation has.
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
def test_the_gate_flags_every_positive_fixture(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    missed = sorted(set(MUST_FLAG) - _scanner_files(repo))
    assert not missed, missed


@requires_gitleaks
def test_the_gate_excuses_placeholders_and_synthetic_paths(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    wrongly_flagged = sorted(set(MUST_EXCUSE) & _scanner_files(repo))
    assert not wrongly_flagged, wrongly_flagged


@requires_gitleaks
def test_the_wrapper_and_a_direct_gitleaks_run_agree(tmp_path: Path) -> None:
    """The wrapper must not narrow what the engine finds, only scope it."""

    repo = _fixture_repo(tmp_path)
    through_wrapper = _scanner_files(repo)
    direct = _gitleaks_files(repo, tmp_path)
    assert through_wrapper == direct, {
        "only_wrapper": sorted(through_wrapper - direct),
        "only_direct": sorted(direct - through_wrapper),
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
