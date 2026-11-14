"""Provider usage readers and the quota guard's measured states."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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
        "input": 402,
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


def test_tier_defaults_only_use_measured_records(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"tiers": {"efficient": ["gpt-5.6-luna"], "top": ["claude-opus-5"]}}),
        encoding="utf-8",
    )
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    codex.mkdir()
    claude.mkdir()
    complete = (
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
        + "\n"
    )
    for index in range(10):
        (codex / f"complete-{index}.jsonl").write_text(complete, encoding="utf-8")
    (codex / "incomplete.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"model": "gpt-5.6-luna"}})
        + "\n"
        + json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 20}},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    defaults, counts = tier_defaults(policy, codex_root=codex, claude_root=claude)

    assert defaults == {"efficient": 13}
    assert counts == {"efficient": 10}


def test_tier_defaults_apply_uncached_basis(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"tiers": {"efficient": ["gpt-5.6-luna"]}}), encoding="utf-8")
    codex = tmp_path / "codex"
    codex.mkdir()
    complete = (
        json.dumps({"type": "session_meta", "payload": {"model": "gpt-5.6-luna"}})
        + "\n"
        + json.dumps(
            {
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
                }
            }
        )
        + "\n"
    )
    for index in range(10):
        (codex / f"complete-{index}.jsonl").write_text(complete, encoding="utf-8")

    defaults, counts = tier_defaults(
        policy, codex_root=codex, claude_root=tmp_path / "claude", basis="uncached"
    )

    assert defaults == {"efficient": 11}
    assert counts == {"efficient": 10}


def test_tier_defaults_require_recent_minimum_and_recompute_cache(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"tiers": {"efficient": ["gpt-5.6-luna"]}}), encoding="utf-8")
    codex = tmp_path / "codex"
    codex.mkdir()
    complete = (
        json.dumps({"type": "session_meta", "payload": {"model": "gpt-5.6-luna"}})
        + "\n"
        + json.dumps(
            {
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
                }
            }
        )
        + "\n"
    )
    for index in range(9):
        (codex / f"recent-{index}.jsonl").write_text(complete, encoding="utf-8")
    old = codex / "old.jsonl"
    old.write_text(complete, encoding="utf-8")
    old_time = time.time() - 31 * 24 * 60 * 60
    os.utime(old, (old_time, old_time))
    cache = tmp_path / "defaults.json"

    defaults, counts = tier_defaults(
        policy, codex_root=codex, claude_root=tmp_path / "claude", cache_path=cache
    )
    assert defaults == {}
    assert counts == {"efficient": 9}

    (codex / "recent-9.jsonl").write_text(complete, encoding="utf-8")
    defaults, counts = tier_defaults(
        policy, codex_root=codex, claude_root=tmp_path / "claude", cache_path=cache
    )
    assert defaults == {"efficient": 13}
    assert counts == {"efficient": 10}

    larger = complete.replace('"total_tokens": 13', '"total_tokens": 100')
    for index in range(5):
        (codex / f"recent-{index}.jsonl").write_text(larger, encoding="utf-8")
    defaults, counts = tier_defaults(
        policy, codex_root=codex, claude_root=tmp_path / "claude", cache_path=cache
    )
    assert defaults == {"efficient": 100}
    assert counts == {"efficient": 10}


def test_quota_uses_only_the_dispatch_account(monkeypatch, tmp_path: Path) -> None:
    accounts = tmp_path / "accounts"
    exhausted = accounts / "exhausted" / "home" / "sessions"
    dispatch = accounts / "dispatch" / "home" / "sessions"
    exhausted.mkdir(parents=True)
    dispatch.mkdir(parents=True)
    def event(used: int) -> str:
        return json.dumps(
            {
                "timestamp": 1_000,
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": used,
                            "window_minutes": 10080,
                            "resets_at": 5_000,
                        }
                    },
                },
            }
        ) + "\n"
    (exhausted / "fresh.jsonl").write_text(event(99), encoding="utf-8")
    (dispatch / "worker.jsonl").write_text(event(10), encoding="utf-8")
    monkeypatch.setenv("CODEX_ACCOUNTS_DIR", str(accounts))
    monkeypatch.setenv("CODEX_HOME", str(accounts / "dispatch" / "home"))

    status = latest_codex_quota(now=1_100)

    assert status["known"] is True
    assert status["remaining_percent"] == 90.0

    monkeypatch.delenv("CODEX_HOME")
    assert latest_codex_quota(now=1_100)["why"] == "account unresolved"


def test_quota_scans_newest_file_then_stops_at_first_valid_snapshot(tmp_path: Path) -> None:
    newer = tmp_path / "newer.jsonl"
    older = tmp_path / "older.jsonl"
    newer.write_text(
        json.dumps(
            {
                "timestamp": 1_000,
                "payload": {
                    "type": "token_count",
                    "rate_limits": {"primary": {"used_percent": 99, "window_minutes": 10080}},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    older.write_text(
        json.dumps(
            {
                "timestamp": 1_100,
                "payload": {
                    "type": "token_count",
                    "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 10080}},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    now = time.time()
    os.utime(newer, (now, now))
    os.utime(older, (now - 10, now - 10))

    status = latest_codex_quota(tmp_path, now=1_100)

    assert status["known"] is True
    assert status["remaining_percent"] == 1.0


def test_quota_guard_marks_14_percent_remaining_as_known(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": 1_000,
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": 86,
                            "window_minutes": 10080,
                            "resets_at": 5_000,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    status = latest_codex_quota(tmp_path, now=1_100)

    assert status["known"] is True
    assert status["remaining_percent"] == 14.0


def test_quota_guard_16_percent_remaining_passes_threshold(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": 1_000,
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": 84,
                            "window_minutes": 10080,
                            "resets_at": 5_000,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "quota",
            "--runtime",
            "codex",
            "--root",
            str(tmp_path),
            "--threshold",
            "15",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert json.loads(result.stdout)["blocked"] is False


def test_quota_guard_treats_a_stale_snapshot_as_unknown(tmp_path: Path) -> None:
    path = tmp_path / "quota.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": 1_000,
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": 99,
                            "window_minutes": 10080,
                            "resets_at": 5_000,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert latest_codex_quota(tmp_path, now=1_000 + 10080 * 60 + 1)["known"] is False


def test_quota_cli_applies_the_threshold_guard(tmp_path: Path) -> None:
    now = time.time()
    (tmp_path / "quota.jsonl").write_text(
        json.dumps(
            {
                "timestamp": now,
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": 86,
                            "window_minutes": 10080,
                            "resets_at": now + 3_600,
                        }
                    },
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
    for label, value in (("negative", -1), ("bool", True), ("string", "100")):
        invalid = gate.register_job(
            f"bad-{label}", lambda value: value.startswith("bad-"), token_budget=value
        )
        assert invalid.allow is False
        assert invalid.reason.value == "INVALID_REQUEST"
    assert not (tmp_path / "ledger.jsonl").exists()
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
    invalid = gate.register_job("bad", lambda value: value == "bad", tokens_basis=[])
    assert invalid.allow is False
    assert invalid.reason.value == "INVALID_REQUEST"
    assert gate.register_job("job-1", lambda value: value == "job-1", token_budget=100).allow
    usage = {"source": "unmeasured", "why": "cursor has no reader"}
    assert gate.settle_usage("job-1", usage).allow
    measured = {
        "input": 4,
        "cached_input": 1,
        "output": 2,
        "total": 6,
        "source": "codex:token_count",
    }
    assert gate.settle_usage("job-1", measured).allow
    assert gate.settle_usage("job-1", {"source": "unmeasured", "why": "late"}).allow
    row = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["token_budget"] == 100
    assert row["token_usage"] == measured
    entries = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sum(entry.get("job_id") == "job-1" and "token_usage" in entry for entry in entries) == 1

    assert gate.settle_usage("pre-pr-job", usage).allow
    assert gate.settle_usage("pre-pr-job", measured).allow
    pre_pr = [
        entry
        for entry in gate.ledger_entries()
        if entry.get("settlement_dispatch_id") == "pre-pr-job"
    ]
    assert len(pre_pr) == 1
    assert pre_pr[0]["settlement_without_registration"] is True
    assert pre_pr[0]["token_usage"] == measured

    denied_ledger = tmp_path / "denied-ledger.jsonl"
    denied_ledger.write_text(
        json.dumps({"job_id": "denied-job", "decision": "DENY"}) + "\n",
        encoding="utf-8",
    )
    denied_gate = DispatchGate(
        DispatchGateConfig(
            ledger_path=denied_ledger,
            ticket_dir=tmp_path / "denied-tickets",
            tier_policy_path=policy,
            known_roots_path=tmp_path / "denied-roots.json",
        )
    )
    assert denied_gate.settle_usage("denied-job", measured).allow
    denied_entries = [
        entry for entry in denied_gate.ledger_entries() if entry.get("settlement_dispatch_id") == "denied-job"
    ]
    assert len(denied_entries) == 1
    assert "job_id" not in denied_entries[0]


def test_settle_cli_accepts_omitted_runtime(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--ledger",
            str(ledger),
            "settle",
            "--dispatch-id",
            "pre-pr-cli",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["allow"] is True

    record = tmp_path / "record.jsonl"
    record.write_text("{}\n", encoding="utf-8")
    with_record = subprocess.run(
        [
            sys.executable,
            str(script),
            "--ledger",
            str(tmp_path / "with-record-ledger.jsonl"),
            "settle",
            "--dispatch-id",
            "pre-pr-cli-record",
            "--record",
            str(record),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert with_record.returncode == 2
    assert "--record requires --runtime" in with_record.stderr


def test_budget_cli_revalidates_declared_tokens(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"tiers": {"efficient": []}}), encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "budget",
            "--tier",
            "efficient",
            "--tier-policy",
            str(policy),
            "--front-matter",
            '{"budget":{"tokens":true}}',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 2
    assert "budget.tokens must be a nonnegative integer" in result.stderr
