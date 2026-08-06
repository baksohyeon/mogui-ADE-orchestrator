from __future__ import annotations

from windows_exec_surface import skip_windows_exec_surface
import hashlib
import json
import os
import runpy
import subprocess
import threading
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


def test_dispatch_gate_config_preserves_old_positional_arity(tmp_path: Path) -> None:
    config = DispatchGateConfig(
        tmp_path / "ledger.jsonl",
        tmp_path / "tickets",
        tmp_path / "known-roots.json",
        101,
        202,
        303,
        frozenset({"premium"}),
        404,
        505,
    )

    assert config.single_dispatch_char_limit == 101
    assert config.batch_dispatch_char_limit == 202
    assert config.duplicate_window_seconds == 303
    assert config.high_cost_runtimes == frozenset({"premium"})
    assert config.ticket_ttl_seconds == 404
    assert config.expired_ticket_gc_grace_seconds == 505
    assert config.tier_policy_path == dispatch_gate._default_tier_policy_path()


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
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["model"] == "gpt-5.6-luna"
    assert entry["cost_proxy"] == 10_000


def test_tier_policy_allows_worker_model(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "allowed tier model")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK


def test_check_can_evaluate_without_recording(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "dry-run allowed tier model")
    dry_run_contract = _contract(tmp_path, "dry-run separate contract")
    gate = _gate(tmp_path, now=1_000)

    recorded = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )
    before = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")

    dry_run = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=dry_run_contract,
            est_input_chars=10_000,
            n_agents=1,
        ),
        record=False,
    )

    assert recorded.allow is True
    assert dry_run.allow is True
    assert (tmp_path / "ledger.jsonl").read_text(encoding="utf-8") == before
    dry_run_ticket = (
        tmp_path
        / "dispatch-tickets"
        / f"codex-{_sha256(dry_run_contract)[:12]}.json"
    )
    assert not dry_run_ticket.exists()


def test_tier_policy_denies_top_tier_and_ledgers_model(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "denied tier model")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-sol",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    entry = _ledger_entries(tmp_path)[-1]
    assert decision.allow is False
    assert decision.reason == ReasonCode.TIER_POLICY
    assert entry["reason"] == "TIER_POLICY"
    assert entry["model"] == "gpt-5.6-sol"


def test_tier_override_allows_top_tier_and_ledgers_reason(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "overridden tier model")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-sol",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            tier_override="owner approved incident response",
        )
    )

    entry = _ledger_entries(tmp_path)[-1]
    assert decision.allow is True
    assert decision.tier_override == "owner approved incident response"
    assert entry["model"] == "gpt-5.6-sol"
    assert entry["tier_override"] == "owner approved incident response"


def test_empty_tier_override_is_invalid(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "empty tier override")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-sol",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            tier_override="   ",
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.INVALID_REQUEST


def test_missing_tier_policy_fails_closed(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "missing tier policy")
    gate = _gate(
        tmp_path,
        now=1_000,
        tier_policy_path=tmp_path / "missing-policy.json",
    )

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.TIER_POLICY_UNAVAILABLE
    assert _ledger_entries(tmp_path)[-1]["reason"] == "TIER_POLICY_UNAVAILABLE"


def test_default_tier_policy_env_overrides_paths(tmp_path: Path) -> None:
    override = tmp_path / "override-policy.json"
    override.write_text("{}", encoding="utf-8")
    assert (
        dispatch_gate._default_tier_policy_path(
            repo_root=tmp_path,
            environ={"DISPATCH_TIER_POLICY": str(override)},
        )
        == override
    )


def test_default_tier_policy_uses_template_when_instance_absent(tmp_path: Path) -> None:
    """Without DISPATCH_TIER_POLICY and without instance file → template path."""
    # Isolate under tmp_path so an onboarded checkout cannot poison the assertion.
    (tmp_path / "master-ops").mkdir()
    template = tmp_path / dispatch_gate.DEFAULT_TIER_POLICY_RELATIVE_PATH
    template.write_text("{}", encoding="utf-8")
    (tmp_path / "config").mkdir()
    assert (
        dispatch_gate._default_tier_policy_path(repo_root=tmp_path, environ={})
        == template
    )


def test_default_tier_policy_prefers_instance_when_present(tmp_path: Path) -> None:
    """When config/model-tier-policy.json exists, it is preferred over template."""
    (tmp_path / "master-ops").mkdir()
    (tmp_path / dispatch_gate.DEFAULT_TIER_POLICY_RELATIVE_PATH).write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "config").mkdir()
    instance = tmp_path / dispatch_gate.INSTANCE_TIER_POLICY_RELATIVE_PATH
    instance.write_text(
        json.dumps(
            {
                "version": 2,
                "tiers": {"top": [], "efficient": []},
                "fanout_caps": {"top": 1, "unknown": 1},
                "window_seconds": 86400,
            }
        ),
        encoding="utf-8",
    )
    assert (
        dispatch_gate._default_tier_policy_path(repo_root=tmp_path, environ={})
        == instance
    )


