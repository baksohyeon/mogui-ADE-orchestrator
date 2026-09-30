"""Coverage for scripts/model-probe-rollout.

Measured 2026-08-13: probing a codex rollout jsonl with
`grep -o '"model":"[^"]*"'` returns the whole JSON fragment
(`"model":"gpt-5.6-luna"`), not the bare model id, so dispatch-gate register's
tier lookup measures tier=unknown even when the declared model and the
rollout's model agree. dispatch-gate register's --model-probe-cmd contract
needs bare-id stdout for the tier policy match to succeed.
"""

from __future__ import annotations

import subprocess
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

    assert result.returncode != 0
    assert "no rollout file" in result.stderr


def test_missing_argument_fails_loudly() -> None:
    result = run_probe()

    assert result.returncode != 0
    assert "no rollout file" in result.stderr


def test_file_with_no_model_field_prints_nothing_and_still_succeeds(tmp_path: Path) -> None:
    """head -1 of an empty sed match is empty stdout, not a crash.

    dispatch-gate register treats empty probe stdout as model_probe_failed
    rather than a parse error, so this must exit 0 with nothing on stdout.
    """

    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text('{"type":"other_event"}\n', encoding="utf-8")

    result = run_probe(str(rollout))

    assert result.returncode == 0
    assert result.stdout.strip() == ""
