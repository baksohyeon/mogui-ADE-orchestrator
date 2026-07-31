from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import pytest

from master_runtime.core.acceptance.casebook import (
    CaseBook,
    CaseSplit,
    RegressionLog,
    VerificationCase,
)
from master_runtime.core.acceptance.layout import AcceptanceRunLayout
from master_runtime.core.acceptance.loop import cli_proposer, run_acceptance_loop
from master_runtime.core.acceptance.models import (
    BASELINE_LABEL,
    CANDIDATE_FILENAME,
    AcceptanceConfig,
    Candidate,
)
from master_runtime.core.acceptance.proposer import ProposerResult
from master_runtime.core.acceptance.verdict import AcceptanceReason, CaseResult


def _case(case_id: str, split: CaseSplit, stratum: str = "unit") -> VerificationCase:
    return VerificationCase(case_id=case_id, split=split, stratum=stratum)


def _book(extra: Sequence[VerificationCase] = ()) -> CaseBook:
    return CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN, "unit"),
            _case("t2", CaseSplit.TRAIN, "io"),
            _case("h1", CaseSplit.HOLDOUT, "unit"),
            _case("h2", CaseSplit.HOLDOUT, "io"),
        )
        + tuple(extra)
    )


def _config(tmp_path: Path, max_iterations: int = 1) -> AcceptanceConfig:
    return AcceptanceConfig(
        name="dz-bwh-demo",
        run_dir=tmp_path / "run",
        workspace_root=tmp_path / "workspace",
        max_iterations=max_iterations,
    )


def _evaluator(passing_by_label, calls: Optional[list] = None):
    def evaluate(candidate: Candidate, cases: Sequence[VerificationCase]):
        if calls is not None:
            calls.append((candidate.label, tuple(case.case_id for case in cases)))
        passing = passing_by_label[candidate.label]
        return tuple(
            CaseResult(
                case_id=case.case_id,
                split=case.split,
                stratum=case.stratum,
                passed=case.case_id in passing,
                detail="" if case.case_id in passing else "assertion failed",
            )
            for case in cases
        )

    return evaluate


def _proposer(candidates: Sequence[Optional[Candidate]]):
    remaining = list(candidates)

    def propose(context):
        del context
        if not remaining:
            return None
        return remaining.pop(0)

    return propose


def _candidate(label: str = "iter-001") -> Candidate:
    return Candidate(
        label=label,
        ref="refs/candidates/{0}".format(label),
        surfaces=("src/target.py",),
        summary="widened the guard",
    )


def test_loop_accepts_a_candidate_that_increases_the_combined_pass_count(
    tmp_path: Path,
) -> None:
    report = run_acceptance_loop(
        config=_config(tmp_path),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator(
            {BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2", "h1"}}
        ),
    )

    assert report.final.label == "iter-001"
    assert report.accepted_count == 1
    assert report.iterations[0].verdict.reason == AcceptanceReason.PASS_COUNT_INCREASED
    assert report.final_score.combined_passed() == 3


def test_loop_rejects_a_candidate_that_trades_holdout_for_train(tmp_path: Path) -> None:
    report = run_acceptance_loop(
        config=_config(tmp_path),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2"}}),
    )

    assert report.final.label == BASELINE_LABEL
    assert report.accepted_count == 0
    verdict = report.iterations[0].verdict
    assert verdict.reason == AcceptanceReason.NO_PASS_COUNT_INCREASE
    assert verdict.delta == 0


def test_decision_json_records_the_audit_fields(tmp_path: Path) -> None:
    config = _config(tmp_path)

    run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1"}, "iter-001": {"t1", "t2", "h1"}}),
    )

    decision_path = (
        Path(config.run_dir) / "history" / "visible" / "iterations" / "001" / "decision.json"
    )
    payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "accepted"
    assert payload["reason"] == AcceptanceReason.PASS_COUNT_INCREASED.value
    assert payload["changed_surfaces"] == ["src/target.py"]
    assert payload["starting_label"] == BASELINE_LABEL
    assert payload["candidate_label"] == "iter-001"
    assert payload["current_combined"] == 1
    assert payload["candidate_combined"] == 3
    assert payload["delta"] == 2
    assert (decision_path.parent / "decision.md").exists()


