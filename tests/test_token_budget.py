"""Provider usage readers and declared token-budget settlement."""

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
    read_agy_transcript,
    read_claude_transcript,
    read_codex_rollout,
    read_runtime,
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


def test_invalid_utf8_does_not_stop_claude_usage_sum(tmp_path: Path) -> None:
    transcript = tmp_path / "claude.jsonl"
    first = {"message": {"id": "first", "usage": {
        "input_tokens": 10,
        "cache_creation_input_tokens": 2,
        "cache_read_input_tokens": 3,
        "output_tokens": 4,
    }}}
    second = {"message": {"id": "second", "usage": {
        "input_tokens": 20,
        "cache_creation_input_tokens": 1,
        "cache_read_input_tokens": 5,
        "output_tokens": 6,
    }}}
    transcript.write_bytes(
        (json.dumps(first) + "\n").encode()
        + b"{\xff\n"
        + (json.dumps(second) + "\n").encode()
    )

    assert read_claude_transcript(transcript) == {
        "input": 41,
        "cached_input": 8,
        "output": 10,
        "total": 51,
        "source": "claude:usage",
    }


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
    assert gate.register_job(
        "job-1",
        lambda value: value == "job-1",
        token_budget=100,
        tokens_basis="uncached",
        token_budget_source="declared",
    ).allow
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
    later_measured = {
        "input": 40,
        "cached_input": 10,
        "output": 20,
        "total": 60,
        "source": "claude:usage",
    }
    assert gate.settle_usage("job-1", later_measured).allow
    row = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["token_budget"] == 100
    assert row["tokens_basis"] == "uncached"
    assert row["token_budget_source"] == "declared"
    assert row["token_usage"] == measured
    entries = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sum(entry.get("job_id") == "job-1" and "token_usage" in entry for entry in entries) == 1


def test_settle_unknown_dispatch_does_not_append_an_orphan(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"version": 2, "runtimes": ["codex"], "tiers": {"efficient": []}, "fanout_caps": {}}),
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.jsonl"
    gate = DispatchGate(
        DispatchGateConfig(
            ledger_path=ledger,
            ticket_dir=tmp_path / "tickets",
            tier_policy_path=policy,
            known_roots_path=tmp_path / "roots.json",
        )
    )

    decision = gate.settle_usage("unknown-job", {"source": "unmeasured", "why": "late"})

    assert decision.allow is False
    assert decision.reason.value == "NO_MATCHING_TICKET"
    assert not ledger.exists()


def test_register_no_cap_columns_are_explicitly_unset(tmp_path: Path) -> None:
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
    ledger = tmp_path / "ledger.jsonl"
    gate = DispatchGate(
        DispatchGateConfig(
            ledger_path=ledger,
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
    assert gate.register_job(
        "job-no-cap",
        lambda value: value == "job-no-cap",
        tokens_basis="total",
        token_budget_source="unset:no-cap",
    ).allow
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert row["token_budget"] is None
    assert row["tokens_basis"] == "total"
    assert row["token_budget_source"] == "unset:no-cap"


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
            "unknown-cli",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 2
    assert "NO_MATCHING_TICKET" in result.stdout

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
            "unknown-cli-record",
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
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "budget",
            "--front-matter",
            '{"budget":{"tokens":true}}',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 2
    assert "budget.tokens must be a positive integer" in result.stderr


def test_budget_cli_rejects_zero_tokens() -> None:
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "budget",
            "--front-matter",
            '{"budget":{"tokens":0}}',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 2
    assert "budget.tokens must be a positive integer" in result.stderr


def test_budget_cli_rejects_malformed_front_matter() -> None:
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "budget",
            "--front-matter",
            '{"budget":',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 2
    assert "front matter must be valid JSON" in result.stderr


def test_budget_cli_leaves_undeclared_cap_unset() -> None:
    script = Path(__file__).parents[1] / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "budget",
            "--front-matter",
            '{"tokens_basis":"uncached"}',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "source": "unset:no-cap",
        "token_budget": None,
        "tokens_basis": "uncached",
    }
