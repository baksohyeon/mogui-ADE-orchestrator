from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "model-drift-audit"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_single_model_session_reports_no_transition() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_single.jsonl"))

    assert result.returncode == 0
    assert "no transition" in result.stdout
    assert "claude-fable-5=3" in result.stdout


def test_midsession_switch_is_found_even_when_the_tail_is_homogeneous() -> None:
    """The failure this script exists for.

    The last ten turns are all one model, so a tail sample reports a clean
    session. The switch happened before that window.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_midsession.jsonl"))

    assert result.returncode == 1
    assert "transitions: 1" in result.stdout
    assert "claude-fable-5 -> claude-opus-5" in result.stdout


def test_expected_model_mismatch_fails_even_without_a_transition() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_single.jsonl"),
        "--expect",
        "claude-opus-5",
    )

    assert result.returncode == 1
    assert "MISMATCH" in result.stdout


def test_expected_model_match_passes() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_single.jsonl"),
        "--expect",
        "claude-fable-5",
    )

    assert result.returncode == 0
    assert "match" in result.stdout


def test_ignore_synthetic_keeps_the_transition_it_bridges() -> None:
    """Dropping synthetic turns must not drop the change across them.

    A -> synthetic -> B is an A -> B change once the synthetic turns are
    removed. Erasing the transition along with the turns is how the original
    drift went unnoticed.
    """
    fixture = str(FIXTURES / "model_drift_audit_synthetic_bridge.jsonl")

    with_synthetic = run("--transcript", fixture)
    without_synthetic = run("--transcript", fixture, "--ignore-synthetic")

    assert with_synthetic.returncode == 1
    assert without_synthetic.returncode == 1
    assert "claude-fable-5 -> claude-opus-5" in without_synthetic.stdout


def test_zero_assistant_turns_is_undecidable_not_clean() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_no_assistant.jsonl"))

    assert result.returncode == 2
    assert "undecidable" in result.stderr


def test_missing_transcript_is_undecidable_not_clean() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_does_not_exist.jsonl"))

    assert result.returncode == 2
    assert "no transcript found" in result.stderr


def test_json_output_carries_transitions_and_counts() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_midsession.jsonl"),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["drift"] is True
    assert payload["counts"]["claude-fable-5"] == 2
    assert payload["counts"]["claude-opus-5"] == 10
    assert payload["transitions"][0]["from"] == "claude-fable-5"
    assert payload["transitions"][0]["to"] == "claude-opus-5"


def test_no_expected_model_is_baked_in() -> None:
    """A default expectation would assert one installation's policy as everyone's."""
    result = run("--transcript", str(FIXTURES / "model_drift_audit_single.jsonl"))

    assert result.returncode == 0
    assert "expected" not in result.stdout