def test_instance_tier_policy_example_is_loadable_version_2() -> None:
    """The shipped example must parse as a version-2 policy the gate accepts."""
    example = (
        Path(dispatch_gate.__file__).resolve().parents[3]
        / "config"
        / "model-tier-policy.example.json"
    )
    policy = dispatch_gate._load_tier_policy(example)
    assert policy.version >= 2
    # Example ships no top cap. Top-tier approval is asked by master-ops/scripts/dispatch,
    # while the gate treats missing caps as uncapped for every tier.
    assert policy.cap_for("unknown") == 8
    assert policy.cap_for("top") is None


def test_unparseable_tier_policy_fails_closed(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "unparseable tier policy")
    policy = tmp_path / "broken-policy.json"
    policy.write_text("not-json\n", encoding="utf-8")
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.TIER_POLICY_UNAVAILABLE


def test_noncanonical_denied_tier_never_fails_open(tmp_path: Path) -> None:
    for unknown_model in ("deny", "warn"):
        case_dir = tmp_path / unknown_model
        case_dir.mkdir()
        contract = _contract(case_dir, f"noncanonical denied tier {unknown_model}")
        policy = case_dir / "model-tier-policy.json"
        policy.write_text(
            json.dumps(
                {
                    "version": 1,
                    "worker_allowed": [],
                    "worker_denied_tiers": ["gpt-5.6-sol "],
                    "unknown_model": unknown_model,
                }
            ),
            encoding="utf-8",
        )
        gate = _gate(case_dir, now=1_000, tier_policy_path=policy)

        decision = gate.check(
            DispatchRequest(
                runtime="codex",
                model="gpt-5.6-sol",
                contract_path=contract,
                est_input_chars=10_000,
                n_agents=1,
            )
        )

        assert decision.allow is False
        assert decision.reason == ReasonCode.TIER_POLICY_UNAVAILABLE
        assert _ledger_entries(case_dir)[-1]["reason"] == "TIER_POLICY_UNAVAILABLE"
        assert not (case_dir / "dispatch-tickets").exists()


def test_noncanonical_requested_model_is_invalid_request(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "noncanonical requested model")
    gate = _gate(
        tmp_path,
        now=1_000,
        tier_policy_path=_tier_policy(tmp_path, unknown_model="warn"),
    )

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-sol ",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.INVALID_REQUEST
    assert _ledger_entries(tmp_path)[-1]["reason"] == "INVALID_REQUEST"
    assert not (tmp_path / "dispatch-tickets").exists()


