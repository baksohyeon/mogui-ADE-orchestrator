from __future__ import annotations

from typing import get_type_hints
import unittest

from master_runtime.core.approval import registry as registry_module
from master_runtime.core.approval.gates import ActionSpec, GateClass, classify
from master_runtime.core.approval.registry import (
    AlreadyDecided,
    ApprovalAuthority,
    ApprovalRequired,
    ApprovalVerdict,
    InvalidAuthority,
    ProposalRegistry,
    ProposalSpec,
    UnknownProposal,
)


def action(
    *,
    read_only: bool = False,
    writes_local: bool = False,
    writes_shared: bool = False,
    irreversible: bool = False,
    description: str = "test action",
) -> ActionSpec:
    return ActionSpec(
        read_only=read_only,
        writes_local=writes_local,
        writes_shared=writes_shared,
        irreversible=irreversible,
        description=description,
    )


def proposal_spec(action_spec: ActionSpec) -> ProposalSpec:
    return ProposalSpec(action=action_spec, description="test proposal")


class ApprovalGateTests(unittest.TestCase):
    def test_classification_matrix(self) -> None:
        cases = (
            (action(read_only=True), GateClass.G0_READ_ONLY),
            (action(), GateClass.G2_SHARED_STATE),
            (action(writes_local=True), GateClass.G1_REVERSIBLE_LOCAL),
            (action(writes_shared=True), GateClass.G2_SHARED_STATE),
            (
                action(writes_local=True, writes_shared=True),
                GateClass.G2_SHARED_STATE,
            ),
            (action(irreversible=True), GateClass.G3_IRREVERSIBLE),
            (
                action(writes_local=True, writes_shared=True, irreversible=True),
                GateClass.G3_IRREVERSIBLE,
            ),
        )

        for action_spec, expected_gate in cases:
            with self.subTest(action=action_spec):
                self.assertEqual(classify(action_spec), expected_gate)

    def test_invalid_read_only_combinations_raise_value_error(self) -> None:
        invalid_kwargs = (
            {"read_only": True, "writes_local": True},
            {"read_only": True, "writes_shared": True},
            {"read_only": True, "irreversible": True},
        )

        for kwargs in invalid_kwargs:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    classify(action(**kwargs))


class ProposalRegistryTests(unittest.TestCase):
    def test_guard_g0_passes_without_proposal(self) -> None:
        registry = ProposalRegistry()

        registry.guard(action(read_only=True), None)

    def test_guard_g1_without_approval_raises_approval_required(self) -> None:
        registry = ProposalRegistry()

        with self.assertRaises(ApprovalRequired):
            registry.guard(action(writes_local=True), None)

    def test_guard_unclassified_action_fails_closed(self) -> None:
        registry = ProposalRegistry()

        with self.assertRaises(ApprovalRequired):
            registry.guard(action(), None)

    def test_approve_then_guard_passes(self) -> None:
        registry = ProposalRegistry()
        action_spec = action(writes_local=True)
        proposal_id = registry.propose(proposal_spec(action_spec))

        registry.decision(proposal_id, ApprovalVerdict.APPROVED, ApprovalAuthority.POLICY)

        registry.guard(action_spec, proposal_id)

    def test_guard_rejects_action_that_does_not_match_approved_spec(self) -> None:
        registry = ProposalRegistry()
        approved_action = action(writes_local=True, description="write local file")
        different_action = action(writes_shared=True, description="write shared state")
        proposal_id = registry.propose(proposal_spec(approved_action))
        registry.decision(proposal_id, ApprovalVerdict.APPROVED, ApprovalAuthority.HUMAN)

        with self.assertRaises(ApprovalRequired):
            registry.guard(different_action, proposal_id)

        registry.guard(approved_action, proposal_id)

    def test_guard_consumes_approved_proposal_once(self) -> None:
        registry = ProposalRegistry()
        action_spec = action(writes_local=True)
        proposal_id = registry.propose(proposal_spec(action_spec))
        registry.decision(proposal_id, ApprovalVerdict.APPROVED, ApprovalAuthority.POLICY)

        registry.guard(action_spec, proposal_id)

        with self.assertRaises(ApprovalRequired):
            registry.guard(action_spec, proposal_id)

    def test_reject_then_guard_raises_approval_required(self) -> None:
        registry = ProposalRegistry()
        action_spec = action(writes_shared=True)
        proposal_id = registry.propose(proposal_spec(action_spec))
        registry.decision(proposal_id, ApprovalVerdict.REJECTED, ApprovalAuthority.POLICY)

        with self.assertRaises(ApprovalRequired):
            registry.guard(action_spec, proposal_id)

    def test_double_decision_raises_already_decided(self) -> None:
        registry = ProposalRegistry()
        proposal_id = registry.propose(proposal_spec(action(writes_local=True)))
        registry.decision(proposal_id, ApprovalVerdict.APPROVED, ApprovalAuthority.POLICY)

        with self.assertRaises(AlreadyDecided):
            registry.decision(proposal_id, ApprovalVerdict.REJECTED, ApprovalAuthority.POLICY)

    def test_unknown_id_raises_unknown_proposal(self) -> None:
        registry = ProposalRegistry()

        with self.assertRaises(UnknownProposal):
            registry.guard(action(writes_local=True), "proposal-404")

        with self.assertRaises(UnknownProposal):
            registry.decision(
                "proposal-404",
                ApprovalVerdict.APPROVED,
                ApprovalAuthority.HUMAN,
            )

    def test_g2_and_g3_require_human_authority(self) -> None:
        registry = ProposalRegistry()
        shared_id = registry.propose(proposal_spec(action(writes_shared=True)))
        irreversible_id = registry.propose(proposal_spec(action(irreversible=True)))

        with self.assertRaises(InvalidAuthority):
            registry.decision(shared_id, ApprovalVerdict.APPROVED, ApprovalAuthority.POLICY)

        with self.assertRaises(InvalidAuthority):
            registry.decision(
                irreversible_id,
                ApprovalVerdict.APPROVED,
                ApprovalAuthority.POLICY,
            )

    def test_string_authority_is_rejected(self) -> None:
        registry = ProposalRegistry()
        proposal_id = registry.propose(proposal_spec(action(writes_shared=True)))

        with self.assertRaises(InvalidAuthority):
            registry.decision(proposal_id, ApprovalVerdict.APPROVED, "HUMAN")

    def test_pending_ordering_is_deterministic(self) -> None:
        registry = ProposalRegistry()
        first = registry.propose(proposal_spec(action(writes_local=True)))
        second = registry.propose(proposal_spec(action(writes_shared=True)))
        third = registry.propose(proposal_spec(action(irreversible=True)))
        registry.decision(second, ApprovalVerdict.APPROVED, ApprovalAuthority.HUMAN)

        self.assertEqual(first, "proposal-1")
        self.assertEqual(second, "proposal-2")
        self.assertEqual(third, "proposal-3")
        self.assertEqual(
            tuple(proposal.proposal_id for proposal in registry.pending()),
            ("proposal-1", "proposal-3"),
        )

    def test_registry_type_hints_are_evaluable(self) -> None:
        get_type_hints(registry_module.DecisionRecord)
        get_type_hints(registry_module.ProposalRecord)
        get_type_hints(registry_module.ProposalRegistry.decision)
        get_type_hints(registry_module.ProposalRegistry.guard)


if __name__ == "__main__":
    unittest.main()
