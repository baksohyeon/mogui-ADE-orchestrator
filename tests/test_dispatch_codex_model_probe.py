"""Pin the codex model-probe wiring in master-ops/scripts/dispatch.

Measured 2026-08-13: a codex worker's register step ran model-identity-probe
(built for claude-shaped transcripts) against a codex rollout and measured
model=<missing>, denying registration with MODEL_TIER_ESCALATION even though
the model id was in the file. A raw `grep -o '"model":"[^"]*"'` probe against
the rollout is not a fix either: it returns the JSON fragment instead of the
bare id, so the gate's tier lookup still measures tier=unknown
(measured="model":"gpt-5.6-luna" tier=unknown, same date).

dispatch must route codex workers to scripts/model-probe-rollout instead, and
never route them to the claude-shaped model-identity-probe + grep combination.

Measured 2026-08-31 (coderabbit Major, cubic P1): the codex rollout glob spans
every Orca-managed account and date, so "newest match" can measure a
concurrent worker's rollout instead of this dispatch's own. dispatch must
narrow the candidate to rollouts no older than this dispatch's own start
marker (select_scoped_codex_rollout), and leave the probe unavailable
instead of guessing when nothing matches that scope.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from windows_exec_surface import skip_windows_exec_surface

pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "master-ops" / "scripts" / "dispatch"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_rollout_probe_binary_is_declared() -> None:
    assert "ROLLOUT_PROBE_BIN={{RUNTIME_ROOT}}/scripts/model-probe-rollout" in _source()


def test_transcript_glob_for_resolves_a_codex_rollout_glob() -> None:
    source = _source()
    assert "    codex)" in source
    assert "rollout-*.jsonl" in source
    assert "codex-accounts" in source


def test_codex_runtime_is_routed_to_the_rollout_probe_not_the_claude_probe() -> None:
    """Structural check of the codex/non-codex branches, not their literal
    bytes (cubic P3, 2026-08-31): a cosmetic reflow of either branch must not
    break this test the way asserting exact source text would. The boundary
    between the two branches is found by the two-space indent of the outer
    if/else guard itself, not by the first "else" substring in the text,
    since a conditional nested inside either branch can contain its own,
    more deeply indented "else".
    """

    source = _source()
    assert 'if [ "$RUNTIME" = codex ]; then' in source

    codex_branch_start = source.index('if [ "$RUNTIME" = codex ]; then')
    outer_else = re.search(r"\n  else\n", source[codex_branch_start:])
    assert outer_else, "expected a two-space-indented else closing the codex/non-codex branch"
    codex_branch = source[codex_branch_start : codex_branch_start + outer_else.start()]

    non_codex_branch_start = codex_branch_start + outer_else.end()
    non_codex_branch_end = source.index("\n  fi\n", non_codex_branch_start)
    non_codex_branch = source[non_codex_branch_start:non_codex_branch_end]

    assert "$PROBE_BIN --transcript" not in codex_branch
    assert "$ROLLOUT_PROBE_BIN" in codex_branch
    assert "$PROBE_BIN --transcript" in non_codex_branch


def test_codex_probe_state_is_labeled_honestly_as_unscoped() -> None:
    source = _source()
    assert 'PROBE_STATE="codex-latest-rollout"' in source
    assert "codex-latest-rollout)" in source
    assert "not worker-scoped" in source


def test_unresolved_codex_rollout_falls_back_to_unavailable_probe_state() -> None:
    """No scoped rollout found must report unavailable, not guess by falling
    back to an unscoped glob."""

    source = _source()
    assert 'PROBE_STATE="unavailable"' in source
    fallback = re.search(
        r'if \[ -n "\$CODEX_ROLLOUT" \]; then\s*\n\s*PROBE_STATE="codex-latest-rollout"\s*\n\s*else\s*\n\s*PROBE_STATE="unavailable"',
        source,
    )
    assert fallback, "expected an empty $CODEX_ROLLOUT to set PROBE_STATE=unavailable"


def _select_scoped_codex_rollout_source() -> str:
    source = _source()
    match = re.search(
        r"^select_scoped_codex_rollout\(\) \{.*?^\}",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "select_scoped_codex_rollout() helper is missing from master-ops/scripts/dispatch"
    return match.group(0)


def run_select_scoped_codex_rollout(glob_expr: str, marker: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise select_scoped_codex_rollout()")
    script = (
        f"{_select_scoped_codex_rollout_source()}\n"
        f'select_scoped_codex_rollout "{glob_expr}" "{marker}"\n'
    )
    return subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _set_mtime(path: Path, epoch: float) -> None:
    os.utime(path, (epoch, epoch))


def test_scoped_rollout_selection_picks_a_rollout_created_after_the_marker(tmp_path: Path) -> None:
    now = time.time()
    marker = tmp_path / "marker"
    marker.write_text("", encoding="utf-8")
    _set_mtime(marker, now)

    fresh = tmp_path / "rollout-fresh.jsonl"
    fresh.write_text("{}", encoding="utf-8")
    _set_mtime(fresh, now + 60)

    result = run_select_scoped_codex_rollout(str(tmp_path / "rollout-*.jsonl"), str(marker))

    assert result.returncode == 0
    assert result.stdout.strip() == str(fresh)


def test_scoped_rollout_selection_excludes_a_rollout_from_before_the_marker(tmp_path: Path) -> None:
    """The measured vulnerability: a worker already running before this
    dispatch started must never win the "newest rollout" race (coderabbit
    Major, cubic P1, 2026-08-31)."""

    now = time.time()
    stale = tmp_path / "rollout-concurrent-worker.jsonl"
    stale.write_text("{}", encoding="utf-8")
    _set_mtime(stale, now - 60)

    marker = tmp_path / "marker"
    marker.write_text("", encoding="utf-8")
    _set_mtime(marker, now)

    result = run_select_scoped_codex_rollout(str(tmp_path / "rollout-*.jsonl"), str(marker))

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_scoped_rollout_selection_picks_the_newest_among_several_scoped_candidates(
    tmp_path: Path,
) -> None:
    now = time.time()
    marker = tmp_path / "marker"
    marker.write_text("", encoding="utf-8")
    _set_mtime(marker, now)

    older = tmp_path / "rollout-a.jsonl"
    older.write_text("{}", encoding="utf-8")
    _set_mtime(older, now + 30)

    newest = tmp_path / "rollout-b.jsonl"
    newest.write_text("{}", encoding="utf-8")
    _set_mtime(newest, now + 60)

    result = run_select_scoped_codex_rollout(str(tmp_path / "rollout-*.jsonl"), str(marker))

    assert result.returncode == 0
    assert result.stdout.strip() == str(newest)


def test_scoped_rollout_selection_reports_nothing_without_a_marker() -> None:
    result = run_select_scoped_codex_rollout("/tmp/does-not-matter/rollout-*.jsonl", "")

    assert result.returncode == 0
    assert result.stdout.strip() == ""
