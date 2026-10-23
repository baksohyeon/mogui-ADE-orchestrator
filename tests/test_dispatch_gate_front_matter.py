"""Typed contract front matter at the dispatch gate.

Covers the grammar in `DispatchGate.check`: a `---`-delimited block of flat
`key: value` lines, strict on an unknown key, a warning (not a refusal) when
the block is absent entirely, and the five typed keys the contract names.
Fixture tier policy and rule files live under `tmp_path`; the real ledger and
the real `master-ops/rules/standing-rules.md` are never read, except by the
CLI-JSON tests, which run the real script against a fixture tier policy and
fixture rule files passed through `DISPATCH_STANDING_RULES` and
`DISPATCH_STANDING_RULES_LOCAL`.
"""

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
    ReasonCode,
)


def _gate(
    tmp_path: Path,
    tier_policy_path: Path | None = None,
    standing_rules_path: Path | None = None,
    standing_rules_local_path: Path | None = None,
) -> DispatchGate:
    return DispatchGate(
        DispatchGateConfig(
            ledger_path=tmp_path / "ledger.jsonl",
            ticket_dir=tmp_path / "dispatch-tickets",
            known_roots_path=tmp_path / "missing-known-roots.json",
            tier_policy_path=tier_policy_path or _tier_policy(tmp_path),
            standing_rules_path=standing_rules_path or _standing_rules(tmp_path),
            standing_rules_local_path=(
                standing_rules_local_path or tmp_path / "missing-standing-rules.overlay.md"
            ),
        ),
        clock=lambda: 1_000,
    )