def test_unknown_model_follows_policy_setting(tmp_path: Path) -> None:
    deny_dir = tmp_path / "deny"
    deny_dir.mkdir()
    deny_contract = _contract(deny_dir, "unknown model denied")
    deny_gate = _gate(
        deny_dir,
        now=1_000,
        tier_policy_path=_tier_policy(deny_dir, unknown_model="deny"),
    )
    deny_decision = deny_gate.check(
        DispatchRequest(
            runtime="codex",
            model="future-model",
            contract_path=deny_contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    warn_dir = tmp_path / "warn"
    warn_dir.mkdir()
    warn_contract = _contract(warn_dir, "unknown model warned")
    warn_gate = _gate(
        warn_dir,
        now=1_000,
        tier_policy_path=_tier_policy(warn_dir, unknown_model="warn"),
    )
    warn_decision = warn_gate.check(
        DispatchRequest(
            runtime="codex",
            model="future-model",
            contract_path=warn_contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert deny_decision.allow is False
    assert deny_decision.reason == ReasonCode.TIER_POLICY
    assert warn_decision.allow is True
    assert warn_decision.warnings == (ReasonCode.TIER_POLICY,)


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
    assert _ledger_entries(tmp_path)[-1]["cost_proxy"] == 1_200_000


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


def test_r3_allows_same_contract_twice_with_hash_attempt_lineage(
    tmp_path: Path,
) -> None:
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
    assert second.allow is True
    assert second.reason == ReasonCode.OK
    entries = _ledger_entries(tmp_path)
    assert [entry["attempt"] for entry in entries] == [1, 2]
    assert {entry["contract_sha"] for entry in entries} == {_sha256(contract)}


def test_r3_check_does_not_change_subsequent_dispatch_outcome(
    tmp_path: Path,
) -> None:
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
    assert second.reason == ReasonCode.OK


def test_r4_registers_verified_job_id(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "verified job")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job("job-123", lambda job_id: job_id == "job-123")

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert _ledger_entries(tmp_path)[-1]["job_id"] == "job-123"
    assert _ledger_entries(tmp_path)[-1]["completion_channel"] == "sentinel-log"
    assert _ledger_entries(tmp_path)[-1]["attempt"] == 2


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


def test_cli_register_requires_orchestration_task(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract = _contract(tmp_path, "orchestration task required")
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

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
    ledger_entry = _ledger_entries(tmp_path)[-1]
    assert ledger_entry["reason"] == "ORCHESTRATION_UNVERIFIED"
    assert ledger_entry["probe_failure"] == "task_omitted"


@skip_windows_exec_surface
def test_cli_register_allows_sentinel_log_without_orchestration_task(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract = _contract(tmp_path, "sentinel log registration")
    ledger = tmp_path / "ledger.jsonl"
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORCA_CLI_COMMAND", str(tmp_path / "missing-orca"))

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
                "sentinel-log",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-sentinel",
                "--probe-cmd",
                "printf job-sentinel",
            ]
        )
        == 0
    )
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["job_id"] == "job-sentinel"
    assert entry["completion_channel"] == "sentinel-log"
    assert "orchestration_task" not in entry


@skip_windows_exec_surface
def test_cli_register_rechecks_expected_completion_channel_under_register_lock(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract = _contract(tmp_path, "stale sentinel channel decision")
    ledger = tmp_path / "ledger.jsonl"
    home = tmp_path / "home"
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ORCA_CLI_COMMAND", str(tmp_path / "missing-orca"))

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

    contract_sha = _sha256(contract)
    ticket = home / ".mogui" / "dispatch-tickets" / f"codex-{contract_sha[:12]}.json"
    assert ticket.exists()

    def stale_channel(self, contract_sha=None, runtime=None):
        return "sentinel-log"

    monkeypatch.setattr(
        script["DispatchGate"],
        "completion_channel_for_registration",
        stale_channel,
    )

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-channel-race",
                "--probe-cmd",
                "printf job-channel-race",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"INVALID_REQUEST"' in output.out
    assert "expected_completion_channel=sentinel-log" in output.err
    assert "actual_completion_channel=orchestration" in output.err
    entries = _ledger_entries(tmp_path)
    assert len(entries) == 1
    assert not any(
        entry.get("job_id") == "job-channel-race"
        and entry.get("decision") == "ALLOW"
        for entry in entries
    )
    assert ticket.exists()


@skip_windows_exec_surface
def test_cli_register_sentinel_log_denies_failing_probe(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract = _contract(tmp_path, "sentinel log failing probe")
    ledger = tmp_path / "ledger.jsonl"
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORCA_CLI_COMMAND", str(tmp_path / "missing-orca"))

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
                "sentinel-log",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-sentinel-missing",
                "--probe-cmd",
                "printf different-job",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"UNVERIFIED_JOB"' in output.out
    assert "UNVERIFIED_JOB" in output.err
    assert all(
        entry.get("job_id") != "job-sentinel-missing"
        for entry in _ledger_entries(tmp_path)
    )


@skip_windows_exec_surface
def test_cli_register_without_matching_ticket_keeps_no_matching_ticket_denial(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    orca = tmp_path / "orca"
    orca.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"ok":true,"result":{"dispatch":{"id":"d1"}}}\'\n',
        encoding="utf-8",
    )
    orca.chmod(0o755)
    monkeypatch.setenv("ORCA_CLI_COMMAND", str(orca))

    assert (
        script["main"](
            [
                "--ledger",
                str(ledger),
                "register",
                "--job-id",
                "job-missing-ticket",
                "--probe-cmd",
                "printf job-missing-ticket",
                "--orchestration-task",
                "task-missing-ticket",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert '"reason":"NO_MATCHING_TICKET"' in output.out
    assert "NO_MATCHING_TICKET: candidate_contract_shas=<none>" in output.err


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


def test_register_with_expected_completion_channel_matches(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "expected sentinel channel")
    gate = _gate(tmp_path, now=1_000)
    gate.check(DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1))

    decision = gate.register_job(
        "job-expected-channel",
        lambda job_id: job_id == "job-expected-channel",
        expected_completion_channel="sentinel-log",
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["job_id"] == "job-expected-channel"
    assert entry["completion_channel"] == "sentinel-log"


def test_register_expected_completion_channel_mismatch_denies_before_write(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "expected channel mismatch")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="orchestration",
            model="gpt-5.6-luna",
        )
    )
    ticket = tmp_path / "dispatch-tickets" / f"codex-{_sha256(contract)[:12]}.json"
    assert ticket.exists()

    decision = gate.register_job(
        "job-channel-mismatch",
        lambda job_id: job_id == "job-channel-mismatch",
        expected_completion_channel="sentinel-log",
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.INVALID_REQUEST
    assert "expected_completion_channel=sentinel-log" in decision.message
    assert "actual_completion_channel=orchestration" in decision.message
    entries = _ledger_entries(tmp_path)
    assert len(entries) == 1
    assert all(entry.get("job_id") != "job-channel-mismatch" for entry in entries)
    assert ticket.exists()


def test_register_without_expected_completion_channel_keeps_current_behavior(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "omitted expected channel")
    gate = _gate(tmp_path, now=1_000)
    gate.check(
        _DispatchRequest(
            runtime="codex",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
            completion_channel="orchestration",
            model="gpt-5.6-luna",
        )
    )

    decision = gate.register_job(
        "job-no-expected-channel",
        lambda job_id: job_id == "job-no-expected-channel",
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["job_id"] == "job-no-expected-channel"
    assert entry["completion_channel"] == "orchestration"


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


def test_repeated_check_writes_next_attempt_and_dispatch_ticket(
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
    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert _ledger_entries(tmp_path)[-1]["attempt"] == 2
    assert payload["issued_ts"] == 1_701
    assert payload["count"] == 1


def test_concurrent_repeated_checks_receive_distinct_attempts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _contract(tmp_path, "concurrent same contract")
    gate = _gate(tmp_path, now=1_000)
    first_in_append = threading.Event()
    release_first = threading.Event()
    append_calls = 0
    real_append_entry = gate._append_entry

    def delayed_first_append(entry):
        nonlocal append_calls
        append_calls += 1
        if append_calls == 1:
            first_in_append.set()
            assert release_first.wait(timeout=2)
        real_append_entry(entry)

    monkeypatch.setattr(gate, "_append_entry", delayed_first_append)
    decisions: list[GateDecision] = []

    def check_contract() -> None:
        decisions.append(
            gate.check(
                DispatchRequest(
                    "codex",
                    contract,
                    est_input_chars=10_000,
                    n_agents=1,
                )
            )
        )

    first_thread = threading.Thread(target=check_contract)
    first_thread.start()
    assert first_in_append.wait(timeout=2)
    second_thread = threading.Thread(target=check_contract)
    second_thread.start()
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert len(decisions) == 2
    assert all(decision.reason == ReasonCode.OK for decision in decisions)
    assert sorted(entry["attempt"] for entry in _ledger_entries(tmp_path)) == [1, 2]


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


@skip_windows_exec_surface
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


@skip_windows_exec_surface
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


def test_cli_report_rolls_up_models_denials_and_overrides(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "report-ledger.jsonl"
    policy = _tier_policy(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    cases = (
        ("gpt-5.6-luna", "allowed report model", 2, None, 0),
        ("gpt-5.6-sol", "denied report model", 1, None, 2),
        (
            "gpt-5.6-sol",
            "overridden report model",
            3,
            "owner approved benchmark",
            0,
        ),
    )
    for model, content, agents, override, expected_status in cases:
        command = [
            "--ledger",
            str(ledger),
            "check",
            "--runtime",
            "codex",
            "--model",
            model,
            "--tier-policy",
            str(policy),
            "--contract",
            str(_contract(tmp_path, content)),
            "--agents",
            str(agents),
            "--est-chars",
            "1000",
            "--completion-channel",
            "orchestration",
        ]
        if override is not None:
            command.extend(("--tier-override", override))
        assert script["main"](command) == expected_status
        capsys.readouterr()

    assert script["main"](["--ledger", str(ledger), "report"]) == 0
    output = capsys.readouterr().out
    assert "Dispatch gate report" in output
    assert "gpt-5.6-luna: dispatches=1 est_cost_proxy=2000" in output
    assert "gpt-5.6-sol: dispatches=1 est_cost_proxy=3000" in output
    assert "TIER_POLICY: 1" in output
    assert (
        'gpt-5.6-sol: reason="owner approved benchmark" count=1' in output
    )


def test_cli_report_shows_every_policy_a_day_was_judged_against(
    tmp_path: Path,
    capsys,
) -> None:
    """Two rows here mean the day was not judged against one policy."""

    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "policy-report-ledger.jsonl"
    rows = (
        {"tier_policy_path": "/policies/installation.json", "tier_policy_sha256": "a" * 64},
        {"tier_policy_path": "/policies/installation.json", "tier_policy_sha256": "a" * 64},
        {"tier_policy_path": "/tmp/substituted.json", "tier_policy_sha256": "b" * 64},
        {"tier_policy_path": "/policies/legacy-entry.json"},
    )
    with ledger.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            entry = {
                "ts": 1_785_000_000 + index,
                "decision": "ALLOW",
                "reason": "OK",
                "model": "gpt-5.6-luna",
                "cost_proxy": 10,
                **row,
            }
            handle.write(json.dumps(entry) + "\n")

    assert script["main"](["--ledger", str(ledger), "report"]) == 0
    output = capsys.readouterr().out
    assert f"/policies/installation.json: sha256={'a' * 12} decisions=2" in output
    assert f"/tmp/substituted.json: sha256={'b' * 12} decisions=1" in output
    assert "/policies/legacy-entry.json: sha256=<unrecorded> decisions=1" in output


def test_cli_report_uses_stored_cost_and_labels_legacy_computation(
    tmp_path: Path,
    capsys,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "report-ledger.jsonl"
    entries = (
        {
            "ts": 1_000,
            "decision": "ALLOW",
            "model": "stored-model",
            "cost_proxy": 7,
            "est_chars": 999,
            "n_agents": 999,
        },
        {
            "ts": 2_000,
            "decision": "ALLOW",
            "model": "legacy-model",
            "est_chars": 20,
            "n_agents": 3,
        },
    )
    ledger.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )

    assert script["main"](["--ledger", str(ledger), "report"]) == 0
    output = capsys.readouterr().out

    assert "stored-model: dispatches=1 est_cost_proxy=7" in output
    assert "legacy-model: dispatches=1 est_cost_proxy=60" in output
    assert "legacy-model: dispatches=1 est_cost_proxy=60 computed_legacy_entries=1" in output


def test_cli_report_skips_non_object_and_invalid_timestamps(
    tmp_path: Path,
    capsys,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    ledger = tmp_path / "damaged-ledger.jsonl"
    ledger.write_text(
        "[]\n"
        '{"ts":1e309,"decision":"DENY","reason":"BAD_TS"}\n'
        f'{{"ts":{10**400},"decision":"ALLOW","model":"damaged-model",'
        '"cost_proxy":12}\n'
        '{"ts":0,"decision":"ALLOW","model":"healthy-model","cost_proxy":3}\n',
        encoding="utf-8",
    )

    assert script["main"](["--ledger", str(ledger), "report"]) == 0
    output = capsys.readouterr().out

    assert "Skipped malformed: 1" in output
    assert "Time span: 1970-01-01T00:00:00Z to 1970-01-01T00:00:00Z" in output
    assert "BAD_TS: 1" in output
    assert "damaged-model: dispatches=1 est_cost_proxy=12" in output
    assert "healthy-model: dispatches=1 est_cost_proxy=3" in output


@skip_windows_exec_surface
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


@skip_windows_exec_surface
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


def test_incident_b_repeated_contract_records_lineage_attempts(
    tmp_path: Path,
) -> None:
    # Scenario B replacement: repeated contracts are lineage, not denial.
    contract = _contract(tmp_path, "duplicate contract")
    gate = _gate(tmp_path, now=1_000)

    first = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )
    second = gate.check(
        DispatchRequest("codex", contract, est_input_chars=10_000, n_agents=1)
    )

    assert first.allow is True
    assert second.allow is True
    assert second.reason == ReasonCode.OK
    assert [entry["attempt"] for entry in _ledger_entries(tmp_path)] == [1, 2]


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


def test_case_variant_of_denied_tier_is_denied_under_warn(tmp_path: Path) -> None:
    """Exact-string membership let a case variant reach the unknown branch."""

    contract = _contract(tmp_path, "case variant of a denied tier")
    gate = _gate(
        tmp_path,
        now=1_000,
        tier_policy_path=_tier_policy(tmp_path, unknown_model="warn"),
    )

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="GPT-5.6-SOL",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.TIER_POLICY
    assert _ledger_entries(tmp_path)[-1]["model"] == "GPT-5.6-SOL"
    assert not (tmp_path / "dispatch-tickets").exists()


def test_case_variant_of_allowed_model_stays_allowed(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "case variant of an allowed model")
    gate = _gate(tmp_path, now=1_000)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="GPT-5.6-Luna",
            contract_path=contract,
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK


def test_ledger_records_which_tier_policy_decided(tmp_path: Path) -> None:
    """The policy path is caller-supplied, so the decision must name the file."""

    policy = _tier_policy(tmp_path)
    digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    allowed = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=_contract(tmp_path, "policy identity on allow"),
            est_input_chars=10_000,
            n_agents=1,
        )
    )
    denied = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-sol",
            contract_path=_contract(tmp_path, "policy identity on deny"),
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert allowed.allow is True
    assert denied.allow is False
    entries = _ledger_entries(tmp_path)[-2:]
    assert [entry["tier_policy_path"] for entry in entries] == [str(policy)] * 2
    assert [entry["tier_policy_sha256"] for entry in entries] == [digest] * 2


def test_tier_policy_rejects_case_differing_duplicate_across_sets(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "model-tier-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "worker_allowed": ["gpt-5.6-luna"],
                "worker_denied_tiers": ["GPT-5.6-LUNA"],
                "unknown_model": "deny",
            }
        ),
        encoding="utf-8",
    )
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-5.6-luna",
            contract_path=_contract(tmp_path, "overlapping policy sets"),
            est_input_chars=10_000,
            n_agents=1,
        )
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.TIER_POLICY_UNAVAILABLE


def test_v2_cap_counts_a_window_not_a_single_fanout(tmp_path: Path) -> None:
    """Ten sequential single-agent dispatches cost what one fan-out of ten costs.

    The incident behind this policy was a top tier multiplied by ten workers.
    Capping concurrency alone would leave the same spend reachable one dispatch
    at a time, so the cap counts agents inside a window.
    """

    policy = _tier_policy_v2(tmp_path)
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    first = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "first top dispatch"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )
    second = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "second top dispatch"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )

    assert first.allow is True
    assert second.allow is False
    assert second.reason == ReasonCode.TIER_FANOUT_CAP
    assert "used=1 cap=1" in second.message
    assert _ledger_entries(tmp_path)[0]["tier"] == "top"


def test_v2_override_passes_the_cap_and_still_consumes_it(tmp_path: Path) -> None:
    """An override bypasses the block for one request; it does not refund cost."""

    policy = _tier_policy_v2(tmp_path)
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    for index in range(2):
        decision = gate.check(
            DispatchRequest(
                runtime="codex",
                model="claude-opus-5",
                contract_path=_contract(tmp_path, f"override dispatch {index}"),
                est_input_chars=1_000,
                n_agents=1,
                tier_override="owner approved benchmark",
            )
        )
        assert decision.allow is True

    blocked = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "third top dispatch"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )
    assert blocked.allow is False
    assert "used=2" in blocked.message


def test_v2_unknown_model_is_capped_not_denied(tmp_path: Path) -> None:
    """A model the policy has never heard of is usable once, and never silently."""

    policy = _tier_policy_v2(tmp_path)
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    allowed = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-6-released-yesterday",
            contract_path=_contract(tmp_path, "unknown model once"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )

    assert allowed.allow is True
    assert ReasonCode.TIER_UNKNOWN_MODEL in allowed.warnings
    assert ReasonCode.TIER_POLICY not in allowed.warnings
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["tier"] == "unknown"
    assert entry["warnings"] == ["TIER_UNKNOWN_MODEL"]

    denied = gate.check(
        DispatchRequest(
            runtime="codex",
            model="gpt-6-released-yesterday",
            contract_path=_contract(tmp_path, "unknown model twice"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )
    assert denied.allow is False
    assert denied.reason == ReasonCode.TIER_FANOUT_CAP


def test_v2_uncapped_tier_allows_a_large_fanout(tmp_path: Path) -> None:
    """A tier with no cap is uncapped: the guard is tier times fan-out, not size."""

    policy = _tier_policy_v2(tmp_path)
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    decision = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-haiku-4-5",
            contract_path=_contract(tmp_path, "efficient fanout"),
            est_input_chars=1_000,
            n_agents=10,
        )
    )

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK


def test_v2_window_expiry_releases_the_cap(tmp_path: Path) -> None:
    policy = _tier_policy_v2(tmp_path, window_seconds=100)
    clock = _MutableClock(1_000)
    gate = _gate(tmp_path, clock=clock, tier_policy_path=policy)

    assert gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "before the window closes"),
            est_input_chars=1_000,
            n_agents=1,
        )
    ).allow is True

    clock.value = 1_000 + 101
    assert gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "after the window closes"),
            est_input_chars=1_000,
            n_agents=1,
        )
    ).allow is True


