"""Run-directory layout that separates proposer-visible from private artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple, Union

from master_runtime.core.acceptance.casebook import (
    CaseBook,
    CaseSplit,
    is_visible_split,
    render_split_markdown,
)
from master_runtime.core.acceptance.models import AcceptanceConfig, Candidate
from master_runtime.core.acceptance.report import AcceptanceReport
from master_runtime.core.acceptance.verdict import AcceptanceVerdict, Scorecard


def write_json(path: Path, payload: object) -> None:
    """Write one JSON artifact atomically, with stable key ordering.

    Every artifact in a run goes through here, so a killed run leaves whole files or
    no file, never a truncated one an auditor would read as fact.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(".{0}.{1}.tmp".format(path.name, os.getpid()))
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def write_text(path: Path, text: str) -> None:
    """Write one text artifact atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(".{0}.{1}.tmp".format(path.name, os.getpid()))
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


class AcceptanceRunLayout:
    """Filesystem layout for one acceptance run.

    Anything under ``history/visible`` may be copied into a proposer workspace.
    Anything under ``history/private`` must not.
    """

    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)

    @property
    def visible_root(self) -> Path:
        """Return the root of proposer-visible artifacts."""

        return self.root / "history" / "visible"

    @property
    def private_root(self) -> Path:
        """Return the root of artifacts withheld from the proposer."""

        return self.root / "history" / "private"

    @property
    def iterations_dir(self) -> Path:
        """Return the visible per-iteration decision directory."""

        return self.visible_root / "iterations"

    def split_dir(self, *, label: str, split: CaseSplit) -> Path:
        """Return the artifact directory for one candidate and split."""

        base = self.visible_root if is_visible_split(split) else self.private_root
        return base / split.value / label

    def iteration_dir(self, iteration: int) -> Path:
        """Return the directory for one iteration."""

        return self.iterations_dir / "{0:03d}".format(iteration)

    def proposer_workspace_dir(self, iteration: int) -> Path:
        """Return the proposer workspace for one iteration."""

        return self.iteration_dir(iteration) / "proposer_workspace"

    @property
    def report_path(self) -> Path:
        """Return the final JSON report path."""

        return self.root / "report.json"

    def write_manifest(self, config: AcceptanceConfig, casebook: CaseBook) -> None:
        """Write run metadata plus the master-side split manifest."""

        write_json(self.root / "manifest.json", config.to_dict())
        write_json(self.root / "split.json", casebook.manifest())
        write_text(self.root / "split.md", render_split_markdown(casebook))

    def write_split_results(self, scorecard: Scorecard) -> None:
        """Persist per-split results, routing private splits away from the proposer."""

        for score in scorecard.splits:
            split_dir = self.split_dir(label=scorecard.label, split=score.split)
            write_json(
                split_dir / "result.json",
                {
                    **score.to_dict(),
                    "label": scorecard.label,
                    "results": [
                        result.to_dict()
                        for result in scorecard.results
                        if result.split == score.split
                    ],
                },
            )

    def write_iteration_decision(
        self,
        *,
        iteration: int,
        starting_label: str,
        candidate: Candidate,
        verdict: AcceptanceVerdict,
        promoted_regressions: Sequence[str] = (),
    ) -> Path:
        """Append one audited decision record for the iteration."""

        iteration_dir = self.iteration_dir(iteration)
        decision = verdict.decision_label
        payload: Dict[str, object] = {
            "iteration": iteration,
            "starting_label": starting_label,
            "candidate_label": candidate.label,
            "candidate_ref": candidate.ref,
            "decision": decision,
            "reason": verdict.reason.value,
            "changed_surfaces": list(candidate.surfaces),
            "current_combined": verdict.current_combined,
            "candidate_combined": verdict.candidate_combined,
            "delta": verdict.delta,
            "promoted_regressions": list(promoted_regressions),
            "summary": candidate.summary,
        }
        decision_path = iteration_dir / "decision.json"
        write_json(decision_path, payload)
        lines = [
            "# Iteration {0}".format(iteration),
            "",
            "- Starting: `{0}`".format(starting_label),
            "- Candidate: `{0}`".format(candidate.label),
            "- Decision: `{0}`".format(decision),
            "- Reason: `{0}`".format(verdict.reason.value),
            "- Combined: `{0} -> {1}` (delta `{2}`)".format(
                verdict.current_combined, verdict.candidate_combined, verdict.delta
            ),
            "- Changed surfaces: `{0}`".format(", ".join(candidate.surfaces) or "none"),
            "",
            "## Summary",
            "",
            candidate.summary or "_No proposal summary written._",
            "",
        ]
        write_text(iteration_dir / "decision.md", "\n".join(lines))
        return decision_path

    def read_decisions(self) -> Tuple[Mapping[str, object], ...]:
        """Return every written decision record in iteration order.

        Cold path: for auditing a finished run. A live loop already holds its
        iteration records in memory and must not re-read them from disk.
        """

        decisions: List[Mapping[str, object]] = []
        if not self.iterations_dir.exists():
            return ()
        for path in sorted(self.iterations_dir.glob("*/decision.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                decisions.append(payload)
        return tuple(decisions)

    def write_report(self, report: AcceptanceReport) -> None:
        """Write the final JSON and Markdown reports."""

        write_json(self.report_path, report.to_dict())
        write_text(self.root / "report.md", report.to_markdown())