def test_private_holdout_never_reaches_the_proposer_workspace(tmp_path: Path) -> None:
    config = _config(tmp_path)

    run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator({BASELINE_LABEL: set(), "iter-001": {"t1"}}),
    )

    workspace = (
        Path(config.run_dir)
        / "history"
        / "visible"
        / "iterations"
        / "001"
        / "proposer_workspace"
    )
    leaked = [
        path
        for path in workspace.rglob("*")
        if path.is_file()
        and any(marker in path.read_text(encoding="utf-8") for marker in ("h1", "h2"))
    ]
    assert leaked == []
    assert "t1" in (workspace / "task.md").read_text(encoding="utf-8")


def test_split_artifacts_are_routed_by_visibility(tmp_path: Path) -> None:
    config = _config(tmp_path)

    run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([None]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1"}}),
    )

    run_dir = Path(config.run_dir)
    assert (run_dir / "history" / "visible" / "train" / BASELINE_LABEL / "result.json").exists()
    assert (run_dir / "history" / "private" / "holdout" / BASELINE_LABEL / "result.json").exists()
    assert not (run_dir / "history" / "visible" / "holdout").exists()


def test_loop_stops_when_the_proposer_returns_no_candidate(tmp_path: Path) -> None:
    report = run_acceptance_loop(
        config=_config(tmp_path, max_iterations=3),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([None]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1"}}),
    )

    assert len(report.iterations) == 1
    assert report.iterations[0].candidate is None
    assert report.iterations[0].verdict is None


def test_loop_stops_when_the_proposer_declares_no_changed_surface(tmp_path: Path) -> None:
    empty = Candidate(label="iter-001", surfaces=())

    report = run_acceptance_loop(
        config=_config(tmp_path, max_iterations=3),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([empty]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1"}}),
    )

    assert len(report.iterations) == 1
    assert report.iterations[0].candidate is None


def test_loop_runs_no_iteration_when_the_baseline_already_passes(tmp_path: Path) -> None:
    calls: list = []

    report = run_acceptance_loop(
        config=_config(tmp_path, max_iterations=3),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "t2", "h1", "h2"}}, calls=calls),
    )

    assert report.iterations == ()
    assert len(calls) == 1


def test_a_rejected_candidate_is_retried_after_the_restore_hook(tmp_path: Path) -> None:
    restored: list = []

    report = run_acceptance_loop(
        config=_config(tmp_path, max_iterations=2),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate("iter-001"), _candidate("iter-002")]),
        evaluator=_evaluator(
            {
                BASELINE_LABEL: {"t1", "h1"},
                "iter-001": {"t1", "t2"},
                "iter-002": {"t1", "t2", "h1"},
            }
        ),
        on_reject=lambda candidate: restored.append(candidate.label),
    )

    assert restored == ["iter-001"]
    assert report.final.label == "iter-002"
    assert report.accepted_count == 1


def test_every_observed_failure_is_pinned_into_the_regression_log(tmp_path: Path) -> None:
    log = RegressionLog(tmp_path / "regressions.jsonl", clock=lambda: 1_000.0)

    report = run_acceptance_loop(
        config=_config(tmp_path),
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator(
            {BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2", "h1"}}
        ),
        regression_log=log,
    )

    assert {case.case_id for case in log.cases()} == {"t2", "h2"}
    assert report.iterations[0].promoted_regressions == ()


def test_a_case_dropped_from_the_book_returns_as_a_private_regression(
    tmp_path: Path,
) -> None:
    log = RegressionLog(tmp_path / "regressions.jsonl", clock=lambda: 1_000.0)
    log.promote((_case("t2", CaseSplit.TRAIN, "io"),), iteration=1)
    shrunk = CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN, "unit"),
            _case("h1", CaseSplit.HOLDOUT, "unit"),
        )
    )
    calls: list = []

    run_acceptance_loop(
        config=_config(tmp_path),
        casebook=shrunk,
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([None]),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1", "t2"}}, calls=calls),
        regression_log=log,
    )

    evaluated = calls[0][1]
    assert "t2" in evaluated
    manifest = json.loads((Path(tmp_path / "run") / "split.json").read_text(encoding="utf-8"))
    holdout_ids = {case["case_id"] for case in manifest["holdout"]}
    assert "t2" in holdout_ids


