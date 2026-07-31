"""Deterministic acceptance loop for master-dispatched worker deliverables.

The loop keeps a candidate only when it strictly increases the combined pass count
over the visible (train) and private (holdout) splits. The private split is never
written into the proposer workspace, so a proposer cannot tune against the cases that
decide its fate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from master_runtime.core.acceptance.casebook import (
    CaseBook,
    CaseSplit,
    RegressionLog,
    VerificationCase,
)
from master_runtime.core.acceptance.layout import AcceptanceRunLayout, write_json
from master_runtime.core.acceptance.models import (
    CANDIDATE_FILENAME,
    CANDIDATE_LABEL_FORMAT,
    PROPOSAL_FILENAME,
    TASK_FILENAME,
    AcceptanceConfig,
    Candidate,
    Evaluator,
    Proposer,
    ProposerContext,
)
from master_runtime.core.acceptance.proposer import (
    CliRunner,
    ProposerRequest,
    invoke_cli_proposer,
)
from master_runtime.core.acceptance.report import AcceptanceReport, IterationRecord
from master_runtime.core.acceptance.verdict import (
    Scorecard,
    decide,
    failed_cases,
    score_results,
)


def build_proposer_workspace(
    *,
    layout: AcceptanceRunLayout,
    iteration: int,
    current: Candidate,
    casebook: CaseBook,
    scorecard: Scorecard,
) -> Path:
    """Materialize the visible-only workspace handed to a proposer."""

    workspace = layout.proposer_workspace_dir(iteration)
    workspace.mkdir(parents=True, exist_ok=True)

    visible_failures = scorecard.visible_failures()
    write_json(
        workspace / "visible_failures.json",
        [result.to_dict() for result in visible_failures],
    )
    write_json(workspace / "casebook_visible.json", casebook.visible_manifest())
    write_json(
        workspace / "history.json",
        [
            {
                "iteration": decision.get("iteration"),
                "decision": decision.get("decision"),
                "reason": decision.get("reason"),
                "changed_surfaces": decision.get("changed_surfaces", []),
            }
            for decision in layout.read_decisions()
        ],
    )

    failure_lines = [
        "- `{0}` [{1}]: {2}".format(
            result.case_id, result.stratum, result.detail or "failed"
        )
        for result in visible_failures
    ]
    if not failure_lines:
        failure_lines.append("- No visible failures remain.")

    train_score = scorecard.split_score(CaseSplit.TRAIN)
    (workspace / TASK_FILENAME).write_text(
        "\n".join(
            [
                "# Candidate Proposal Task",
                "",
                "You are proposing one candidate change to the target repository.",
                "",
                "Rules:",
                "- Fix the visible failures listed below.",
                "- Prefer a general fix over anything that special-cases a listed case id.",
                "- A private holdout split you cannot see decides acceptance. Overfitting to",
                "  the visible cases will be rejected by the pass-count comparison.",
                "- When you are done, write `{0}` with the changed surfaces and a summary,".format(
                    workspace / CANDIDATE_FILENAME
                ),
                '  shaped as {"surfaces": ["path/one.py"], "summary": "what changed and why"}.',
                "  Without that file the proposal is discarded.",
                "- Also write a short rationale to `{0}`.".format(
                    workspace / PROPOSAL_FILENAME
                ),
                "",
                "Repository under change: `{0}`".format(current.ref or "current workspace"),
                "Current candidate: `{0}`".format(current.label),
                "Visible score: `{0}/{1}`".format(train_score.passed, train_score.total),
                "",
                "Visible failures:",
                *failure_lines,
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / PROPOSAL_FILENAME).write_text(
        "# Proposal\n\n- Summary:\n- Why this should help:\n- Surfaces changed:\n",
        encoding="utf-8",
    )
    return workspace


def read_candidate(workspace: Path, label: str) -> Optional[Candidate]:
    """Read the candidate a proposer declared, failing closed when it is absent."""

    candidate_path = workspace / CANDIDATE_FILENAME
    if not candidate_path.exists():
        return None
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, (list, tuple)):
        return None
    declared = tuple(item for item in surfaces if isinstance(item, str) and item.strip())
    if not declared:
        return None

    summary = payload.get("summary")
    ref = payload.get("ref")
    proposal_path = workspace / PROPOSAL_FILENAME
    if not isinstance(summary, str) or not summary.strip():
        summary = proposal_path.read_text(encoding="utf-8").strip() if proposal_path.exists() else ""
    return Candidate(
        label=label,
        ref=ref if isinstance(ref, str) else "",
        surfaces=declared,
        summary=summary,
    )


def cli_proposer(
    config: AcceptanceConfig,
    runner: Optional[CliRunner] = None,
) -> Proposer:
    """Build a proposer backed by a subscription CLI subprocess."""

    def propose(context: ProposerContext) -> Optional[Candidate]:
        prompt = (context.workspace_dir / TASK_FILENAME).read_text(encoding="utf-8")
        result = invoke_cli_proposer(
            ProposerRequest(
                runtime=config.proposer_runtime,
                prompt=prompt,
                cwd=config.workspace_root,
                model=config.proposer_model,
                timeout_seconds=config.proposer_timeout_seconds,
            ),
            runner=runner,
        )
        write_json(context.workspace_dir / "proposer_result.json", result.to_dict())
        (context.workspace_dir / "proposer_stdout.log").write_text(
            result.stdout, encoding="utf-8"
        )
        (context.workspace_dir / "proposer_stderr.log").write_text(
            result.stderr, encoding="utf-8"
        )
        if not result.ok:
            return None
        return read_candidate(
            context.workspace_dir,
            CANDIDATE_LABEL_FORMAT.format(context.iteration),
        )

    return propose


def run_acceptance_loop(
    *,
    config: AcceptanceConfig,
    casebook: CaseBook,
    baseline: Candidate,
    proposer: Proposer,
    evaluator: Evaluator,
    regression_log: Optional[RegressionLog] = None,
    on_reject: Optional[Callable[[Candidate], None]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> AcceptanceReport:
    """Run the acceptance loop and return its audited report."""

    if config.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    now = clock or time.time
    casebook.validate()
    if regression_log is not None:
        casebook = regression_log.apply(casebook)

    layout = AcceptanceRunLayout(config.run_dir)
    layout.write_manifest(config, casebook)

    gated = casebook.gated_cases()
    scorecard_cases = casebook.cases_for_split(CaseSplit.SCORECARD)

    current = baseline
    baseline_score = _evaluate(
        evaluator=evaluator, candidate=baseline, cases=gated, layout=layout
    )
    current_score = baseline_score
    _promote(regression_log, gated, baseline_score, iteration=0)

    iterations: List[IterationRecord] = []
    for index in range(1, config.max_iterations + 1):
        if current_score.is_complete():
            break

        workspace = build_proposer_workspace(
            layout=layout,
            iteration=index,
            current=current,
            casebook=casebook,
            scorecard=current_score,
        )
        candidate = proposer(
            ProposerContext(
                iteration=index,
                workspace_dir=workspace,
                current=current,
                visible_cases=casebook.visible_cases(),
                visible_failures=current_score.visible_failures(),
            )
        )
        if candidate is None or not candidate.changed:
            iterations.append(
                IterationRecord(
                    iteration=index,
                    starting_label=current.label,
                    candidate=None,
                    verdict=None,
                )
            )
            break

        candidate_score = _evaluate(
            evaluator=evaluator, candidate=candidate, cases=gated, layout=layout
        )
        verdict = decide(
            current=current_score,
            candidate=candidate_score,
            candidate_changed=candidate.changed,
        )
        promoted = _promote(regression_log, gated, candidate_score, iteration=index)
        layout.write_iteration_decision(
            iteration=index,
            starting_label=current.label,
            candidate=candidate,
            verdict=verdict,
            promoted_regressions=promoted,
        )
        iterations.append(
            IterationRecord(
                iteration=index,
                starting_label=current.label,
                candidate=candidate,
                verdict=verdict,
                promoted_regressions=promoted,
            )
        )
        if verdict.accepted:
            current = candidate
            current_score = candidate_score
        elif on_reject is not None:
            on_reject(candidate)

    baseline_scorecard = None
    final_scorecard = None
    if scorecard_cases:
        baseline_scorecard = _evaluate(
            evaluator=evaluator,
            candidate=baseline,
            cases=scorecard_cases,
            layout=layout,
            label_suffix="scorecard",
        )
        final_scorecard = _evaluate(
            evaluator=evaluator,
            candidate=current,
            cases=scorecard_cases,
            layout=layout,
            label_suffix="scorecard",
        )

    report = AcceptanceReport(
        created_at=float(now()),
        config=config,
        baseline=baseline,
        final=current,
        baseline_score=baseline_score,
        final_score=current_score,
        baseline_scorecard=baseline_scorecard,
        final_scorecard=final_scorecard,
        iterations=tuple(iterations),
    )
    layout.write_report(report)
    return report


def _evaluate(
    *,
    evaluator: Evaluator,
    candidate: Candidate,
    cases: Sequence[VerificationCase],
    layout: AcceptanceRunLayout,
    label_suffix: str = "",
) -> Scorecard:
    label = candidate.label if not label_suffix else "{0}-{1}".format(candidate.label, label_suffix)
    results = evaluator(candidate, tuple(cases))
    scorecard = score_results(label=label, cases=cases, results=results)
    layout.write_split_results(scorecard)
    return scorecard


def _promote(
    regression_log: Optional[RegressionLog],
    cases: Sequence[VerificationCase],
    scorecard: Scorecard,
    *,
    iteration: int,
) -> Tuple[str, ...]:
    if regression_log is None:
        return ()
    promoted = regression_log.promote(
        failed_cases(cases=cases, scorecard=scorecard),
        iteration=iteration,
    )
    return tuple(case.case_id for case in promoted)