def test_v2_policy_validation_fails_closed(tmp_path: Path) -> None:
    """Every malformed v2 shape denies rather than falling back to a default."""

    bad_payloads = (
        {"version": 2, "tiers": {}, "fanout_caps": {"unknown": 1}},
        {
            "version": 2,
            "tiers": {"top": ["a"], "other": ["a"]},
            "fanout_caps": {"unknown": 1},
        },
        {
            "version": 2,
            "tiers": {"unknown": ["a"]},
            "fanout_caps": {"unknown": 1},
        },
        {
            "version": 2,
            "tiers": {"top": ["a"]},
            "fanout_caps": {"top": -1, "unknown": 1},
        },
        {
            "version": 2,
            "tiers": {"top": ["a"]},
            "fanout_caps": {"nosuchtier": 1, "unknown": 1},
        },
        {
            "version": 2,
            "tiers": {"top": ["a"]},
            "fanout_caps": {"unknown": 1},
            "window_seconds": 0,
        },
    )
    for index, payload in enumerate(bad_payloads):
        case_dir = tmp_path / f"bad{index}"
        case_dir.mkdir()
        policy = case_dir / "model-tier-policy.json"
        policy.write_text(json.dumps(payload), encoding="utf-8")
        gate = _gate(case_dir, now=1_000, tier_policy_path=policy)

        decision = gate.check(
            DispatchRequest(
                runtime="codex",
                model="claude-haiku-4-5",
                contract_path=_contract(case_dir, f"bad policy {index}"),
                est_input_chars=1_000,
                n_agents=1,
            )
        )
        assert decision.allow is False, payload
        assert decision.reason == ReasonCode.TIER_POLICY_UNAVAILABLE, payload


