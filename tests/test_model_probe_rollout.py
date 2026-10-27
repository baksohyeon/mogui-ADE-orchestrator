"""Coverage for scripts/model-probe-rollout.

Measured 2026-08-13: probing a codex rollout jsonl with
`grep -o '"model":"[^"]*"'` returns the whole JSON fragment
(`"model":"gpt-5.6-luna"`) instead of the bare model id, so dispatch-gate
register's tier lookup measures tier=unknown even when the declared model
and the rollout's model agree. dispatch-gate register's --model-probe-cmd
contract needs bare-id stdout for the tier policy match to succeed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from windows_exec_surface import skip_windows_exec_surface

pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "scripts" / "model-probe-rollout"


def run_probe(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_extracts_bare_model_id_not_the_json_fragment(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout-2026-08-13.jsonl"
    rollout.write_text(
        '{"type":"response_item","payload":{"model":"gpt-5.6-luna","other":1}}\n',
        encoding="utf-8",
    )

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == "gpt-5.6-luna"
    # The measured regression: raw grep would have produced this instead.
    assert result.stdout.strip() != '"model":"gpt-5.6-luna"'


def test_returns_the_first_model_field_in_the_file(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(
        '{"model":"gpt-5.6-luna"}\n{"model":"gpt-5.5"}\n',
        encoding="utf-8",
    )

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == "gpt-5.6-luna"


def test_missing_file_fails_loudly() -> None:
    result = run_probe("/nonexistent/rollout.jsonl")

    assert result.returncode == 1
    assert "no rollout file" in result.stderr


def test_missing_argument_fails_loudly() -> None:
    result = run_probe()

    assert result.returncode == 1
    assert "no rollout file" in result.stderr


def test_file_with_no_model_field_prints_nothing_and_still_succeeds(tmp_path: Path) -> None:
    """head -1 of an empty sed match is empty stdout. dispatch-gate
    register treats empty probe stdout as model_probe_failed, never a
    parse error, so this must exit 0 with nothing on stdout.
    """

    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text('{"type":"other_event"}\n', encoding="utf-8")

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_whitespace_around_the_colon_still_matches(tmp_path: Path) -> None:
    """Measured 2026-08-31 (coderabbit Minor): a greedy `.*`-based sed pattern
    with no whitespace tolerance produced no match against `"model": "x"`
    (a space after the colon), even though the field is present."""

    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text('{"model": "gpt-5.6-luna"}\n', encoding="utf-8")

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == "gpt-5.6-luna"


def test_returns_the_first_model_field_when_two_share_one_line(tmp_path: Path) -> None:
    """Measured 2026-08-31 (cubic P2): a greedy leading `.*` captures the
    LAST "model" field on a line instead of the first, so a codex rollout
    line carrying both a request and a response model id must still pin
    the first one."""

    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(
        '{"request":{"model":"gpt-5.6-luna"},"response":{"model":"gpt-5.5"}}\n',
        encoding="utf-8",
    )

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == "gpt-5.6-luna"


def test_unreadable_file_fails_loudly_matching_the_documented_exit_code(tmp_path: Path) -> None:
    """docs/public/reference.md documents exit 1 for a missing OR unreadable
    path; an existing-but-unreadable file must take the same exit-1 path as
    a missing one instead of silently succeeding (coderabbit Minor,
    2026-08-31: the prior pipeline's `head -1` masked a sed read failure).

    Skipped for root and on Windows (coderabbit Major / cubic P2,
    2026-10-26): chmod(0o000) denies nothing to root, which reads past file
    mode bits regardless, and win32 mode bits don't gate reads either, so
    this case measures nothing in either environment.
    """

    if sys.platform == "win32" or os.geteuid() == 0:
        pytest.skip(
            "chmod(0o000) does not deny reads for root or on Windows, "
            "so this case cannot measure anything there"
        )

    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text('{"model":"gpt-5.6-luna"}\n', encoding="utf-8")
    rollout.chmod(0o000)
    try:
        result = run_probe(str(rollout))
    finally:
        rollout.chmod(0o644)

    assert result.returncode == 1
    assert "no rollout file" in result.stderr
