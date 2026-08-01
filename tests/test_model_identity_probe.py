from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "model-identity-probe"
FIXTURES = ROOT / "tests" / "fixtures"


def test_model_identity_probe_ok_for_recent_default_limit() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(FIXTURES / "model_identity_probe_ok.jsonl"),
            "--expect",
            "claude-fable-5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "MODEL-PROBE OK claude-fable-5 10/10"


def test_model_identity_probe_drift_reports_distribution() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(FIXTURES / "model_identity_probe_drift.jsonl"),
            "--expect",
            "claude-fable-5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout.startswith("MODEL-PROBE DRIFT: ")
    assert "claude-fable-5=2" in result.stdout
    assert "gpt-5=1" in result.stdout
    assert "cursor-agent-model=1" in result.stdout
    assert "<missing>=1" in result.stdout
    assert "propose a clean-spawn succession" in result.stdout


def test_model_identity_probe_limit_can_narrow_recent_turns() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(FIXTURES / "model_identity_probe_drift.jsonl"),
            "--expect",
            "cursor-agent-model",
            "--limit",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "cursor-agent-model=1" in result.stdout
    assert "<missing>=1" in result.stdout
    assert "gpt-5" not in result.stdout


def test_model_identity_probe_ok_for_nested_real_shape() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(FIXTURES / "model_identity_probe_nested_real_shape.jsonl"),
            "--expect",
            "claude-fable-5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODEL-PROBE OK claude-fable-5 2/2" in result.stdout


def test_model_identity_probe_asserts_nothing_without_expected_model() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transcript",
            str(FIXTURES / "model_identity_probe_ok.jsonl"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODEL-PROBE INFO" in result.stdout
    assert "nothing asserted" in result.stdout
