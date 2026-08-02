from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
from pathlib import Path

import master_runtime.core.dispatch_gate as dispatch_gate
from master_runtime.core.dispatch_gate import (
    DispatchGate,
    DispatchGateConfig,
    DispatchRequest as _DispatchRequest,
    GateDecision,
    ReasonCode,
)
from master_runtime.core.watchdog import StallStatus, check_stall


def DispatchRequest(*args, **kwargs):
    kwargs.setdefault("completion_channel", "sentinel-log")
    kwargs.setdefault("model", "gpt-5.6-luna")
    return _DispatchRequest(*args, **kwargs)


def test_check_without_completion_channel_records_denial_in_ledger(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "missing completion channel")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            model="gpt-5.6-luna",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.NO_COMPLETION_CHANNEL
    assert _ledger_entries(tmp_path)[-1]["reason"] == "NO_COMPLETION_CHANNEL"


def test_check_records_orchestration_completion_channel(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "orchestration completion channel")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="orchestration",
            model="gpt-5.6-luna",
        )
    )

    assert decision.allow is True
    assert _ledger_entries(tmp_path)[-1]["completion_channel"] == "orchestration"


def test_check_without_model_records_denial_in_ledger(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "missing model")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="orchestration",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.NO_MODEL
    assert _ledger_entries(tmp_path)[-1]["reason"] == "NO_MODEL"


def test_check_records_model(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "model recorded")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="orchestration",
            model="gpt-5.6-luna",
        )
    )

    assert decision.allow is True
    assert _ledger_entries(tmp_path)[-1]["model"] == "gpt-5.6-luna"


def test_check_records_sentinel_log_completion_channel(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "sentinel-log completion channel")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="sentinel-log",
            model="gpt-5.6-luna",
        )
    )

    assert decision.allow is True
    assert _ledger_entries(tmp_path)[-1]["completion_channel"] == "sentinel-log"


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


def test_unmeasured_contract_fails_closed_before_validation_and_budget(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "readable but deliberately unmeasured")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=None,
            n_agents=1_000_000,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_UNREADABLE
    assert decision.cost_proxy == 0
    assert _ledger_entries(tmp_path)[-1]["est_chars"] is None


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


def test_check_allow_issues_dispatch_ticket_with_contract_fixture(
    tmp_path: Path,
) -> None:
    contract = _dispatch_contract(tmp_path, runtime="grok")
    gate = _gate(tmp_path, now=1_700_000_000)

    decision = gate.check(
        DispatchRequest(
            runtime="grok",
            contract_path=contract,
            est_input_chars=25_000,
            n_agents=3,
            purpose="u5 ticket issuance",
        )
    )

    contract_sha = _sha256(contract)
    ticket = tmp_path / "dispatch-tickets" / f"grok-{contract_sha[:12]}.json"

    assert decision.allow is True
    assert decision.contract_sha == contract_sha
    assert json.loads(ticket.read_text(encoding="utf-8")) == {
        "runtime": "grok",
        "contract_sha": contract_sha,
        "issued_ts": 1_700_000_000,
        "count": 3,
    }