def test_v2_missing_unknown_cap_is_uncapped_like_any_tier(tmp_path: Path) -> None:
    """Absence of fanout_caps.unknown is uncapped, same as any other missing key.

    Measured asymmetry before the fix: cap_for returned None for a missing
    efficient entry (uncapped), but the loader rejected a policy that omitted
    unknown, so instance revisions could not drop the key and had to invent a
    placeholder value.
    """

    policy = tmp_path / "model-tier-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 2,
                "tiers": {
                    "top": ["claude-opus-5"],
                    "efficient": ["claude-haiku-4-5"],
                },
                "fanout_caps": {"top": 1},
                "window_seconds": 86_400,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    for index in range(3):
        decision = gate.check(
            DispatchRequest(
                runtime="codex",
                model="gpt-6-released-yesterday",
                contract_path=_contract(tmp_path, f"unlisted fanout {index}"),
                est_input_chars=1_000,
                n_agents=1,
            )
        )
        assert decision.allow is True, decision
        assert ReasonCode.TIER_UNKNOWN_MODEL in decision.warnings
        assert _ledger_entries(tmp_path)[-1]["tier"] == "unknown"


def test_v2_tier_resolution_listed_top_efficient_unlisted_and_sonnet5(
    tmp_path: Path,
) -> None:
    """Tier resolution: listed top, listed efficient, unlisted, no-cap tier.

    Pins claude-sonnet-5 by name — the measured regression where an unlisted
    mid-tier id resolved to unknown with the same cap as top and was refused
    with TIER_FANOUT_CAP exactly like claude-opus-5.
    """

    policy = tmp_path / "model-tier-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 2,
                "tiers": {
                    "top": ["claude-opus-5"],
                    "efficient": ["claude-haiku-4-5", "claude-sonnet-5"],
                },
                "fanout_caps": {"top": 1},
                "window_seconds": 86_400,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)

    top = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "listed top id"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )
    assert top.allow is True
    assert _ledger_entries(tmp_path)[-1]["tier"] == "top"

    top_capped = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-opus-5",
            contract_path=_contract(tmp_path, "listed top id again"),
            est_input_chars=1_000,
            n_agents=1,
        )
    )
    assert top_capped.allow is False
    assert top_capped.reason == ReasonCode.TIER_FANOUT_CAP

    efficient = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-haiku-4-5",
            contract_path=_contract(tmp_path, "listed efficient id"),
            est_input_chars=1_000,
            n_agents=10,
        )
    )
    assert efficient.allow is True
    assert _ledger_entries(tmp_path)[-1]["tier"] == "efficient"

    # Measured regression pin: claude-sonnet-5 must resolve as listed efficient,
    # not unknown, and must not inherit the top fan-out cap.
    sonnet = gate.check(
        DispatchRequest(
            runtime="codex",
            model="claude-sonnet-5",
            contract_path=_contract(tmp_path, "claude-sonnet-5 regression pin"),
            est_input_chars=1_000,
            n_agents=5,
        )
    )
    assert sonnet.allow is True
    assert sonnet.reason == ReasonCode.OK
    assert ReasonCode.TIER_UNKNOWN_MODEL not in sonnet.warnings
    sonnet_entry = _ledger_entries(tmp_path)[-1]
    assert sonnet_entry["tier"] == "efficient"
    assert sonnet_entry["model"] == "claude-sonnet-5"

    unlisted = gate.check(
        DispatchRequest(
            runtime="codex",
            model="brand-new-model-id",
            contract_path=_contract(tmp_path, "unlisted model id"),
            est_input_chars=1_000,
            n_agents=5,
        )
    )
    assert unlisted.allow is True
    assert ReasonCode.TIER_UNKNOWN_MODEL in unlisted.warnings
    assert _ledger_entries(tmp_path)[-1]["tier"] == "unknown"


