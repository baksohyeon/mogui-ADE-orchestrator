"""Regression coverage for the dispatch pane delivery classifier."""

from __future__ import annotations

import re
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "master-ops" / "scripts" / "dispatch"


def _classifier() -> str:
    """Extract the side-effect-free classifier for focused shell tests."""

    source = SCRIPT.read_text(encoding="utf-8")
    assignments = "\n".join(
        line
        for line in source.splitlines()
        if re.match(
            r"^(HOOK_TRUST_MARKERS|LIMIT_MARKERS|PREPARED_PROMPT_MARKERS|"
            r"PREPARED_UNICODE_PROMPT_MARKERS)=",
            line,
        )
    )
    function = re.search(
        r"pane_classify_text\(\) \{.*?^\}", source, flags=re.MULTILINE | re.DOTALL
    )
    assert function, "dispatch classifier function is missing"
    delivery = re.search(
        r"delivery_result\(\) \{.*?^\}", source, flags=re.MULTILINE | re.DOTALL
    )
    assert delivery, "dispatch delivery transition function is missing"
    return (
        f"{assignments}\n{function.group(0)}\n{delivery.group(0)}\n"
        "if [ \"${CLASSIFY_ONLY:-1}\" = 1 ]; then pane_classify_text \"$1\"; "
        "else delivery_result \"$(pane_classify_text \"$1\")\" "
        "\"$(pane_classify_text \"$2\")\"; fi"
    )


def classify(pane: str) -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise the dispatch shell classifier")
    result = subprocess.run(
        [bash, "-c", _classifier(), "classifier", pane],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def transition(before: str, after: str) -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise the dispatch shell classifier")
    result = subprocess.run(
        [bash, "-c", _classifier(), "transition", before, after],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "CLASSIFY_ONLY": "0"},
    )
    return result.stdout.strip()


def test_hook_and_trust_markers_are_their_own_class() -> None:
    assert classify("Do you trust the files in this folder?") == "hook-trust"
    assert classify("I trust this folder") == "hook-trust"


def test_limit_markers_are_their_own_class() -> None:
    assert classify("You've hit your limit. Try again after 2 hours.") == "limit"
    assert classify("Rate limit reached") == "limit"


def test_prepared_agent_prompt_is_delivery_evidence() -> None:
    assert classify("codex> ") == "prepared-prompt"
    assert classify("❯ ") == "prepared-prompt"


def test_unclassified_pane_is_not_a_delivery_pass() -> None:
    assert classify("worker emitted 128 bytes") == "unknown"
    assert classify("ordinary output ➜") == "unknown"
    assert classify("spec mentions provider rate limit") == "unknown"
    assert classify("context window 40% used\ncodex> ") == "prepared-prompt"


def test_hook_class_wins_when_multiple_gate_markers_are_visible() -> None:
    assert classify("workspace trust\nrate limit") == "hook-trust"


def test_unchanged_prompt_is_unverified_and_prompt_consumption_is_started() -> None:
    assert transition("codex> ", "codex> ") == "unknown"
    assert transition("codex> ", "working") == "agent-started"


def test_post_injection_gate_transitions_are_confirmed_failures() -> None:
    assert transition("codex> ", "Do you trust the files in this folder?") == "hook-trust"
    assert transition("codex> ", "Rate limit reached") == "limit"


def test_delivery_no_longer_uses_output_clock() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "pane_advanced" not in source
    assert "pane_last_output" not in source
