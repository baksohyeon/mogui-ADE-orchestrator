"""`*.local.env` false positive (issue #331, item 4).

The `internal_host` rule's allowlist covered only the literal `settings.local`
(#168), so a file name or comment naming `instance.local.env` still flagged.

Fixed entirely in `config/gitleaks.toml`, with gitleaks' own matching and
allowlist, same as #168: the rule's regex now swallows every further dotted
label after the keyword instead of stopping at the first one, so the match
is always the whole token, truncating nothing away; the allowlist then
requires that whole token to end exactly at `.local.env` with a single plain
label before it. A real host wearing a `.local.env`-shaped suffix, a real
corp/internal label folded into the same token, or more host-like text after
`.env`, all keep the match longer than the anchored allowlist entry allows,
so they still flag (each a real bug caught in review on an earlier version
that put the exemption in a second, Python-side check outside gitleaks'
own matching instead).
"""

from __future__ import annotations

import base64
import os
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
def test_local_env_file_name_is_excused_but_bare_local_host_still_flags(
    tmp_path: Path,
) -> None:
    # Whole literals here would be findings in this file: the bare host is
    # joined at runtime the same way other fixtures in this suite are.
    bare_local_host = "db" + "." + "local"
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        "see instance.local.env for local overrides\n"
        f"{bare_local_host} is a bare host, still real\n",
        encoding="utf-8",
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "instance.local.env" not in output, output
    assert "notes.md" in output, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_name_on_a_line_with_a_real_host_still_flags_the_host(
    tmp_path: Path,
) -> None:
    bare_corp_host = "db" + "." + "corp"
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        f"instance.local.env and {bare_corp_host} are mentioned on one line\n",
        encoding="utf-8",
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert bare_corp_host in output, output
    assert "instance.local.env" not in output, output


@requires_gitleaks
def test_local_env_embedded_in_a_longer_real_host_still_flags(
    tmp_path: Path,
) -> None:
    """A `*.local.env` shape sitting mid-hostname is not a bare filename
    mention. A whole literal here would be a finding in this file, so it is
    joined at runtime the same way other fixtures in this suite are.
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        "cache" + ".local" + ".env.acme.net serves traffic\n",
        encoding="utf-8",
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_embedded_in_a_unicode_continued_host_still_flags(
    tmp_path: Path,
) -> None:
    """An ASCII-only continuation class truncated the match one label
    early at a non-ASCII dotted label, which the allowlist then exempted
    as if that truncated prefix were the whole token (caught in review,
    confirmed directly against gitleaks with ignore-matching disabled: the
    match came back as exactly the truncated ASCII prefix, excused).
    """
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        "cache" + ".local" + ".env." + "équipe.net serves traffic\n",
        encoding="utf-8",
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_embedded_in_a_korean_unicode_host_still_flags(
    tmp_path: Path,
) -> None:
    """A hostname ending in a non-ASCII character must stay a finding."""
    repo = _repo_with_commits(tmp_path, ["base"])
    host = "cache" + ".local" + ".env." + "한국"
    (repo / "notes.md").write_text(f"{host}\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert host in output, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_embedded_in_a_decomposed_unicode_host_still_flags(
    tmp_path: Path,
) -> None:
    """The same `.local.env.équipe.net` host written in Unicode's NFD
    (decomposed) form — "e" plus its own combining accent, rather than the
    single precomposed "é" codepoint — is letters and digits plus a
    combining mark, not a letter followed by a boundary. Without \\p{M} in
    the continuation class this still failed closed rather than hiding the
    finding (truncated one character short of the combining mark, which
    the allowlist's end anchor then rejected), but the match text was an
    oddly truncated "...env.e"; confirmed directly against gitleaks that
    \\p{M} fixes the truncation and the match now reads the full host.
    """
    import unicodedata

    repo = _repo_with_commits(tmp_path, ["base"])
    host_nfd = unicodedata.normalize(
        "NFD", "cache" + ".local" + ".env." + "équipe.net"
    )
    (repo / "notes.md").write_text(
        f"{host_nfd} serves traffic\n", encoding="utf-8"
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_exemption_holds_across_a_lone_cr_line(
    tmp_path: Path,
) -> None:
    """gitleaks counts lines by "\\n" only; a lone "\\r" is just a character
    to it, not a line break. An earlier version of this fix re-read the
    source line itself in Python, whose default newline handling splits on
    a lone "\\r" too and desynced from gitleaks' own line count, excusing a
    real host that landed on the wrong line by that reading (caught in
    review). The gitleaks-native fix has no separate line read to desync;
    this fixture is kept as a regression pin. Whole literals split at
    runtime, same convention as the rest of this suite.
    """
    bare_local_env = "a" + "." + "local" + ".env is fine\r"
    bare_local_host = "via " + "b" + "." + "local" + " is not\n"
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_bytes(
        (bare_local_env + bare_local_host).encode("utf-8")
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_exemption_does_not_widen_to_corp_or_internal(
    tmp_path: Path,
) -> None:
    """The exemption is `*.local.env` only, per the issue; a `*.corp.env` or
    `*.internal.env` shape is not a Claude-settings-style file name and must
    still flag. Whole literal split at runtime, same convention as above.
    """
    corp_env_host = "vault" + "." + "corp" + ".env for overrides\n"
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text("see " + corp_env_host, encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_decoded_finding_is_never_excused_by_a_same_line_decoy(
    tmp_path: Path,
) -> None:
    """gitleaks decodes base64/hex/percent-encoded substrings by default and
    reports a finding there with its own decoded `Match` text, keeping the
    encoded line's `StartLine`. An earlier version of this fix answered "is
    this excused" by re-reading that `StartLine`'s raw source text in
    Python, which is the *encoded* line, not the decoded content gitleaks
    actually matched: a plain, genuinely bare `*.local.env` mention earlier
    on that same encoded line let a decoded, unrelated host ride along
    excused (caught in review). The gitleaks-native fix judges each
    finding's own `Match` text directly, so a decoded host's full text has
    to satisfy the allowlist on its own merits; this fixture is kept as a
    regression pin. Whole literals split or built at runtime, same
    convention as the rest of this suite.
    """
    safe_name = "instance" + "." + "local" + ".env"
    hidden_host = "evil" + "." + "local" + "." + "realcorp" + ".net"
    encoded = base64.b64encode(hidden_host.encode("utf-8")).decode("ascii")
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text(
        f"see {safe_name} and also {encoded}\n", encoding="utf-8"
    )
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output


@requires_gitleaks
def test_local_env_exemption_requires_a_single_label_before_local(
    tmp_path: Path,
) -> None:
    """The regex's own greedy character class can absorb an earlier "corp"
    or "internal" label into one match ending in ".local", so the text
    before ".local" must itself be a single label, not a real corp/internal
    host wearing a `.local.env` suffix (caught in review). Whole literal
    built at runtime, same convention as the rest of this suite.
    """
    host_label = "vault"
    corp_label = "corp"
    local_label = "local"
    corp_local_env_host = (
        host_label + "." + corp_label + "." + local_label + ".env here\n"
    )
    repo = _repo_with_commits(tmp_path, ["base"])
    (repo / "notes.md").write_text("see " + corp_local_env_host, encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "notes")

    result = _scan(repo)
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "internal_host" in output, output
