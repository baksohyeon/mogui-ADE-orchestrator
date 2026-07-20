"""Approval gate classification and proposal registry."""

from master_runtime.core.approval.gates import ActionSpec, GateClass, classify
from master_runtime.core.approval.registry import (
    AlreadyDecided,
    ApprovalAuthority,
    ApprovalRequired,
    ApprovalVerdict,
    Authority,
    DecisionRecord,
    InvalidAuthority,
    ProposalRecord,
    ProposalRegistry,
    ProposalSpec,
    ProposalState,
    UnknownProposal,
    Verdict,
)

__all__ = [
    "ActionSpec",
    "GateClass",
    "classify",
    "AlreadyDecided",
    "ApprovalAuthority",
    "ApprovalRequired",
    "ApprovalVerdict",
    "Authority",
    "DecisionRecord",
    "InvalidAuthority",
    "ProposalRecord",
    "ProposalRegistry",
    "ProposalSpec",
    "ProposalState",
    "UnknownProposal",
    "Verdict",
]