def test_check_deny_does_not_issue_dispatch_ticket(tmp_path: Path) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    gate = _gate(tmp_path, now=1_700_000_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=500_001,
            n_agents=1,
            purpose="u5 denial path",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.BUDGET_EXCEEDED
    assert not (tmp_path / "dispatch-tickets").exists()


def test_check_rejects_invalid_runtimes_without_ticket(
    tmp_path: Path,
) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    invalid_runtimes = ("../escape", "Codex", "a" * 33)

    for runtime in invalid_runtimes:
        case_dir = tmp_path / runtime.replace("/", "_")
        gate = DispatchGate(
            DispatchGateConfig(
                ledger_path=case_dir / "ledger.jsonl",
                ticket_dir=case_dir / "dispatch-tickets",
            ),
            clock=lambda: 1_700_000_000,
        )

        decision = gate.check(
            DispatchRequest(
                runtime=runtime,
                contract_path=contract,
                est_input_chars=25_000,
                n_agents=1,
                purpose="u5 invalid runtime regression",
            )
        )

        assert decision.allow is False
        assert decision.reason == ReasonCode.INVALID_REQUEST
        assert not (case_dir / "dispatch-tickets").exists()
        assert not (case_dir.parent / "escape").exists()


def test_issue_dispatch_ticket_confines_runtime_path_escape(
    tmp_path: Path,
) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    gate = _gate(tmp_path, now=1_700_000_000)

    gate._issue_dispatch_ticket(
        DispatchRequest(
            runtime="../escape",
            contract_path=contract,
            est_input_chars=25_000,
            n_agents=1,
            purpose="u5 ticket confinement regression",
        ),
        GateDecision(
            allow=True,
            reason=ReasonCode.OK,
            contract_sha="b" * 64,
            cost_proxy=25_000,
        ),
    )

    assert list((tmp_path / "dispatch-tickets").glob("*.json")) == []
    assert not (tmp_path / "escape-bbbbbbbbbbbb.json").exists()


def test_issue_dispatch_ticket_uses_tmp_then_os_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    gate = _gate(tmp_path, now=1_700_000_000)
    contract_sha = _sha256(contract)
    ticket = tmp_path / "dispatch-tickets" / f"codex-{contract_sha[:12]}.json"
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = dispatch_gate.os.replace

    def tracking_replace(
        src: str | os.PathLike[str],
        dst: str | os.PathLike[str],
    ) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        replace_calls.append((src_path, dst_path))
        assert src_path.name.startswith(f".{ticket.name}.")
        assert src_path.name.endswith(".tmp")
        assert src_path.exists()
        assert not dst_path.exists()
        real_replace(src, dst)

    monkeypatch.setattr(dispatch_gate.os, "replace", tracking_replace)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=25_000,
            n_agents=1,
            purpose="u5 atomic ticket regression",
        )
    )

    assert decision.allow is True
    assert len(replace_calls) == 1
    tmp_ticket, final_ticket = replace_calls[0]
    assert final_ticket == ticket
    assert ticket.exists()
    assert not tmp_ticket.exists()
    assert json.loads(ticket.read_text(encoding="utf-8"))["count"] == 1


def test_issue_dispatch_ticket_allow_guard_skips_deny_decision(
    tmp_path: Path,
) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    gate = _gate(tmp_path, now=1_700_000_000)

    gate._issue_dispatch_ticket(
        DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=500_001,
            n_agents=1,
            purpose="u5 allow guard regression",
        ),
        GateDecision(
            allow=False,
            reason=ReasonCode.BUDGET_EXCEEDED,
            contract_sha="c" * 64,
            cost_proxy=500_001,
        ),
    )

    assert not (tmp_path / "dispatch-tickets").exists()


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


def test_cli_register_with_verified_orchestration_task_records_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _contract(tmp_path, "orchestration registration")
    ledger = tmp_path / "ledger.jsonl"
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "check",
                "--runtime",
                "codex",
                "--model",
                "gpt-5.6-luna",
                "--contract",
                str(contract),
                "--agents",
                "1",
                "--est-chars",
                "1000",
                "--completion-channel",
                "orchestration",
            ]
        )
        == 0
    )

    def successful_probe(command, **kwargs):
        if isinstance(command, list):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"ok": true, "result": {"dispatch": {"id": "d1"}}}',
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="job-orch",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", successful_probe)

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-orch",
                "--probe-cmd",
                "printf job-orch",
                "--orchestration-task",
                "task-orch-123",
            ]
        )
        == 0
    )
    assert _ledger_entries(tmp_path)[-1]["orchestration_task"] == "task-orch-123"


def test_cli_register_requires_orchestration_task(tmp_path: Path, capsys) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "ledger.jsonl"

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-without-task",
                "--probe-cmd",
                "printf job-without-task",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"ORCHESTRATION_UNVERIFIED"' in output.out
    assert "ORCHESTRATION_UNVERIFIED" in output.err
    ledger_entry = json.loads(ledger.read_text(encoding="utf-8"))
    assert ledger_entry["reason"] == "ORCHESTRATION_UNVERIFIED"
    assert ledger_entry["probe_failure"] == "task_not_found"


