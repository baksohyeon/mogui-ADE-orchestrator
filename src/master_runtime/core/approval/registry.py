"""In-memory proposal registry and approval enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from master_runtime.core.approval.gates import ActionSpec, GateClass, classify


class ApprovalRequired(RuntimeError):
    """Raised when a gated action lacks an approved proposal."""


class AlreadyDecided(RuntimeError):
    """Raised when a proposal receives more than one decision."""


class UnknownProposal(RuntimeError):
    """Raised when a proposal id is not known to the registry."""


class InvalidAuthority(RuntimeError):
    """Raised when an approval authority is not valid for a proposal."""


class ApprovalVerdict(str, Enum):
    """Final approval decision values."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


Verdict = ApprovalVerdict


class ApprovalAuthority(str, Enum):
    """Typed authorities allowed to approve proposals."""

    HUMAN = "HUMAN"
    POLICY = "POLICY"


Authority = ApprovalAuthority


class ProposalState(str, Enum):
    """Proposal lifecycle states."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True)
class ProposalSpec:
    """Proposal input captured before an approval decision."""

    action: ActionSpec
    description: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    """Recorded approval authority decision."""

    verdict: ApprovalVerdict
    authority: ApprovalAuthority


@dataclass(frozen=True)
class ProposalRecord:
    """Immutable proposal state held by the registry."""

    proposal_id: str
    spec: ProposalSpec
    decision: Optional[DecisionRecord] = None
    state: ProposalState = ProposalState.PENDING


class ProposalRegistry:
    """Deterministic in-memory proposal registry."""

    def __init__(self) -> None:
        self._next_sequence = 1
        self._proposals: Dict[str, ProposalRecord] = {}
        self._proposal_order: List[str] = []

    def propose(self, spec: ProposalSpec) -> str:
        """Register a proposal and return its deterministic sequence id."""

        proposal_id = f"proposal-{self._next_sequence}"
        self._next_sequence += 1
        self._proposals[proposal_id] = ProposalRecord(proposal_id, spec)
        self._proposal_order.append(proposal_id)
        return proposal_id

    def decision(
        self,
        proposal_id: str,
        verdict: Union[ApprovalVerdict, str],
        authority: ApprovalAuthority,
    ) -> None:
        """Record the single final decision for a proposal."""

        record = self._get(proposal_id)
        if record.decision is not None:
            raise AlreadyDecided(f"proposal already decided: {proposal_id}")

        checked_authority = _require_authority(authority)
        checked_verdict = _coerce_verdict(verdict)
        _validate_authority_for_gate(
            classify(record.spec.action),
            checked_authority,
            checked_verdict,
        )
        state = (
            ProposalState.APPROVED
            if checked_verdict == ApprovalVerdict.APPROVED
            else ProposalState.REJECTED
        )
        self._proposals[proposal_id] = ProposalRecord(
            proposal_id=record.proposal_id,
            spec=record.spec,
            decision=DecisionRecord(checked_verdict, checked_authority),
            state=state,
        )

    def pending(self) -> Tuple[ProposalRecord, ...]:
        """Return undecided proposals in deterministic proposal order."""

        return tuple(
            self._proposals[proposal_id]
            for proposal_id in self._proposal_order
            if self._proposals[proposal_id].state == ProposalState.PENDING
        )

    def guard(self, action: ActionSpec, proposal_id: Optional[str]) -> None:
        """Enforce proposal-approval-execution for gated actions."""

        gate = classify(action)
        if gate == GateClass.G0_READ_ONLY:
            return

        if proposal_id is None:
            raise ApprovalRequired("approved proposal required")

        record = self._get(proposal_id)
        if (
            record.decision is None
            or record.decision.verdict != ApprovalVerdict.APPROVED
            or record.state != ProposalState.APPROVED
        ):
            raise ApprovalRequired("approved proposal required")
        if record.spec.action != action:
            raise ApprovalRequired("approved proposal does not match action")

        self._proposals[proposal_id] = ProposalRecord(
            proposal_id=record.proposal_id,
            spec=record.spec,
            decision=record.decision,
            state=ProposalState.CONSUMED,
        )

    def _get(self, proposal_id: str) -> ProposalRecord:
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise UnknownProposal(f"unknown proposal: {proposal_id}") from exc


def _coerce_verdict(verdict: Union[ApprovalVerdict, str]) -> ApprovalVerdict:
    if isinstance(verdict, ApprovalVerdict):
        return verdict

    try:
        return ApprovalVerdict(verdict)
    except ValueError:
        pass

    normalized = verdict.upper()
    try:
        return ApprovalVerdict[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown approval verdict: {verdict}") from exc


def _require_authority(authority: ApprovalAuthority) -> ApprovalAuthority:
    if isinstance(authority, ApprovalAuthority):
        return authority
    raise InvalidAuthority("approval authority must be ApprovalAuthority")


def _validate_authority_for_gate(
    gate: GateClass,
    authority: ApprovalAuthority,
    verdict: ApprovalVerdict,
) -> None:
    if (
        verdict == ApprovalVerdict.APPROVED
        and gate in (GateClass.G2_SHARED_STATE, GateClass.G3_IRREVERSIBLE)
    ):
        if authority != ApprovalAuthority.HUMAN:
            raise InvalidAuthority("G2 and G3 approvals require HUMAN authority")