def test_template_policy_resolves_claude_sonnet_5_as_efficient() -> None:
    """Shipped template lists claude-sonnet-5 under efficient (measured fix)."""

    from master_runtime.core.dispatch_gate import _load_tier_policy

    repo_root = Path(__file__).resolve().parents[1]
    template = repo_root / "master-ops" / "model-tier-policy.json"
    policy = _load_tier_policy(template)

    assert policy.version == 2
    assert policy.tier_of("claude-sonnet-5") == "efficient"
    assert policy.tier_of("claude-opus-5") == "top"
    assert policy.tier_of("claude-haiku-4-5") == "efficient"
    assert policy.tier_of("grok-4.5-fast") == "efficient"
    assert policy.tier_of("never-listed-anywhere") == "unknown"
    assert policy.cap_for("top") is None
    assert policy.cap_for("unknown") == 8
    assert policy.cap_for("efficient") is None


def _registered(
    tmp_path: Path,
    policy: Path,
    declared: str | None,
    measured: str | None,
    probe_failed: bool = False,
    dispatch_model: str = "gpt-5.6-luna",
    label: str = "job",
):
    """Issue a ticket with check, then register with a measured model."""

    gate = _gate(tmp_path, now=1_000, tier_policy_path=policy)
    gate.check(
        DispatchRequest(
            runtime="codex",
            model=dispatch_model,
            contract_path=_contract(tmp_path, f"{label} contract"),
            est_input_chars=10_000,
            n_agents=1,
        )
    )
    return gate.register_job(
        label,
        lambda job_id: job_id == label,
        declared_model=declared,
        measured_model=measured,
        model_probe_failed=probe_failed,
    )


