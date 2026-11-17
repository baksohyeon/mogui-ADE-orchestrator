"""Fingerprint drift and a stale-fingerprint check (issue #331, item 2).

A `.gitleaksignore` fingerprint is `path:rule:line`: gitleaks has no
content-based form as of 8.30.1. Confirmed directly against its source
(`detect/detect.go`, tag v8.30.1): the fingerprint is built as
`fmt.Sprintf("%s:%s:%d", finding.File, finding.RuleID, finding.StartLine)`,
nothing else. So one line added above an exempted finding moves it to a new fingerprint and
the old exemption matches nothing, live again. The finding this exposes
already fails the scan on its own merits; the check here only reports which
`.gitleaksignore` lines are now dead weight, in tracked mode, without
reimplementing gitleaks' own ignore matching.

The check also covers commit-message exemptions (their fingerprints have no
file, just an empty leading field) and fails closed, not just non-blocking,
on a `.gitleaksignore` it cannot read at all.
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

# This fixture's AWS-shaped key matches both the default ruleset's own
# aws-access-token rule and this repo's aws_access_key rule, so exempting it
# fully at a given line takes both fingerprints.
FINGERPRINTS_AT_LINE_1 = (
    "secret.txt:aws_access_key:1\n" "secret.txt:aws-access-token:1\n"
)


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


@requires_gitleaks
def test_a_line_shift_breaks_the_fingerprint_and_the_scan_reports_it_stale(
    tmp_path: Path,
) -> None:
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "secret.txt").write_text(f"{LEAK}\n", encoding="utf-8")
    (repo / ".gitleaksignore").write_text(FINGERPRINTS_AT_LINE_1, encoding="utf-8")
    _git(repo, "add", "secret.txt", ".gitleaksignore")
    _git(repo, "commit", "-q", "-m", "add the secret, exempted at line 1")

    before = _scan(repo)
    before_output = before.stdout + before.stderr
    # Before: the fingerprint sits where the secret actually is, so the
    # exemption holds and nothing is stale.
    assert before.returncode == 0, before_output
    assert "stale-fingerprints=0" in before.stdout, before_output

    with open(repo / "secret.txt", "r+", encoding="utf-8") as handle:
        body = handle.read()
        handle.seek(0)
        handle.write("a new header line\n" + body)
    _git(repo, "add", "secret.txt")
    _git(repo, "commit", "-q", "-m", "shift the secret down one line")

    after = _scan(repo)
    after_output = after.stdout + after.stderr
    # After: the same two fingerprints now name line 1, which is the new
    # header, not the secret (now on line 2). The exemption stops applying:
    # the secret is live again and the scan fails on it, and separately
    # reports both listed fingerprints as stale (matching nothing live).
    assert after.returncode == 1, after_output
    assert "aws_access_key" in after_output, after_output
    assert "secret.txt:2" in after_output, after_output
    assert "stale-fingerprints=2" in after_output, after_output
    assert "secret.txt:aws_access_key:1" in after_output, after_output
    assert "secret.txt:aws-access-token:1" in after_output, after_output


@requires_gitleaks
def test_a_commit_message_exemption_is_not_wrongly_reported_stale(
    tmp_path: Path,
) -> None:
    """Commit-message findings use gitleaks' stdin fingerprint shape (no
    file, so the leading field is empty) and never show up in the tracked
    file rescan the stale check reruns. Without also rerunning the scanned
    commits' messages, a still-live exemption for one of them always read
    as stale (caught in review, reproduced with `--commit-messages` on a
    tracked-mode run whose exemption was actively suppressing the secret).
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / ".gitleaksignore").write_text(
        ":aws_access_key:1\n:aws-access-token:1\n", encoding="utf-8"
    )
    _git(repo, "add", ".gitleaksignore")
    _git(repo, "commit", "-q", "-m", "add the gitleaksignore")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "f1.md").write_text("file 1\n", encoding="utf-8")
    _git(repo, "add", "f1.md")
    _git(repo, "commit", "-q", "-m", LEAK)

    result = _scan(repo, "--commit-messages", f"{base}..HEAD")
    output = result.stdout + result.stderr

    # The exemption is doing its job: the commit-message secret is
    # suppressed, not just coincidentally absent.
    assert result.returncode == 0, output
    assert "stale-fingerprints=0" in result.stdout, output


@requires_gitleaks
def test_a_malformed_gitleaksignore_fails_closed_with_a_named_reason(
    tmp_path: Path,
) -> None:
    """A stray non-UTF-8 byte anywhere in `.gitleaksignore` — even inside a
    comment that never reaches matching — must not crash the stale check
    with an uncaught exception: under `set -e` that previously aborted with
    exit 1, the same code used for blocking findings, instead of the exit 2
    "cannot decide" this script uses everywhere else for an unreadable
    input (caught in review, reproduced with a `\\xff` byte in a comment).
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "secret.txt").write_text(f"{LEAK}\n", encoding="utf-8")
    (repo / ".gitleaksignore").write_bytes(
        b"# note \xff bad byte\nsecret.txt:aws_access_key:1\n"
    )
    _git(repo, "add", "secret.txt")
    _git(repo, "add", "-f", ".gitleaksignore")
    _git(repo, "commit", "-q", "-m", "add a malformed gitleaksignore")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 2, output
    assert "gitleaksignore" in output, output