def _tier_policy(tmp_path: Path, name: str = "model-tier-policy.json") -> Path:
    policy = tmp_path / name
    policy.write_text(
        json.dumps(
            {
                "version": 2,
                "runtimes": ["claude", "codex"],
                "tiers": {
                    "top": ["claude-opus-5"],
                    "efficient": ["claude-sonnet-5"],
                },
                "fanout_caps": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return policy


def _standing_rules(
    tmp_path: Path,
    names: tuple[str, ...] = ("headless", "ack-token"),
    name: str = "standing-rules.md",
) -> Path:
    path = tmp_path / name
    path.write_text(
        "".join(f"## {rule}\n\n{rule} body text.\n\n" for rule in names),
        encoding="utf-8",
    )
    return path


def _contract(tmp_path: Path, body: str, name: str = "contract.md") -> Path:
    contract = tmp_path / name
    contract.write_text(body, encoding="utf-8")
    return contract


def _request(contract: Path, **overrides: object) -> DispatchRequest:
    fields: dict[str, object] = {
        "runtime": "claude",
        "model": "claude-sonnet-5",
        "contract_path": contract,
        "est_input_chars": 1_000,
        "n_agents": 1,
        "completion_channel": "orchestration",
    }
    fields.update(overrides)
    return DispatchRequest(**fields)


VALID_HEAD = "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n---\n"


def test_valid_front_matter_is_accepted_and_exposed_on_the_decision(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, VALID_HEAD + "\nbody\n")
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert decision.front_matter == {
        "tier": "efficient",
        "runtime": "claude",
        "repo": "example-repo",
    }
    assert ReasonCode.CONTRACT_FRONT_MATTER_MISSING not in decision.warnings


def test_unknown_key_refuses_naming_the_key(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\nbogus: x\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "bogus" in decision.message


def test_missing_tier_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path, "---\nruntime: claude\nrepo: example-repo\n---\n"
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "tier" in decision.message


def test_runtime_different_from_the_request_runtime_is_refused(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: codex\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract, runtime="claude"))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_RUNTIME_MISMATCH
    assert "codex" in decision.message and "claude" in decision.message


def test_runtime_outside_the_policy_runtimes_is_not_eligible(
    tmp_path: Path,
) -> None:
    # The request's own runtime ("claude") is policy-eligible, so this clears
    # the gate's earlier, request-level UNKNOWN_RUNTIME check; it is the
    # front matter's declared runtime ("grok") that the policy does not list,
    # which is what RUNTIME_NOT_ELIGIBLE is about.
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: grok\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract, runtime="claude"))

    assert decision.allow is False
    assert decision.reason == ReasonCode.RUNTIME_NOT_ELIGIBLE


def test_tier_not_in_the_policy_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: nonexistent\nruntime: claude\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_TIER_MISMATCH
    assert "nonexistent" in decision.message


def test_tier_mismatched_with_the_requested_models_tier_is_refused(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: top\nruntime: claude\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(
        _request(contract, model="claude-sonnet-5")
    )

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_TIER_MISMATCH
    assert "top" in decision.message and "efficient" in decision.message


def test_unknown_standing_rule_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "standing_rules: [headless, nonexistent]\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.STANDING_RULE_UNKNOWN
    assert "nonexistent" in decision.message


def test_standing_rule_from_the_local_overlay_only_is_accepted(
    tmp_path: Path,
) -> None:
    local = _standing_rules(tmp_path, names=("seat-only",), name="standing-rules.overlay.md")
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "standing_rules: [seat-only]\n---\n",
    )
    decision = _gate(tmp_path, standing_rules_local_path=local).check(_request(contract))

    assert decision.allow is True
    assert decision.front_matter["standing_rules"] == ["seat-only"]


def test_known_standing_rules_and_budget_and_writes_are_recorded(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "budget: [rounds=2, hours=4, cost_usd=1.5]\n"
        "writes: [src/**, tests/**]\n"
        "standing_rules: [headless, ack-token]\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is True
    assert decision.front_matter["budget"] == {
        "rounds": 2,
        "hours": 4,
        "cost_usd": 1.5,
    }
    assert decision.front_matter["writes"] == ["src/**", "tests/**"]
    assert decision.front_matter["standing_rules"] == ["headless", "ack-token"]


def test_missing_front_matter_block_warns_and_still_allows(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, "no front matter here\n")
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is True
    assert decision.reason == ReasonCode.OK
    assert ReasonCode.CONTRACT_FRONT_MATTER_MISSING in decision.warnings
    assert decision.front_matter is None


def test_malformed_block_names_its_line(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nnot a key value line\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "line 3" in decision.message


def test_unterminated_block_names_its_line(tmp_path: Path) -> None:
    contract = _contract(tmp_path, "---\ntier: efficient\nruntime: claude\n")
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "unterminated" in decision.message


def test_duplicate_key_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "tier: top\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "duplicate key: tier" in decision.message


def test_non_ascii_digit_in_budget_rounds_is_refused(tmp_path: Path) -> None:
    # "²" (superscript two) passes str.isdigit() but int() cannot parse
    # it; this must refuse cleanly instead of raising ValueError.
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "budget: [rounds=²]\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "rounds" in decision.message


def test_non_finite_cost_usd_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "budget: [cost_usd=nan]\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "cost_usd" in decision.message


def test_malformed_writes_shape_is_refused(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "writes: not-a-list\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "writes" in decision.message


def test_standing_rule_name_with_an_unsafe_shape_is_refused(tmp_path: Path) -> None:
    # A space in the name would break the dispatch wrapper's unquoted,
    # space-joined shell loop over the names the gate allows through.
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "standing_rules: [my rule]\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_FRONT_MATTER
    assert "my rule" in decision.message


def test_declared_tier_unknown_matches_an_unlisted_models_computed_tier(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: unknown\nruntime: claude\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(
        _request(contract, model="some-unlisted-model")
    )

    assert decision.allow is True
    assert decision.front_matter["tier"] == "unknown"


def test_declared_tier_unknown_for_a_known_models_tier_is_refused(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: unknown\nruntime: claude\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract, model="claude-sonnet-5"))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_TIER_MISMATCH


def test_error_decisions_never_expose_unvalidated_front_matter(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: top\nruntime: claude\nrepo: example-repo\n---\n",
    )
    decision = _gate(tmp_path).check(_request(contract, model="claude-sonnet-5"))

    assert decision.allow is False
    assert decision.front_matter is None


def test_v1_tier_policy_denies_any_declared_tier(tmp_path: Path) -> None:
    # Front matter's `tier` key is a version 2 concept; a version 1 policy
    # names no tiers at all, so tier_names is empty and any declared tier
    # refuses as a mismatch, documented in the charter paragraph.
    policy = tmp_path / "v1-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "worker_allowed": ["claude-sonnet-5"],
                "worker_denied_tiers": [],
                "unknown_model": "warn",
            }
        ),
        encoding="utf-8",
    )
    contract = _contract(tmp_path, VALID_HEAD + "\nbody\n")
    decision = _gate(tmp_path, tier_policy_path=policy).check(_request(contract))

    assert decision.allow is False
    assert decision.reason == ReasonCode.CONTRACT_TIER_MISMATCH


def test_ledger_row_carries_only_schema_keys(tmp_path: Path) -> None:
    contract = _contract(tmp_path, VALID_HEAD + "\nbody\n")
    gate = _gate(tmp_path)
    gate.check(_request(contract))

    ledger_path = tmp_path / "ledger.jsonl"
    entries = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row = entries[-1]
    assert row["front_matter"] == {
        "tier": "efficient",
        "runtime": "claude",
        "repo": "example-repo",
    }
    assert row["contract_repo"] == "example-repo"


def _run_cli_check(
    tmp_path: Path,
    contract: Path,
    *,
    standing_rules_local_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "dispatch-gate"
    policy = _tier_policy(tmp_path)
    standing_rules = _standing_rules(tmp_path)
    env = os.environ.copy()
    env["DISPATCH_STANDING_RULES"] = str(standing_rules)
    env["DISPATCH_STANDING_RULES_LOCAL"] = str(
        standing_rules_local_path or tmp_path / "missing-standing-rules.overlay.md"
    )
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "check",
            "--runtime",
            "claude",
            "--model",
            "claude-sonnet-5",
            "--tier-policy",
            str(policy),
            "--contract",
            str(contract),
            "--agents",
            "1",
            "--est-chars",
            "1000",
            "--completion-channel",
            "orchestration",
            "--no-record",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_check_prints_front_matter_and_allows(tmp_path: Path) -> None:
    contract = _contract(tmp_path, VALID_HEAD + "\nbody\n")
    result = _run_cli_check(tmp_path, contract)

    payload = json.loads(result.stdout)
    assert payload["allow"] is True
    assert payload["front_matter"] == {
        "tier": "efficient",
        "runtime": "claude",
        "repo": "example-repo",
    }


def test_cli_check_with_an_unknown_key_prints_the_refusal(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\nbogus: x\n---\n",
    )
    result = _run_cli_check(tmp_path, contract)

    payload = json.loads(result.stdout)
    assert payload["allow"] is False
    assert payload["reason"] == "CONTRACT_FRONT_MATTER"
    assert "front_matter" not in payload
    assert result.returncode == 2


def test_cli_check_with_a_named_standing_rule_appears_in_front_matter(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "standing_rules: [headless]\n---\n",
    )
    result = _run_cli_check(tmp_path, contract)

    payload = json.loads(result.stdout)
    assert payload["allow"] is True
    assert payload["front_matter"]["standing_rules"] == ["headless"]


def test_cli_check_with_an_unknown_standing_rule_prints_the_refusal(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        "---\ntier: efficient\nruntime: claude\nrepo: example-repo\n"
        "standing_rules: [nonexistent]\n---\n",
    )
    result = _run_cli_check(tmp_path, contract)

    payload = json.loads(result.stdout)
    assert payload["allow"] is False
    assert payload["reason"] == "STANDING_RULE_UNKNOWN"
    assert result.returncode == 2