def test_cli_register_denies_unverified_orchestration_task_with_ledger_entry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract = _contract(tmp_path, "failed orchestration registration")
    ledger = tmp_path / "ledger.jsonl"
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "check",
                "--runtime",
                "codex",
                "--model",
                "gpt-5.6-luna",
                "--contract",
                str(contract),
                "--agents",
                "1",
                "--est-chars",
                "1000",
                "--completion-channel",
                "orchestration",
            ]
        )
        == 0
    )
    capsys.readouterr()

    def null_dispatch_probe(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"ok": true, "result": {"dispatch": null}}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", null_dispatch_probe)

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-orch-failed",
                "--probe-cmd",
                "printf job-orch-failed",
                "--orchestration-task",
                "task-orch-failed",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"ORCHESTRATION_UNVERIFIED"' in output.out
    assert "ORCHESTRATION_UNVERIFIED" in output.err
    assert any(
        entry.get("job_id") == "job-orch-failed"
        and entry.get("reason") == "ORCHESTRATION_UNVERIFIED"
        and entry.get("probe_failure") == "task_not_found"
        for entry in _ledger_entries(tmp_path)
    )


def test_cli_orchestration_probe_requires_success_ok_true_and_dispatch(
    monkeypatch,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    results = iter(
        (
            type("Result", (), {"returncode": 1, "stdout": '{"ok": true}'})(),
            type("Result", (), {"returncode": 0, "stdout": '{"ok": false}'})(),
            type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": '{"ok": true, "result": {"dispatch": null}}',
                },
            )(),
            type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": '{"ok": true, "result": {"dispatch": {"id": "d1"}}}',
                },
            )(),
        )
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))

    probe_failure = script["ProbeFailure"]
    assert (
        script["_probe_orchestration_task"]("task-nonzero")
        == probe_failure.TASK_NOT_FOUND
    )
    assert (
        script["_probe_orchestration_task"]("task-not-ok")
        == probe_failure.TASK_NOT_FOUND
    )
    assert (
        script["_probe_orchestration_task"]("task-null-dispatch")
        == probe_failure.TASK_NOT_FOUND
    )
    assert script["_probe_orchestration_task"]("task-with-dispatch") is None


def test_cli_orchestration_probe_uses_resolved_command_and_timeout(monkeypatch) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    calls = []

    def successful_probe(command, **kwargs):
        calls.append((command, kwargs))
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"ok": true, "result": {"dispatch": {"id": "d1"}}}',
            },
        )()

    monkeypatch.setenv("ORCA_CLI_COMMAND", "orca-custom")
    monkeypatch.setattr(subprocess, "run", successful_probe)

    assert script["_probe_orchestration_task"]("task-timeout") is None
    assert calls[0][0][0] == "orca-custom"
    assert calls[0][1]["timeout"] == script["ORCHESTRATION_PROBE_TIMEOUT_SECONDS"]


def test_cli_orchestration_probe_treats_timeout_as_unverified(monkeypatch) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")

    def timed_out_probe(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timed_out_probe)

    assert (
        script["_probe_orchestration_task"]("task-timeout")
        == script["ProbeFailure"].PROBE_TIMEOUT
    )


def test_cli_register_records_distinct_orchestration_probe_failures(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    cases = (
        (
            "orca_missing",
            lambda command, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError(command[0])
            ),
        ),
        (
            "probe_timeout",
            lambda command, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(command, kwargs["timeout"])
            ),
        ),
        (
            "probe_unparseable",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 0, stdout="not-json", stderr=""
            ),
        ),
        (
            "task_not_found",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 1, stdout="", stderr="task not found"
            ),
        ),
    )

    for failure_reason, probe in cases:
        ledger = tmp_path / f"{failure_reason}.jsonl"
        monkeypatch.setattr(subprocess, "run", probe)
        assert (
            script["main"](
                [
                    "--ledger",
                    str(ledger),
                    "register",
                    "--job-id",
                    f"job-{failure_reason}",
                    "--probe-cmd",
                    f"printf job-{failure_reason}",
                    "--orchestration-task",
                    f"task-{failure_reason}",
                ]
            )
            == 2
        )
        capsys.readouterr()
        entry = json.loads(ledger.read_text(encoding="utf-8"))
        assert entry["reason"] == "ORCHESTRATION_UNVERIFIED"
        assert entry["probe_failure"] == failure_reason


