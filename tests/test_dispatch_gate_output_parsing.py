"""Regression coverage for dispatch's jqf() gate-output parser.

Measured 2026-08-13: a dispatch-gate invocation surfaced a human diagnostic
line ("dispatch-gate: REASON ...") on stdout ahead of the JSON verdict line.
The old jqf() ran `json.load(sys.stdin)` against the whole captured output and
died with `Expecting value: line 2 column 1 (char 1)`, which killed the
register step after the worker was already dispatched and running — the
ledger was never told the job existed
("register ... (worker IS running — resolve register manually)").

jqf() must tolerate an extra human line anywhere in the captured output and
still recover the JSON verdict, in both the success path (JSON only) and the
failure path (a prefix line ahead of the JSON).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from windows_exec_surface import skip_windows_exec_surface

pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "master-ops" / "scripts" / "dispatch"


def _jqf_source() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^jqf\(\) \{.*?^\}", source, flags=re.MULTILINE | re.DOTALL)
    assert match, "jqf() helper is missing from master-ops/scripts/dispatch"
    return match.group(0)


def run_jqf(stdin_text: str, expr: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise the dispatch jqf() helper")
    script = f'{_jqf_source()}\njqf "{expr}"\n'
    return subprocess.run(
        [bash, "-c", script],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_single_line_json_still_parses() -> None:
    result = run_jqf('{"allow": true, "reason": "ok"}\n', "d['allow']")
    assert result.returncode == 0
    assert result.stdout.strip() == "True"


def test_human_diagnostic_line_ahead_of_json_does_not_crash() -> None:
    """The exact measured shape: a prefixed reason line, then the JSON verdict."""

    mixed = 'dispatch-gate: MODEL_TIER_ESCALATION\n{"allow": false, "reason": "MODEL_TIER_ESCALATION"}\n'
    allow = run_jqf(mixed, "d['allow']")
    reason = run_jqf(mixed, "d['reason']")

    assert allow.returncode == 0
    assert allow.stdout.strip() == "False"
    assert "Traceback" not in allow.stderr
    assert "JSONDecodeError" not in allow.stderr

    assert reason.returncode == 0
    assert reason.stdout.strip() == "MODEL_TIER_ESCALATION"


def test_blank_lines_around_the_json_do_not_crash() -> None:
    result = run_jqf('\n\n{"allow": true, "reason": "ok"}\n\n', "d['allow']")
    assert result.returncode == 0
    assert result.stdout.strip() == "True"


def test_no_json_object_line_fails_loudly_instead_of_silently() -> None:
    result = run_jqf("dispatch-gate: something went wrong with no JSON at all\n", "d['allow']")
    assert result.returncode != 0
    assert "no JSON object line" in result.stderr