def test_register_without_a_declared_model_warns_rather_than_denies(
    tmp_path: Path,
) -> None:
    """A runtime that cannot report its model must still be able to dispatch."""

    decision = _registered(tmp_path, _tier_policy_v2(tmp_path), None, None)

    assert decision.allow is True
    assert ReasonCode.MODEL_UNVERIFIED in decision.warnings
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["model_verified"] is False
    assert entry["warnings"] == ["MODEL_UNVERIFIED"]


def test_register_records_a_failed_model_probe_distinctly(tmp_path: Path) -> None:
    """Not declared and declared-but-unanswered are different states."""

    decision = _registered(
        tmp_path, _tier_policy_v2(tmp_path), "gpt-5.6-luna", None, probe_failed=True
    )

    assert decision.allow is True
    assert ReasonCode.MODEL_PROBE_FAILED in decision.warnings
    assert _ledger_entries(tmp_path)[-1]["model_verified"] is False


def test_register_records_a_verified_match(tmp_path: Path) -> None:
    decision = _registered(
        tmp_path, _tier_policy_v2(tmp_path), "gpt-5.6-luna", "GPT-5.6-Luna"
    )

    assert decision.allow is True
    assert decision.warnings == ()
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["model_verified"] is True
    assert entry["model_declared"] == "gpt-5.6-luna"
    assert entry["model_measured"] == "GPT-5.6-Luna"