def test_cli_check_missing_contract_without_estimate_returns_gate_denial(
    tmp_path: Path, capsys
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    missing_contract = tmp_path / "missing-contract.md"
    ledger = tmp_path / "ledger.jsonl"

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "check",
                "--runtime",
                "codex",
                "--model",
                "gpt-5.6-luna",
                "--contract",
                str(missing_contract),
                "--agents",
                "1",
                "--completion-channel",
                "orchestration",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"CONTRACT_UNREADABLE"' in output.out
    assert "Traceback" not in output.err
    assert json.loads(ledger.read_text(encoding="utf-8"))["est_chars"] is None


def test_register_consumes_matching_pending_dispatch_by_contract_sha(
    tmp_path: Path,
) -> None:
    first_contract = _contract(tmp_path, "first parallel dispatch")
    second_contract = _contract(tmp_path, "second parallel dispatch")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        DispatchRequest("codex", first_contract, est_input_chars=10_000, n_agents=1)
    )
    gate.check(
        DispatchRequest("codex", second_contract, est_input_chars=10_000, n_agents=1)
    )

    first_sha = _sha256(first_contract)
    decision = gate.register_job(
        "job-first",
        lambda job_id: job_id == "job-first",
        contract_sha=first_sha[:12],
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert _ledger_entries(tmp_path)[-1]["contract_sha"] == first_sha


def test_register_denies_ambiguous_pending_dispatch_without_contract_sha(
    tmp_path: Path,
) -> None:
    first_contract = _contract(tmp_path, "first ambiguous dispatch")
    second_contract = _contract(tmp_path, "second ambiguous dispatch")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        DispatchRequest("codex", first_contract, est_input_chars=10_000, n_agents=1)
    )
    gate.check(
        DispatchRequest("codex", second_contract, est_input_chars=10_000, n_agents=1)
    )

    decision = gate.register_job("job-ambiguous", lambda job_id: job_id)

    assert decision.allow is False
    assert decision.reason == ReasonCode.AMBIGUOUS_TICKET
    assert _sha256(first_contract) in decision.message
    assert _sha256(second_contract) in decision.message
    assert all("job_id" not in entry for entry in _ledger_entries(tmp_path))


def test_register_ignores_expired_tickets_but_preserves_them_within_grace_window(
    tmp_path: Path,
) -> None:
    first_contract = _contract(tmp_path, "expired dispatch")
    second_contract = _contract(tmp_path, "fresh dispatch")
    now = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=now)
    gate.check(
        DispatchRequest("codex", first_contract, est_input_chars=10_000, n_agents=1)
    )
    now.value += 601
    gate.check(
        DispatchRequest("codex", second_contract, est_input_chars=10_000, n_agents=1)
    )

    decision = gate.register_job("job-fresh", lambda job_id: job_id == "job-fresh")

    assert decision.allow is True
    assert decision.contract_sha == _sha256(second_contract)
    assert (
        tmp_path / "dispatch-tickets" / f"codex-{_sha256(first_contract)[:12]}.json"
    ).exists()
    assert _ledger_entries(tmp_path)[-1]["contract_sha"] == _sha256(second_contract)


def test_register_without_contract_sha_requires_one_valid_ticket(
    tmp_path: Path,
) -> None:
    first_contract = _contract(tmp_path, "first valid ticket")
    second_contract = _contract(tmp_path, "second valid ticket")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        DispatchRequest("codex", first_contract, est_input_chars=10_000, n_agents=1)
    )
    gate.check(
        DispatchRequest("cursor", second_contract, est_input_chars=10_000, n_agents=1)
    )

    decision = gate.register_job("job-ambiguous", lambda job_id: job_id)

    assert decision.allow is False
    assert decision.reason == ReasonCode.AMBIGUOUS_TICKET
    assert decision.message == (
        "candidate_contract_shas="
        + ",".join(sorted([_sha256(first_contract), _sha256(second_contract)]))
    )


