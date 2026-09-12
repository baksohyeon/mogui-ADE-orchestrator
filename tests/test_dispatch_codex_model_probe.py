"""Pin the codex model-probe wiring in master-ops/scripts/dispatch.

Measured 2026-08-13: a codex worker's register step ran model-identity-probe
(built for claude-shaped transcripts) against a codex rollout and measured
model=<missing>, denying registration with MODEL_TIER_ESCALATION even though
the model id was in the file. A raw `grep -o '"model":"[^"]*"'` probe against
the rollout is not a fix either — it returns the JSON fragment, not the bare
id, so the gate's tier lookup still measures tier=unknown
(measured="model":"gpt-5.6-luna" tier=unknown, same date).

dispatch must route codex workers to scripts/model-probe-rollout instead, and
never route them to the claude-shaped model-identity-probe + grep combination.
"""

from __future__ import annotations

from pathlib import Path

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
    source = _source()
    assert 'if [ "$RUNTIME" = codex ]; then' in source
    assert (
        'MODEL_PROBE_ARGS=(--model-probe-cmd "$ROLLOUT_PROBE_BIN \\"\\$(ls -t $TGLOB 2>/dev/null | head -1)\\"")'
        in source
    )
    # The claude-shaped probe + grep combination stays for other runtimes, but
    # must not be the one selected for codex.
    codex_branch_start = source.index('if [ "$RUNTIME" = codex ]; then')
    codex_branch_end = source.index("else", codex_branch_start)
    codex_branch = source[codex_branch_start:codex_branch_end]
    assert "$PROBE_BIN --transcript" not in codex_branch


def test_codex_probe_state_is_labeled_honestly_as_unscoped() -> None:
    source = _source()
    assert 'codex) PROBE_STATE="codex-latest-rollout";;' in source
    assert "codex-latest-rollout)" in source
    assert "not worker-scoped" in source
