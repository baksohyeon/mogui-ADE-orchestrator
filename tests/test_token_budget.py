"""Provider usage readers and the quota guard's measured states."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from master_runtime.core.dispatch_gate import (
    DispatchGate,
    DispatchGateConfig,
    DispatchRequest,
)
from master_runtime.core.token_budget import (
    cap_total,
    latest_codex_quota,
    p90,
    read_agy_transcript,
    read_claude_transcript,
    read_codex_rollout,
    read_runtime,
    tier_defaults,
)


FIXTURES = Path(__file__).parent / "fixtures" / "token_usage"


def test_codex_reader_uses_latest_cumulative_token_count() -> None:
    usage = read_codex_rollout(FIXTURES / "codex-real-sample.jsonl")

    assert usage == {
        "input": 107091,
        "cached_input": 88704,
        "output": 4966,
        "total": 112057,
        "source": "codex:token_count",
    }


def test_claude_reader_sums_message_usage_and_preserves_cache_reads() -> None:
    usage = read_claude_transcript(FIXTURES / "claude-real-sample.jsonl")

    assert usage == {
        "input": 102,
        "cached_input": 300,
        "output": 20,
        "total": 422,
        "source": "claude:usage",
    }


def test_agy_reader_is_explicitly_unmeasured_in_phase_one() -> None:
    usage = read_agy_transcript(FIXTURES / "agy-real-sample.jsonl")

    assert usage["source"] == "unmeasured"
    assert usage["why"] == "agy: runtime reader is deferred"


def test_cursor_is_unmeasured_and_never_a_zero() -> None:
    usage = read_runtime("cursor", FIXTURES / "missing.jsonl")

    assert usage["source"] == "unmeasured"
    assert "input" not in usage
    assert cap_total(usage) is None


def test_p90_is_rounded_up_and_empty_tier_has_no_default() -> None:
    assert p90([10, 20, 30, 40]) == 37
    assert p90([]) is None


def test_tier_defaults_only_use_measured_records(tmp_path: Path, monkeypatch) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"tiers": {"efficient": ["gpt-5.6-luna"], "top": ["claude-opus-5"]}}),
        encoding="utf-8",
    )
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    codex.mkdir()
    claude.mkdir()
    (codex / "one.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"model": "gpt-5.6-luna"}})
        + "\n"
        + json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 2,
                            "output_tokens": 3,
                            "total_tokens": 13,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    defaults, counts = tier_defaults(policy, codex_root=codex, claude_root=claude)

    assert defaults == {"efficient": 13}
    assert counts == {"efficient": 1}


def test_quota_guard_marks_14_percent_remaining_as_known(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-11-15T00:00:00Z",
                "type": "event_msg",
                "payload": {"type": "token_count"},
                "rate_limits": {
                    "secondary": {
                        "used_percent": 86,
                        "resets_at": 1_800_000_000,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    status = latest_codex_quota(tmp_path, now=1_763_164_800)

    assert status["known"] is True
    assert status["remaining_percent"] == 14.0


def test_quota_guard_16_percent_remaining_passes_threshold(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-11-15T00:00:00Z",
                "type": "event_msg",
                "payload": {"type": "token_count"},
                "rate_limits": {
                    "secondary": {
                        "used_percent": 84,
                        "resets_at": 1_800_000_000,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert latest_codex_quota(tmp_path, now=1_763_164_800)["remaining_percent"] == 16.0


def test_quota_guard_treats_a_stale_snapshot_as_unknown(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2020-01-01T00:00:00Z",
                "type": "event_msg",
                "payload": {"type": "token_count"},
                "rate_limits": {
                    "secondary": {
                        "used_percent": 99,
                        "resets_at": 1_900_000_000,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert latest_codex_quota(tmp_path, now=1_763_164_800)["known"] is False


def test_quota_cli_applies_the_threshold_guard(tmp_path: Path) -> None:
    (tmp_path / "quota.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-11-15T00:00:00Z",
                "type": "event_msg",
                "payload": {"type": "token_count"},
                "rate_limits": {
                    "primary": {
                        "used_percent": 86,
                        "window_minutes": 10080,
                        "resets_at": 1_800_000_000,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [sys.executable, str(script), "quota", "--runtime", "codex", "--root", str(tmp_path), "--threshold", "15"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["blocked"] is True


def test_settle_usage_is_idempotent_and_stores_unmeasured_state(tmp_path: Path) -> None:
    contract = tmp_path / "contract.md"
    contract.write_text("dispatch contract", encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 2,
                "runtimes": ["codex"],
                "tiers": {"efficient": ["gpt-5.6-luna"]},
                "fanout_caps": {},
            }
        ),
        encoding="utf-8",
    )
    gate = DispatchGate(
        DispatchGateConfig(
            ledger_path=tmp_path / "ledger.jsonl",
            ticket_dir=tmp_path / "tickets",
            tier_policy_path=policy,
            known_roots_path=tmp_path / "roots.json",
        )
    )
    assert gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=contract,
            est_input_chars=10,
            n_agents=1,
            completion_channel="sentinel-log",
        )
    ).allow
    assert gate.register_job("job-1", lambda value: value == "job-1", token_budget=100).allow
    usage = {"source": "unmeasured", "why": "cursor has no reader"}
    assert gate.settle_usage("job-1", usage).allow
    assert gate.settle_usage("job-1", {"source": "unmeasured", "why": "late"}).allow
    row = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["token_budget"] == 100
    assert row["token_usage"] == usage
