from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from master_runtime.core.dispatch_gate import (
    DispatchGate,
    DispatchGateConfig,
    DispatchRequest,
    ReasonCode,
)
from master_runtime.core.watchdog import StallStatus, check_stall


def test_r1_allows_dispatch_under_budget(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "normal contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            purpose="small dispatch",
        )
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert decision.cost_proxy == 10_000


def test_r1_denies_single_contract_over_limit(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "oversized contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=500_001,
            n_agents=1,
            purpose="too large",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.BUDGET_EXCEEDED


def test_r1_denies_batch_cost_over_limit(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "large batch contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=400_000,
            n_agents=3,
            purpose="large batch",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.BUDGET_EXCEEDED
    assert decision.cost_proxy == 1_200_000


def test_r2_allows_single_high_cost_runtime_with_warning(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "single fable contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="fable",
            contract_path=contract,
            est_input_chars=120_000,
            n_agents=1,
            purpose="single high-cost analysis",
        )
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert decision.warnings == (ReasonCode.HIGH_COST_RUNTIME,)


def test_r2_denies_multi_agent_high_cost_runtime(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "multi fable contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="fable",
            contract_path=contract,
            est_input_chars=120_000,
            n_agents=2,
            purpose="fanout",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.ROUTING_VIOLATION


def test_r3_denies_recent_duplicate_contract(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "same contract")
    now = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=now)

    first = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )
    second = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert first.allow is True
    assert second.allow is False
    assert second.reason == ReasonCode.DUPLICATE_CONTRACT


def test_r3_allows_duplicate_after_window(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "repeatable later")
    now = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=now)

    first = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )
    now.value += 1_801
    second = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert first.allow is True
    assert second.allow is True


def test_r4_registers_verified_job_id(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "verified job")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job("job-123", lambda job_id: job_id == "job-123")

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert _ledger_entries(tmp_path)[-1]["job_id"] == "job-123"


def test_r4_denies_unverified_job_id(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "unverified job")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job("ghost-job", lambda job_id: False)

    assert decision.allow is False
    assert decision.reason == ReasonCode.UNVERIFIED_JOB
    assert all("job_id" not in entry for entry in _ledger_entries(tmp_path))


def test_cli_check_register_and_watch_commands(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "cli contract")
    ledger = tmp_path / "cli-ledger.jsonl"

    check_result = subprocess.run(
        [
            str(_script()),
            "--ledger",
            str(ledger),
            "check",
            "--runtime",
            "codex",
            "--contract",
            str(contract),
            "--agents",
            "1",
            "--est-chars",
            "1000",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    register_result = subprocess.run(
        [
            str(_script()),
            "--ledger",
            str(ledger),
            "register",
            "--job-id",
            "job-cli",
            "--probe-cmd",
            "printf job-cli",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    log = tmp_path / "worker.log"
    log.write_text("progress\n", encoding="utf-8")
    watch_result = subprocess.run(
        [
            str(_script()),
            "watch",
            "--log",
            str(log),
            "--max-idle",
            "9999999999",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check_result.returncode == 0, check_result.stderr
    assert register_result.returncode == 0, register_result.stderr
    assert watch_result.returncode == 0, watch_result.stderr


def test_incident_a_fable_fanout_denied(tmp_path: Path) -> None:
    # Scenario A: high-cost model fan-out should be enforced by code, not judgment.
    contract = _contract(tmp_path, "fanout contract")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="fable",
            contract_path=contract,
            est_input_chars=120_000,
            n_agents=6,
            purpose="large fanout",
        )
    )

    assert decision.allow is False
    assert decision.reason in {
        ReasonCode.ROUTING_VIOLATION,
        ReasonCode.BUDGET_EXCEEDED,
    }


def test_incident_b_duplicate_contract_denied(tmp_path: Path) -> None:
    # Scenario B: the same contract must not be dispatched twice by a forwarder.
    contract = _contract(tmp_path, "duplicate contract")
    gate = _gate(tmp_path, now=1_000)

    first = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )
    second = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert first.allow is True
    assert second.allow is False
    assert second.reason == ReasonCode.DUPLICATE_CONTRACT


def test_incident_c_missing_probe_job_id_denies_registration(tmp_path: Path) -> None:
    # Scenario C: worker self-report of a job id is not evidence without a probe.
    contract = _contract(tmp_path, "ghost job")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job("job-404", lambda job_id: False)

    assert decision.allow is False
    assert decision.reason == ReasonCode.UNVERIFIED_JOB


def test_incident_d_old_log_mtime_is_stalled(tmp_path: Path) -> None:
    # Scenario D: long inactivity in a worker log should be detected early.
    log = tmp_path / "worker.log"
    log.write_text("last progress\n", encoding="utf-8")
    os.utime(log, (400, 400))

    decision = check_stall(log, max_idle_seconds=360, now=1_000)

    assert decision.status == StallStatus.STALLED
    assert decision.stalled is True
    assert decision.idle_seconds == 600


def test_watchdog_uses_injected_progress_timestamp(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text("noise\nprogress at 500\nnoise\n", encoding="utf-8")
    os.utime(log, (990, 990))

    decision = check_stall(
        log,
        max_idle_seconds=360,
        progress_predicate=lambda line: 500 if line.startswith("progress") else None,
        now=1_000,
    )

    assert decision.status == StallStatus.STALLED
    assert decision.last_progress_at == 500


class _MutableClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _gate(
    tmp_path: Path,
    now: float | None = None,
    clock: _MutableClock | None = None,
) -> DispatchGate:
    return DispatchGate(
        DispatchGateConfig(ledger_path=tmp_path / "ledger.jsonl"),
        clock=clock or (lambda: now if now is not None else 1_000),
    )


def _contract(tmp_path: Path, content: str) -> Path:
    contract = tmp_path / f"{abs(hash(content))}.md"
    contract.write_text(content, encoding="utf-8")
    return contract


def _ledger_entries(tmp_path: Path) -> list[dict[str, object]]:
    ledger = tmp_path / "ledger.jsonl"
    return [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "dispatch-gate"
