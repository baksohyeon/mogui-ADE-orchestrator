"""Audit records rendered from one acceptance run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from master_runtime.core.acceptance.casebook import GATED_SPLITS, CaseSplit
from master_runtime.core.acceptance.models import AcceptanceConfig, Candidate
from master_runtime.core.acceptance.verdict import AcceptanceVerdict, Scorecard


@dataclass(frozen=True)
class IterationRecord:
    """One audited acceptance iteration."""

    iteration: int
    starting_label: str
    candidate: Optional[Candidate]
    verdict: Optional[AcceptanceVerdict]
    promoted_regressions: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        """Serialize the iteration record."""

        return {
            "iteration": self.iteration,
            "starting_label": self.starting_label,
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
            "verdict": None if self.verdict is None else self.verdict.to_dict(),
            "promoted_regressions": list(self.promoted_regressions),
        }


@dataclass(frozen=True)
class AcceptanceReport:
    """Final report for one acceptance run."""

    created_at: float
    config: AcceptanceConfig
    baseline: Candidate
    final: Candidate
    baseline_score: Scorecard
    final_score: Scorecard
    baseline_scorecard: Optional[Scorecard]
    final_scorecard: Optional[Scorecard]
    iterations: Tuple[IterationRecord, ...]

    @property
    def accepted_count(self) -> int:
        """Return how many candidates were accepted."""

        return sum(
            1
            for record in self.iterations
            if record.verdict is not None and record.verdict.accepted
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialize the report."""

        return {
            "created_at": self.created_at,
            "config": self.config.to_dict(),
            "baseline": self.baseline.to_dict(),
            "final": self.final.to_dict(),
            "baseline_score": self.baseline_score.to_dict(),
            "final_score": self.final_score.to_dict(),
            "baseline_scorecard": None
            if self.baseline_scorecard is None
            else self.baseline_scorecard.to_dict(),
            "final_scorecard": None
            if self.final_scorecard is None
            else self.final_scorecard.to_dict(),
            "iterations": [record.to_dict() for record in self.iterations],
        }

    def to_markdown(self) -> str:
        """Render a concise Markdown report."""

        lines = [
            "# Acceptance Report: {0}".format(self.config.name),
            "",
            "- Baseline: `{0}`".format(self.baseline.label),
            "- Final: `{0}`".format(self.final.label),
            "- Accepted candidates: `{0}/{1}`".format(
                self.accepted_count, len(self.iterations)
            ),
            "",
            "| Split | Baseline | Final |",
            "| --- | --- | --- |",
        ]
        for split in GATED_SPLITS:
            baseline_split = self.baseline_score.split_score(split)
            final_split = self.final_score.split_score(split)
            lines.append(
                "| {0} | `{1}/{2}` | `{3}/{4}` |".format(
                    split.value,
                    baseline_split.passed,
                    baseline_split.total,
                    final_split.passed,
                    final_split.total,
                )
            )
        if self.baseline_scorecard is not None and self.final_scorecard is not None:
            baseline_split = self.baseline_scorecard.split_score(CaseSplit.SCORECARD)
            final_split = self.final_scorecard.split_score(CaseSplit.SCORECARD)
            lines.append(
                "| scorecard | `{0}/{1}` | `{2}/{3}` |".format(
                    baseline_split.passed,
                    baseline_split.total,
                    final_split.passed,
                    final_split.total,
                )
            )

        lines.extend(["", "## Iterations", ""])
        if not self.iterations:
            lines.append("- No iterations were run.")
        for record in self.iterations:
            if record.candidate is None or record.verdict is None:
                lines.append(
                    "- Iteration {0}: no candidate produced".format(record.iteration)
                )
                continue
            lines.extend(
                [
                    "- Iteration {0}: {1} `{2}`".format(
                        record.iteration,
                        "accepted" if record.verdict.accepted else "rejected",
                        record.candidate.label,
                    ),
                    "  - Reason: `{0}`".format(record.verdict.reason.value),
                    "  - Combined: `{0} -> {1}` (delta `{2}`)".format(
                        record.verdict.current_combined,
                        record.verdict.candidate_combined,
                        record.verdict.delta,
                    ),
                    "  - Changed surfaces: `{0}`".format(
                        ", ".join(record.candidate.surfaces) or "none"
                    ),
                ]
            )
            if record.promoted_regressions:
                lines.append(
                    "  - Pinned regressions: `{0}`".format(
                        ", ".join(record.promoted_regressions)
                    )
                )
        lines.append("")
        return "\n".join(lines)
