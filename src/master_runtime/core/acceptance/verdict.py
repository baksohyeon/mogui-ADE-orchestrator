"""Deterministic candidate acceptance comparison.

Acceptance is a pure comparison of pass counts. No model judgement, no heuristic
score, no natural-language rationale participates in the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Sequence, Tuple

from master_runtime.core.acceptance.casebook import (
    GATED_SPLITS,
    CaseSplit,
    VerificationCase,
)


MISSING_RESULT_DETAIL = "missing result"


class AcceptanceReason(str, Enum):
    """Stable acceptance decision reason codes."""

    PASS_COUNT_INCREASED = "PASS_COUNT_INCREASED"
    NO_PASS_COUNT_INCREASE = "NO_PASS_COUNT_INCREASE"
    NO_CANDIDATE_CHANGE = "NO_CANDIDATE_CHANGE"


@dataclass(frozen=True)
class CaseResult:
    """One case-level verification outcome."""

    case_id: str
    split: CaseSplit
    stratum: str
    passed: bool
    detail: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        """Serialize the result."""

        return {
            "case_id": self.case_id,
            "split": self.split.value,
            "stratum": self.stratum,
            "passed": self.passed,
            "detail": self.detail,
            "duration_s": self.duration_s,
        }


@dataclass(frozen=True)
class SplitScore:
    """Aggregate outcome for one split."""

    split: CaseSplit
    passed: int
    total: int
    failed_case_ids: Tuple[str, ...] = ()

    @property
    def correctness(self) -> float:
        """Return the pass rate for the split."""

        return 0.0 if self.total == 0 else self.passed / self.total

    def to_dict(self) -> Dict[str, object]:
        """Serialize the split score."""

        return {
            "split": self.split.value,
            "passed": self.passed,
            "total": self.total,
            "correctness": self.correctness,
            "failed_case_ids": list(self.failed_case_ids),
        }


@dataclass(frozen=True)
class Scorecard:
    """Full verification outcome for one candidate."""

    label: str
    splits: Tuple[SplitScore, ...]
    results: Tuple[CaseResult, ...]

    def split_score(self, split: CaseSplit) -> SplitScore:
        """Return the score for one split, or an empty score when absent."""

        for score in self.splits:
            if score.split == split:
                return score
        return SplitScore(split=split, passed=0, total=0)

    def combined_passed(self) -> int:
        """Return the pass count the acceptance gate compares."""

        return sum(self.split_score(split).passed for split in GATED_SPLITS)

    def combined_total(self) -> int:
        """Return the total case count the acceptance gate compares against."""

        return sum(self.split_score(split).total for split in GATED_SPLITS)

    def is_complete(self) -> bool:
        """Return whether every gated case passed."""

        return self.combined_total() > 0 and self.combined_passed() == self.combined_total()

    def failed_results(self) -> Tuple[CaseResult, ...]:
        """Return every failing case result."""

        return tuple(result for result in self.results if not result.passed)

    def visible_failures(self) -> Tuple[CaseResult, ...]:
        """Return only the failures a candidate proposer may be shown."""

        return tuple(
            result
            for result in self.failed_results()
            if result.split == CaseSplit.TRAIN
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialize the scorecard."""

        return {
            "label": self.label,
            "combined_passed": self.combined_passed(),
            "combined_total": self.combined_total(),
            "splits": [score.to_dict() for score in self.splits],
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class AcceptanceVerdict:
    """Outcome of the deterministic acceptance comparison."""

    accepted: bool
    reason: AcceptanceReason
    current_combined: int
    candidate_combined: int

    @property
    def delta(self) -> int:
        """Return the combined pass-count delta."""

        return self.candidate_combined - self.current_combined

    def to_dict(self) -> Dict[str, object]:
        """Serialize the verdict."""

        return {
            "accepted": self.accepted,
            "reason": self.reason.value,
            "current_combined": self.current_combined,
            "candidate_combined": self.candidate_combined,
            "delta": self.delta,
        }


def score_results(
    *,
    label: str,
    cases: Sequence[VerificationCase],
    results: Iterable[CaseResult],
) -> Scorecard:
    """Score one candidate, treating any missing case result as a failure.

    Scoring is fail-closed on purpose: an evaluator that silently skips a case must
    not be able to raise a candidate's pass count.
    """

    by_id: Dict[str, CaseResult] = {}
    for result in results:
        by_id[result.case_id] = result

    ordered: list = []
    for case in cases:
        result = by_id.get(case.case_id)
        if result is None:
            result = CaseResult(
                case_id=case.case_id,
                split=case.split,
                stratum=case.stratum,
                passed=False,
                detail=MISSING_RESULT_DETAIL,
            )
        else:
            # The case book, not the evaluator, owns split and stratum.
            result = CaseResult(
                case_id=case.case_id,
                split=case.split,
                stratum=case.stratum,
                passed=bool(result.passed),
                detail=result.detail,
                duration_s=result.duration_s,
            )
        ordered.append(result)

    return Scorecard(
        label=label,
        splits=_split_scores(cases, ordered),
        results=tuple(ordered),
    )


def decide(
    *,
    current: Scorecard,
    candidate: Scorecard,
    candidate_changed: bool = True,
) -> AcceptanceVerdict:
    """Accept a candidate only when it strictly increases the combined pass count."""

    current_combined = current.combined_passed()
    candidate_combined = candidate.combined_passed()

    if not candidate_changed:
        return AcceptanceVerdict(
            accepted=False,
            reason=AcceptanceReason.NO_CANDIDATE_CHANGE,
            current_combined=current_combined,
            candidate_combined=candidate_combined,
        )

    if candidate_combined > current_combined:
        return AcceptanceVerdict(
            accepted=True,
            reason=AcceptanceReason.PASS_COUNT_INCREASED,
            current_combined=current_combined,
            candidate_combined=candidate_combined,
        )

    return AcceptanceVerdict(
        accepted=False,
        reason=AcceptanceReason.NO_PASS_COUNT_INCREASE,
        current_combined=current_combined,
        candidate_combined=candidate_combined,
    )


def failed_cases(
    *,
    cases: Sequence[VerificationCase],
    scorecard: Scorecard,
) -> Tuple[VerificationCase, ...]:
    """Map failing results back to their case-book entries."""

    failed_ids = {result.case_id for result in scorecard.failed_results()}
    return tuple(case for case in cases if case.case_id in failed_ids)


def _split_scores(
    cases: Sequence[VerificationCase],
    results: Sequence[CaseResult],
) -> Tuple[SplitScore, ...]:
    ordered_splits: list = []
    for case in cases:
        if case.split not in ordered_splits:
            ordered_splits.append(case.split)

    by_split: Dict[CaseSplit, list] = {split: [] for split in ordered_splits}
    for result in results:
        by_split[result.split].append(result)

    scores: list = []
    for split in ordered_splits:
        split_results = by_split[split]
        scores.append(
            SplitScore(
                split=split,
                passed=sum(1 for result in split_results if result.passed),
                total=len(split_results),
                failed_case_ids=tuple(
                    result.case_id for result in split_results if not result.passed
                ),
            )
        )
    return tuple(scores)
