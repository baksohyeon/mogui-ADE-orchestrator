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
concurrent worker's rollout instead of this dispatch's own.

Measured 2026-10-26 (coderabbit Major): the fix above scoped selection to
"newer than a marker file timestamping this dispatch's start" via `-nt`, but
codex appends to the same rollout file for a pane's whole session, and every
append moves that file's mtime forward. A worker that was already running
before this dispatch started still reads as "newer than the marker" once it
writes anything after the marker is created, so that worker's rollout keeps
winning the mtime race it was supposed to lose. dispatch now selects by
existence instead: snapshot_codex_rollouts lists the glob's candidates right
before this worker's pane exists, and new_rollout_since diffs that snapshot
against the glob afterward, taking the one file that is new. Existence is
stable under appends, mtime is not.
"""

from __future__ import annotations

import glob as globmod
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from windows_exec_surface import skip_windows_exec_surface

pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "master-ops" / "scripts" / "dispatch"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{.*?^\}}",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"{name}() helper is missing from master-ops/scripts/dispatch"
    return match.group(0)


def test_rollout_probe_binary_is_declared() -> None:
    assert "ROLLOUT_PROBE_BIN={{RUNTIME_ROOT}}/scripts/model-probe-rollout" in _source()


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise this dispatch helper")
    return subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_transcript_glob_for_resolves_a_codex_rollout_glob_from_the_live_accounts_dir(
    tmp_path: Path,
) -> None:
    """Executes transcript_glob_for against a temporary CODEX_ACCOUNTS_DIR
    instead of asserting on source text (cubic P2, 2026-10-26): a cosmetic
    reflow of the function must not break this test the way asserting
    literal source bytes would, and only running it proves the glob it
    emits actually matches a real rollout path shape."""

    accounts_dir = tmp_path / "codex accounts"
    accounts_dir.mkdir()
    script = (
        f"export CODEX_ACCOUNTS_DIR={shlex.quote(str(accounts_dir))}\n"
        f"{_function_source('codex_accounts_dir')}\n"
        f"{_function_source('transcript_glob_for')}\n"
        'transcript_glob_for codex ""\n'
    )
    result = _run_bash(script)

    assert result.returncode == 0, result.stderr
    glob = result.stdout.strip()
    assert glob, "transcript_glob_for codex produced no glob"

    mangled_accounts_dir = str(accounts_dir).replace(" ", "?")
    expected = f"{mangled_accounts_dir}/*/home/sessions/*/*/*/rollout-*.jsonl"
    assert glob == expected

    # The glob this test asserts on must actually match a real rollout path
    # shape, not just echo back whatever codex_accounts_dir printed.
    candidate = (
        accounts_dir
        / "acct-1"
        / "home"
        / "sessions"
        / "2026"
        / "10"
        / "26"
        / "rollout-2026-10-26T00-00-00.jsonl"
    )
    candidate.parent.mkdir(parents=True)
    candidate.write_text("{}", encoding="utf-8")

    assert globmod.glob(glob) == [str(candidate)]


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


def test_codex_probe_state_is_labeled_honestly_as_worker_scoped() -> None:
    """The probe state name and its label must say "worker-scoped" now that
    new_rollout_since actually scopes the rollout to this worker by
    existence, not "not worker-scoped" the way the old, unscoped
    machine-wide-newest selection honestly had to (2026-10-26)."""

    source = _source()
    assert 'PROBE_STATE="codex-new-rollout"' in source
    assert "codex-new-rollout)" in source
    assert "worker-scoped" in source
    assert "not worker-scoped" not in source


def test_unresolved_codex_rollout_falls_back_to_unavailable_probe_state() -> None:
    """No new rollout found must report unavailable, not guess by falling
    back to an unscoped glob."""

    source = _source()
    assert 'PROBE_STATE="unavailable"' in source
    fallback = re.search(
        r'if new_rollout_since "\$CODEX_ROLLOUT_BEFORE" "\$TGLOB"; then\s*\n'
        r'\s*PROBE_STATE="codex-new-rollout"\s*\n'
        r"\s*else\s*\n"
        r'\s*PROBE_STATE="unavailable"',
        source,
    )
    assert fallback, "expected a failed new_rollout_since call to set PROBE_STATE=unavailable"


def test_codex_rollout_before_snapshot_is_taken_ahead_of_task_create() -> None:
    """The before-snapshot has to be taken before this worker's pane can
    exist (task-create precedes terminal create/reuse, so it is the
    earliest safe point); taking it any later could snapshot a rollout
    this worker itself already started, and then never see it as "new"."""

    source = _source()
    snapshot_call = source.index("CODEX_ROLLOUT_BEFORE=$(snapshot_codex_rollouts")
    task_create = source.index("# 2. task-create")
    assert snapshot_call < task_create


def run_rollout_scenario(tmp_path: Path, between: str) -> subprocess.CompletedProcess[str]:
    """Runs snapshot_codex_rollouts against tmp_path's rollout-*.jsonl glob,
    then the free-form bash in `between` (which may add, grow, or leave
    alone candidate files), then new_rollout_since against the same glob.
    Reports the outcome as RC=0 plus ROLLOUT=<path>, or RC=1 plus
    REASON=<text>."""

    glob_expr = str(tmp_path / "rollout-*.jsonl")
    script = (
        f"{_function_source('snapshot_codex_rollouts')}\n"
        f'before=$(snapshot_codex_rollouts "{glob_expr}")\n'
        f"{between}\n"
        f"{_function_source('new_rollout_since')}\n"
        f'if new_rollout_since "$before" "{glob_expr}"; then\n'
        '  printf "RC=0\\nROLLOUT=%s\\n" "$CODEX_ROLLOUT"\n'
        "else\n"
        '  printf "RC=1\\nREASON=%s\\n" "$CODEX_ROLLOUT_REASON"\n'
        "fi\n"
    )
    return _run_bash(script)


def test_new_rollout_since_excludes_a_pre_existing_rollout_even_after_it_grows(
    tmp_path: Path,
) -> None:
    """The measured vulnerability (coderabbit Major, 2026-10-26): a worker
    that was already running before this dispatch started must never be
    selected, even once codex appends to its rollout and moves the file's
    mtime past every timestamp this dispatch could have snapshotted."""

    stale = tmp_path / "rollout-concurrent-worker.jsonl"
    stale.write_text("{}", encoding="utf-8")

    # Simulate codex appending to the pre-existing worker's rollout after
    # the snapshot was taken: this moves its mtime forward, the thing the
    # old "-nt marker" filter mistook for freshness.
    result = run_rollout_scenario(tmp_path, between=f'sleep 1; printf "{{}}\\n" >> "{stale}"')

    assert result.returncode == 0, result.stderr
    assert "RC=1" in result.stdout
    assert "no new rollout file appeared" in result.stdout
    assert str(stale) not in result.stdout


def test_new_rollout_since_selects_the_one_file_that_appeared_after_the_snapshot(
    tmp_path: Path,
) -> None:
    stale = tmp_path / "rollout-concurrent-worker.jsonl"
    stale.write_text("{}", encoding="utf-8")
    fresh = tmp_path / "rollout-this-worker.jsonl"

    result = run_rollout_scenario(tmp_path, between=f'printf "{{}}" > "{fresh}"')

    assert result.returncode == 0, result.stderr
    assert "RC=0" in result.stdout
    assert f"ROLLOUT={fresh}" in result.stdout


def test_new_rollout_since_reports_unavailable_with_a_reason_when_nothing_new_appeared(
    tmp_path: Path,
) -> None:
    result = run_rollout_scenario(tmp_path, between="")

    assert result.returncode == 0, result.stderr
    assert "RC=1" in result.stdout
    assert "no new rollout file appeared for this worker" in result.stdout


def test_new_rollout_since_reports_unavailable_with_a_reason_when_more_than_one_appeared(
    tmp_path: Path,
) -> None:
    rollout_a = tmp_path / "rollout-a.jsonl"
    rollout_b = tmp_path / "rollout-b.jsonl"
    between = f'printf "{{}}" > "{rollout_a}"; printf "{{}}" > "{rollout_b}"'

    result = run_rollout_scenario(tmp_path, between=between)

    assert result.returncode == 0, result.stderr
    assert "RC=1" in result.stdout
    assert "more than one new rollout file appeared" in result.stdout
