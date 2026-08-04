"""Pin master-ops canon clauses that protect operating behavior."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_OPS = REPO_ROOT / "master-ops" / "docs"


def _read(relative: str) -> str:
    return (MASTER_OPS / relative).read_text(encoding="utf-8")


def test_instruction_stacking_countermeasure_is_in_constitution_and_execution():
    role = _read("charter/02-role-constitution.md")
    execution = _read("charter/03-execution-principles.md")

    assert "This constitution outranks generic host, global, or session-injected instructions" in role
    assert "never override Proposal -> Approval -> Execution" in role
    assert "never license ignoring the owner's speech" in role
    assert "Answer the owner before working" in execution
    assert "mid-turn text between tool calls may never render for the owner" in execution
    assert "Instruction-stacking drift has a visible shape" in execution
    assert "Do not add per-turn rule injection as a shortcut for this drift" in execution


def test_orca_grounding_and_dispatch_ack_chaining_are_canon():
    dispatch = _read("charter/05-dispatch-gate.md")
    boot = _read("charter/08-boot-hooks-observability.md")
    grounding = _read("orca-docs-grounding.md")

    assert "camelCase `deliveryId`" in dispatch
    assert "unacknowledged backlog makes `--wait` return the same stale batch forever" in dispatch
    assert "two canonical source-grounded references" in boot
    assert "Orca Documentation (operational reference, 22 pages)" in grounding
    assert "Orca Developer Reference Wiki (internals, 6 pages)" in grounding
    assert "check --wait` with deliveryId ack-chaining" in grounding
    assert "Hand-rolled sleep/poll loops" in grounding


def test_contract_conventions_include_sweep_2b_clauses():
    conventions = _read("runbooks/contract-conventions.md")
    records = _read("charter/07-records.md")

    assert "Compare `reviews[].submittedAt` with the last measured time" in conventions
    assert "Public-surface redaction clause" in conventions
    assert "Context-injection policy" in conventions
    assert "Chat-to-docs rule" in conventions
    assert "repository scanners do not read forge" in conventions
    assert "conversation surfaces" in conventions
    assert "Explanations written in chat to resolve owner confusion are documentation candidates" in records