def test_register_with_contract_sha_allows_expired_ticket_and_consumes_it(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "expired ticket can still register")
    now = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=now)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))
    contract_sha = _sha256(contract)
    ticket = tmp_path / "dispatch-tickets" / f"codex-{contract_sha[:12]}.json"
    now.value += 601

    decision = gate.register_job(
        "job-expired-ticket",
        lambda job_id: job_id == "job-expired-ticket",
        contract_sha=contract_sha,
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert decision.contract_sha == contract_sha
    assert not ticket.exists()
    assert _ledger_entries(tmp_path)[-1]["job_id"] == "job-expired-ticket"


def test_register_with_contract_sha_allows_ledger_fallback_when_ticket_absent(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "ticket absent uses ledger fallback")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))
    contract_sha = _sha256(contract)
    ticket = tmp_path / "dispatch-tickets" / f"codex-{contract_sha[:12]}.json"
    ticket.unlink()

    decision = gate.register_job(
        "job-ledger-fallback",
        lambda job_id: job_id == "job-ledger-fallback",
        contract_sha=contract_sha[:12],
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert decision.contract_sha == contract_sha
    assert "ticket_absent" in decision.message
    assert _ledger_entries(tmp_path)[-1]["job_id"] == "job-ledger-fallback"


def test_register_with_contract_sha_denies_when_ticket_and_ledger_are_absent(
    tmp_path: Path,
) -> None:
    gate = _gate(tmp_path, now=1_000)

    decision = gate.register_job(
        "job-no-evidence",
        lambda job_id: job_id == "job-no-evidence",
        contract_sha="a" * 12,
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.NO_MATCHING_TICKET
    assert decision.message == "candidate_contract_shas=<none>"


def test_register_runtime_filter_limits_ticket_candidates(tmp_path: Path) -> None:
    codex_contract = _contract(tmp_path, "codex ticket")
    cursor_contract = _contract(tmp_path, "cursor ticket")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        DispatchRequest("codex", codex_contract, est_input_chars=10_000, n_agents=1)
    )
    gate.check(
        DispatchRequest("cursor", cursor_contract, est_input_chars=10_000, n_agents=1)
    )

    decision = gate.register_job(
        "job-cursor",
        lambda job_id: job_id == "job-cursor",
        runtime="cursor",
    )

    assert decision.allow is True
    assert decision.contract_sha == _sha256(cursor_contract)


def test_duplicate_check_refreshes_existing_dispatch_ticket(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "refresh duplicate ticket")
    now = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=now)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))
    now.value += 701

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    ticket = tmp_path / "dispatch-tickets" / f"codex-{_sha256(contract)[:12]}.json"
    payload = json.loads(ticket.read_text(encoding="utf-8"))
    assert decision.allow is False
    assert decision.reason == ReasonCode.DUPLICATE_CONTRACT
    assert payload["issued_ts"] == 1_701
    assert payload["count"] == 1


def test_register_uses_ticket_flock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _contract(tmp_path, "locked registration")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))
    calls: list[int] = []

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(fd: int, operation: int) -> None:
            calls.append(operation)

    monkeypatch.setattr(dispatch_gate, "fcntl", FakeFcntl)

    decision = gate.register_job("job-locked", lambda job_id: job_id == "job-locked")

    assert decision.allow is True
    assert calls == [FakeFcntl.LOCK_EX, FakeFcntl.LOCK_UN]