def test_scorecard_runs_only_for_the_baseline_and_the_final_candidate(
    tmp_path: Path,
) -> None:
    calls: list = []
    book = _book((_case("s1", CaseSplit.SCORECARD, "unit"),))

    run_acceptance_loop(
        config=_config(tmp_path),
        casebook=book,
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator(
            {BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2", "h1"}}, calls=calls
        ),
    )

    scorecard_calls = [call for call in calls if call[1] == ("s1",)]
    gated_calls = [call for call in calls if "t1" in call[1]]
    assert [call[0] for call in scorecard_calls] == [BASELINE_LABEL, "iter-001"]
    assert len(gated_calls) == 2
    for call in gated_calls:
        assert "s1" not in call[1]


def test_report_and_manifest_files_are_written(tmp_path: Path) -> None:
    config = _config(tmp_path)

    report = run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=_proposer([_candidate()]),
        evaluator=_evaluator(
            {BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2", "h1"}}
        ),
    )

    run_dir = Path(config.run_dir)
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "split.json").exists()
    assert (run_dir / "split.md").exists()
    assert json.loads((run_dir / "report.json").read_text(encoding="utf-8"))["final"][
        "label"
    ] == "iter-001"
    markdown = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Acceptance Report: dz-bwh-demo" in markdown
    assert "| train |" in markdown
    assert report.to_markdown() == markdown


def test_loop_rejects_a_max_iterations_below_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        run_acceptance_loop(
            config=_config(tmp_path, max_iterations=0),
            casebook=_book(),
            baseline=Candidate(label=BASELINE_LABEL),
            proposer=_proposer([]),
            evaluator=_evaluator({BASELINE_LABEL: set()}),
        )


def test_loop_rejects_an_invalid_case_book(tmp_path: Path) -> None:
    from master_runtime.core.acceptance.casebook import CaseBookError

    with pytest.raises(CaseBookError):
        run_acceptance_loop(
            config=_config(tmp_path),
            casebook=CaseBook(cases=(_case("t1", CaseSplit.TRAIN),)),
            baseline=Candidate(label=BASELINE_LABEL),
            proposer=_proposer([]),
            evaluator=_evaluator({BASELINE_LABEL: set()}),
        )


def test_cli_proposer_goes_through_the_single_invocation_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    seen: list = []

    def fake_invoke(request, runner=None):
        del runner
        seen.append(request)
        workspace = (
            Path(config.run_dir)
            / "history"
            / "visible"
            / "iterations"
            / "001"
            / "proposer_workspace"
        )
        (workspace / CANDIDATE_FILENAME).write_text(
            json.dumps({"surfaces": ["src/target.py"], "summary": "seam"}),
            encoding="utf-8",
        )
        return ProposerResult(
            runtime=request.runtime, argv=("claude", "-p", "..."), returncode=0
        )

    monkeypatch.setattr(
        "master_runtime.core.acceptance.loop.invoke_cli_proposer", fake_invoke
    )

    report = run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=cli_proposer(config),
        evaluator=_evaluator(
            {BASELINE_LABEL: {"t1", "h1"}, "iter-001": {"t1", "t2", "h1"}}
        ),
    )

    assert len(seen) == 1
    assert seen[0].runtime == "claude"
    assert "Candidate Proposal Task" in seen[0].prompt
    assert report.final.label == "iter-001"
    assert report.final.summary == "seam"
    workspace = (
        Path(config.run_dir)
        / "history"
        / "visible"
        / "iterations"
        / "001"
        / "proposer_workspace"
    )
    assert json.loads((workspace / "proposer_result.json").read_text(encoding="utf-8"))[
        "ok"
    ] is True


def test_cli_proposer_produces_no_candidate_when_the_cli_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    def fake_invoke(request, runner=None):
        del runner
        return ProposerResult(
            runtime=request.runtime,
            argv=("claude",),
            returncode=1,
            stderr="quota exhausted",
        )

    monkeypatch.setattr(
        "master_runtime.core.acceptance.loop.invoke_cli_proposer", fake_invoke
    )

    report = run_acceptance_loop(
        config=config,
        casebook=_book(),
        baseline=Candidate(label=BASELINE_LABEL),
        proposer=cli_proposer(config),
        evaluator=_evaluator({BASELINE_LABEL: {"t1", "h1"}}),
    )

    assert report.iterations[0].candidate is None
    assert report.final.label == BASELINE_LABEL


def test_layout_keeps_private_results_outside_the_visible_root(tmp_path: Path) -> None:
    layout = AcceptanceRunLayout(tmp_path / "run")

    train_dir = layout.split_dir(label=BASELINE_LABEL, split=CaseSplit.TRAIN)
    holdout_dir = layout.split_dir(label=BASELINE_LABEL, split=CaseSplit.HOLDOUT)
    scorecard_dir = layout.split_dir(label=BASELINE_LABEL, split=CaseSplit.SCORECARD)

    assert layout.visible_root in train_dir.parents
    assert layout.private_root in holdout_dir.parents
    assert layout.private_root in scorecard_dir.parents
