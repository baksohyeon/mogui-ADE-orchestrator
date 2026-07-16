"""Approval gate classification and proposal registry."""

from master_runtime.core.approval.gates import ActionSpec, GateClass, classify
from master_runtime.core.approval.registry import (
    AlreadyDecided,
    ApprovalRequired,
    ApprovalVerdict,
    DecisionRecord,
    ProposalRecord,
    ProposalRegistry,
    ProposalSpec,
    UnknownProposal,
    Verdict,
)

__all__ = [
    "ActionSpec",
    "GateClass",
    "classify",
    "AlreadyDecided",
    "ApprovalRequired",
    "ApprovalVerdict",
    "DecisionRecord",
    "ProposalRecord",
    "ProposalRegistry",
    "ProposalSpec",
    "UnknownProposal",
    "Verdict",
]