def test_register_denies_a_measured_model_in_a_stricter_tier(tmp_path: Path) -> None:
    """The incident was a worker inheriting a tier nobody asked for."""

    decision = _registered(
        tmp_path, _tier_policy_v2(tmp_path), "gpt-5.6-luna", "claude-opus-5"
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.MODEL_TIER_ESCALATION
    assert "measured=claude-opus-5" in decision.message
    entry = _ledger_entries(tmp_path)[-1]
    assert entry["decision"] == "DENY"
    assert entry["model_declared"] == "gpt-5.6-luna"
    assert entry["model_measured"] == "claude-opus-5"


def test_register_allows_a_measured_model_in_a_looser_tier_with_a_warning(
    tmp_path: Path,
) -> None:
    """Running cheaper than declared is not the failure this guards."""

    decision = _registered(
        tmp_path,
        _tier_policy_v2(tmp_path),
        "claude-opus-5",
        "gpt-5.6-luna",
        dispatch_model="claude-opus-5",
    )

    assert decision.allow is True
    assert ReasonCode.MODEL_MISMATCH in decision.warnings


def test_register_under_a_v1_policy_warns_but_cannot_rank(tmp_path: Path) -> None:
    """Version 1 has no tiers to compare, so a mismatch is all it can say."""

    decision = _registered(
        tmp_path, _tier_policy(tmp_path), "gpt-5.6-luna", "gpt-5.6-sol"
    )

    assert decision.allow is True
    assert ReasonCode.MODEL_MISMATCH in decision.warnings


@skip_windows_exec_surface
def test_cli_model_probe_separates_no_command_from_a_failed_one(
    tmp_path: Path,
) -> None:
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_test")
    measure = script["_measure_worker_model"]

    assert measure(None) == (None, False)
    assert measure("echo claude-haiku-4-5") == ("claude-haiku-4-5", False)
    assert measure("printf 'noise\nclaude-haiku-4-5\n'") == (
        "claude-haiku-4-5",
        False,
    )
    assert measure("exit 3") == (None, True)
    assert measure("true") == (None, True)


def _gate(
    tmp_path: Path,
    now: float | None = None,
    clock: _MutableClock | None = None,
    known_roots_path: Path | None = None,
    tier_policy_path: Path | None = None,
) -> DispatchGate:
    return DispatchGate(
        DispatchGateConfig(
            ledger_path=tmp_path / "ledger.jsonl",
            ticket_dir=tmp_path / "dispatch-tickets",
            known_roots_path=known_roots_path or tmp_path / "missing-known-roots.json",
            tier_policy_path=tier_policy_path or _tier_policy(tmp_path),
        ),
        clock=clock or (lambda: now if now is not None else 1_000),
    )


def _tier_policy(tmp_path: Path, unknown_model: str = "deny") -> Path:
    policy = tmp_path / "model-tier-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "worker_allowed": ["gpt-5.6-luna"],
                "worker_denied_tiers": ["gpt-5.6-sol"],
                "unknown_model": unknown_model,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return policy


def _tier_policy_v2(
    tmp_path: Path,
    caps: dict | None = None,
    window_seconds: int = 86_400,
    name: str = "model-tier-policy-v2.json",
) -> Path:
    policy = tmp_path / name
    policy.write_text(
        json.dumps(
            {
                "version": 2,
                "tiers": {
                    "top": ["gpt-5.6-sol", "claude-opus-5"],
                    "efficient": ["gpt-5.6-luna", "claude-haiku-4-5"],
                },
                "fanout_caps": caps if caps is not None else {"top": 1, "unknown": 1},
                "window_seconds": window_seconds,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return policy


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


def test_probe_contract_exit_code_zero_and_job_id_in_stdout(monkeypatch) -> None:
    """The probe helper enforces both exit status and stdout evidence."""
    script = runpy.run_path(str(_script()), run_name="dispatch_gate_probe_test")
    cases = [
        (0, "", "job-123", False),
        # A filename-only stdout containing the id is accepted by the helper,
        # but does not prove that the artifact contents were read.
        (0, "/artifact/job-456.log", "job-456", True),
        (1, "job-789", "job-789", False),
        (0, "processed job-abc-123", "job-abc-123", True),
    ]

    for returncode, stdout, job_id, expected in cases:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, _returncode=returncode, _stdout=stdout, **kwargs: subprocess.CompletedProcess(
                args[0], _returncode, stdout=_stdout, stderr=""
            ),
        )
        assert script["_probe_contains_job_id"]("probe", job_id) is expected


def test_public_probe_docs_state_exit_and_stdout_requirements() -> None:
    repo_root = _script().parents[1]
    for relative_path in (
        "docs/public/delegation-and-review.md",
        "docs/public/reference.md",
    ):
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        assert (
            "exit 0" in text
            or "exits 0" in text
            or "exit with status 0" in text
        )
        assert "stdout" in text