def test_register_denies_contract_sha_without_matching_pending_dispatch(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "pending dispatch")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job(
        "job-mismatch",
        lambda job_id: job_id == "job-mismatch",
        contract_sha="f" * 12,
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.NO_MATCHING_TICKET
    assert decision.message == "candidate_contract_shas=" + _sha256(contract)
    assert all("job_id" not in entry for entry in _ledger_entries(tmp_path))


def test_contract_lint_warns_for_mcp_without_trust_handling(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "Use the MCP tool mcp__review for this contract.")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert ReasonCode.MCP_TRUST_UNHANDLED in decision.warnings
    assert _ledger_entries(tmp_path)[-1]["warnings"] == ["MCP_TRUST_UNHANDLED"]


def test_contract_lint_accepts_mcp_with_trust_handling(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "Use MCP after the trust dialog is handled by the worker.",
    )
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.MCP_TRUST_UNHANDLED not in decision.warnings


def test_contract_lint_accepts_mcp_with_korean_trust_handling(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "MCP 도구를 쓴다. 신뢰 다이얼로그는 워커가 처리한다.",
    )
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.MCP_TRUST_UNHANDLED not in decision.warnings


def test_contract_lint_warns_for_path_outside_known_roots(
    tmp_path: Path,
) -> None:
    known_roots = tmp_path / "known-roots.json"
    known_roots.write_text(
        json.dumps(["/Users/dev/workspace/example-product"]),
        encoding="utf-8",
    )
    contract = _contract(
        tmp_path,
        "Inspect /Users/dev/projects/mogui-ADE-orchestrator/src.",
    )
    gate = _gate(tmp_path, now=1_000, known_roots_path=known_roots)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.PATH_OUTSIDE_KNOWN_ROOTS in decision.warnings


def test_contract_lint_accepts_paths_inside_known_roots(
    tmp_path: Path,
) -> None:
    known_roots = tmp_path / "known-roots.json"
    known_roots.write_text(
        json.dumps(["/Users/dev/workspace/example-product"]),
        encoding="utf-8",
    )
    contract = _contract(
        tmp_path,
        "Inspect /Users/dev/workspace/example-product/example-ops.",
    )
    gate = _gate(tmp_path, now=1_000, known_roots_path=known_roots)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.PATH_OUTSIDE_KNOWN_ROOTS not in decision.warnings


def test_contract_lint_skips_path_check_without_known_roots(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "Inspect /Users/dev/projects/mogui-ADE-orchestrator/src.",
    )
    gate = _gate(tmp_path, now=1_000, known_roots_path=tmp_path / "missing.json")

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.PATH_OUTSIDE_KNOWN_ROOTS not in decision.warnings


def test_contract_lint_warns_for_worktree_as_repo_root(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "repo_root=/Users/dev/workspace/example-product/.orca/worktrees/unit-a",
    )
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.WORKTREE_AS_REPO_ROOT in decision.warnings


def test_contract_lint_accepts_worktree_path_without_repo_root_context(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "workspace=/Users/dev/workspace/example-product/.orca/worktrees/unit-a",
    )
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert ReasonCode.WORKTREE_AS_REPO_ROOT not in decision.warnings


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
    home = tmp_path / "cli-home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    orca = tmp_path / "orca"
    orca.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"ok":true,"result":{"dispatch":{"id":"d1"}}}\'\n',
        encoding="utf-8",
    )
    orca.chmod(0o755)
    env["ORCA_CLI_COMMAND"] = str(orca)

    check_result = subprocess.run(
        [
            str(_script()),
            "--ledger",
            str(ledger),
            "check",
            "--runtime",
            "codex",
            "--model",
            "gpt-5.6-luna",
            "--contract",
            str(contract),
            "--agents",
            "1",
            "--est-chars",
            "1000",
            "--completion-channel",
            "sentinel-log",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
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
            "--orchestration-task",
            "task-cli",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
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
        env=env,
    )

    assert check_result.returncode == 0, check_result.stderr
    assert register_result.returncode == 0, register_result.stderr
    assert watch_result.returncode == 0, watch_result.stderr


def test_cli_check_creates_default_ticket_directory(tmp_path: Path) -> None:
    contract = _dispatch_contract(tmp_path, runtime="codex")
    ledger = tmp_path / "cli-ledger.jsonl"
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [
            str(_script()),
            "--ledger",
            str(ledger),
            "check",
            "--runtime",
            "codex",
            "--model",
            "gpt-5.6-luna",
            "--contract",
            str(contract),
            "--agents",
            "2",
            "--est-chars",
            "24000",
            "--completion-channel",
            "sentinel-log",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    contract_sha = _sha256(contract)
    ticket_dir = home / ".mogui" / "dispatch-tickets"
    ticket = ticket_dir / f"codex-{contract_sha[:12]}.json"

    assert result.returncode == 0, result.stderr
    assert ticket_dir.is_dir()
    payload = json.loads(ticket.read_text(encoding="utf-8"))
    assert payload["runtime"] == "codex"
    assert payload["contract_sha"] == contract_sha
    assert payload["count"] == 2
    assert isinstance(payload["issued_ts"], (int, float))


def test_cli_register_ambiguous_prints_candidate_shas(tmp_path: Path) -> None:
    first_contract = _contract(tmp_path, "first cli candidate")
    second_contract = _contract(tmp_path, "second cli candidate")
    ledger = tmp_path / "cli-ledger.jsonl"
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    orca = tmp_path / "orca"
    orca.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"ok":true,"result":{"dispatch":{"id":"d1"}}}\'\n',
        encoding="utf-8",
    )
    orca.chmod(0o755)
    env["ORCA_CLI_COMMAND"] = str(orca)

    for contract in (first_contract, second_contract):
        result = subprocess.run(
            [
                str(_script()),
                "--ledger",
                str(ledger),
                "check",
                "--runtime",
                "codex",
                "--model",
                "gpt-5.6-luna",
                "--contract",
                str(contract),
                "--agents",
                "1",
                "--est-chars",
                "1000",
                "--completion-channel",
                "sentinel-log",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr

    register_result = subprocess.run(
        [
            str(_script()),
            "--ledger",
            str(ledger),
            "register",
            "--job-id",
            "job-cli-ambiguous",
            "--probe-cmd",
            "printf job-cli-ambiguous",
            "--orchestration-task",
            "task-cli-ambiguous",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert register_result.returncode == 2
    assert "AMBIGUOUS_TICKET: candidate_contract_shas=" in register_result.stderr
    assert _sha256(first_contract) in register_result.stderr
    assert _sha256(second_contract) in register_result.stderr


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
    known_roots_path: Path | None = None,
) -> DispatchGate:
    return DispatchGate(
        DispatchGateConfig(
            ledger_path=tmp_path / "ledger.jsonl",
            ticket_dir=tmp_path / "dispatch-tickets",
            known_roots_path=known_roots_path or tmp_path / "missing-known-roots.json",
        ),
        clock=clock or (lambda: now if now is not None else 1_000),
    )


def _contract(tmp_path: Path, content: str) -> Path:
    contract = tmp_path / f"{abs(hash(content))}.md"
    contract.write_text(content, encoding="utf-8")
    return contract


def _dispatch_contract(tmp_path: Path, runtime: str) -> Path:
    payload = {
        "job_id": "u5-ticket-impl-mogui-20260723",
        "runtime": runtime,
        "workspace": "/Users/dev/workspace/example-product",
        "repo": "/Users/dev/projects/mogui-ADE-orchestrator",
        "objective": "Implement U5 dispatch gate ticket issuance",
        "scope": {
            "include": [
                "src/master_runtime/core/dispatch_gate.py",
                "scripts/dispatch-gate",
            ],
            "exclude": [
                "example-ops dispatch-gate-warn.sh consumption",
                "git commit",
                "git push",
            ],
        },
        "acceptance": [
            "ALLOW check writes a dispatch ticket",
            "DENY check does not write a dispatch ticket",
            "ticket directory is created automatically",
        ],
    }
    contract = tmp_path / "u5-ticket-impl-mogui-20260723.contract.json"
    contract.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return contract


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger_entries(tmp_path: Path) -> list[dict[str, object]]:
    ledger = tmp_path / "ledger.jsonl"
    return [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "dispatch-gate"
