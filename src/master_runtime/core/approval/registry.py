"""In-memory proposal registry and approval enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from master_runtime.core.approval.gates import ActionSpec, GateClass, classify


class ApprovalRequired(RuntimeError):
    """Raised when a gated action lacks an approved proposal."""


class AlreadyDecided(RuntimeError):
    """Raised when a proposal receives more than one decision."""


class UnknownProposal(RuntimeError):
    """Raised when a proposal id is not known to the registry."""


class ApprovalVerdict(str, Enum):
    """Final approval decision values."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


Verdict = ApprovalVerdict


@dataclass(frozen=True)
class ProposalSpec:
    """Proposal input captured before an approval decision."""

    action: ActionSpec
    description: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    """Recorded approval authority decision."""

    verdict: ApprovalVerdict
    authority: str


@dataclass(frozen=True)
class ProposalRecord:
    """Immutable proposal state held by the registry."""

    proposal_id: str
    spec: ProposalSpec
    decision: DecisionRecord | None = None


class ProposalRegistry:
    """Deterministic in-memory proposal registry."""

    def __init__(self) -> None:
        self._next_sequence = 1
        self._proposals: dict[str, ProposalRecord] = {}
        self._proposal_order: list[str] = []

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
        verdict: ApprovalVerdict | str,
        authority: str,
    ) -> None:
        """Record the single final decision for a proposal."""

        record = self._get(proposal_id)
        if record.decision is not None:
            raise AlreadyDecided(f"proposal already decided: {proposal_id}")

        self._proposals[proposal_id] = ProposalRecord(
            proposal_id=record.proposal_id,
            spec=record.spec,
            decision=DecisionRecord(_coerce_verdict(verdict), authority),
        )

    def pending(self) -> tuple[ProposalRecord, ...]:
        """Return undecided proposals in deterministic proposal order."""

        return tuple(
            self._proposals[proposal_id]
            for proposal_id in self._proposal_order
            if self._proposals[proposal_id].decision is None
        )

    def guard(self, action: ActionSpec, proposal_id: str | None) -> None:
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
        ):
            raise ApprovalRequired("approved proposal required")

    def _get(self, proposal_id: str) -> ProposalRecord:
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise UnknownProposal(f"unknown proposal: {proposal_id}") from exc


def _coerce_verdict(verdict: ApprovalVerdict | str) -> ApprovalVerdict:
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
