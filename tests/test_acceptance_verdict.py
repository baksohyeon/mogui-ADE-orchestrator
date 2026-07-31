from __future__ import annotations

from master_runtime.core.acceptance.casebook import CaseSplit, VerificationCase
from master_runtime.core.acceptance.verdict import (
    MISSING_RESULT_DETAIL,
    AcceptanceReason,
    CaseResult,
    decide,
    failed_cases,
    score_results,
)


def _case(case_id: str, split: CaseSplit, stratum: str = "unit") -> VerificationCase:
    return VerificationCase(case_id=case_id, split=split, stratum=stratum)


CASES = (
    _case("t1", CaseSplit.TRAIN),
    _case("t2", CaseSplit.TRAIN, "io"),
    _case("h1", CaseSplit.HOLDOUT),
    _case("h2", CaseSplit.HOLDOUT, "io"),
)


def _result(case_id: str, split: CaseSplit, passed: bool) -> CaseResult:
    return CaseResult(case_id=case_id, split=split, stratum="unit", passed=passed)


def _scorecard(label: str, passing: set):
    return score_results(
        label=label,
        cases=CASES,
        results=[
            _result(case.case_id, case.split, case.case_id in passing) for case in CASES
        ],
    )


def test_score_results_counts_each_split_separately() -> None:
    scorecard = _scorecard("baseline", {"t1", "h1"})

    assert scorecard.split_score(CaseSplit.TRAIN).passed == 1
    assert scorecard.split_score(CaseSplit.TRAIN).total == 2
    assert scorecard.split_score(CaseSplit.HOLDOUT).failed_case_ids == ("h2",)
    assert scorecard.combined_passed() == 2
    assert scorecard.combined_total() == 4


def test_score_results_treats_a_missing_result_as_a_failure() -> None:
    scorecard = score_results(
        label="candidate",
        cases=CASES,
        results=[_result("t1", CaseSplit.TRAIN, True)],
    )

    assert scorecard.combined_passed() == 1
    missing = [result for result in scorecard.results if result.case_id == "h1"][0]
    assert missing.passed is False
    assert missing.detail == MISSING_RESULT_DETAIL


def test_score_results_takes_split_and_stratum_from_the_case_book() -> None:
    lying = CaseResult(
        case_id="h1", split=CaseSplit.TRAIN, stratum="spoofed", passed=True
    )

    scorecard = score_results(label="candidate", cases=CASES, results=[lying])

    recorded = [result for result in scorecard.results if result.case_id == "h1"][0]
    assert recorded.split == CaseSplit.HOLDOUT
    assert recorded.stratum == "unit"


def test_combined_pass_count_excludes_the_scorecard_split() -> None:
    cases = CASES + (_case("s1", CaseSplit.SCORECARD),)
    scorecard = score_results(
        label="candidate",
        cases=cases,
        results=[_result(case.case_id, case.split, True) for case in cases],
    )

    assert scorecard.combined_passed() == 4
    assert scorecard.split_score(CaseSplit.SCORECARD).passed == 1


def test_visible_failures_hide_the_private_split() -> None:
    scorecard = _scorecard("baseline", set())

    assert {result.case_id for result in scorecard.visible_failures()} == {"t1", "t2"}
    assert {result.case_id for result in scorecard.failed_results()} == {
        "t1",
        "t2",
        "h1",
        "h2",
    }


def test_decide_accepts_only_a_strict_combined_increase() -> None:
    verdict = decide(
        current=_scorecard("baseline", {"t1", "h1"}),
        candidate=_scorecard("iter-001", {"t1", "t2", "h1"}),
    )

    assert verdict.accepted is True
    assert verdict.reason == AcceptanceReason.PASS_COUNT_INCREASED
    assert verdict.delta == 1


def test_decide_rejects_an_equal_combined_count() -> None:
    verdict = decide(
        current=_scorecard("baseline", {"t1", "h1"}),
        candidate=_scorecard("iter-001", {"t1", "t2"}),
    )

    assert verdict.accepted is False
    assert verdict.reason == AcceptanceReason.NO_PASS_COUNT_INCREASE
    assert verdict.delta == 0


def test_decide_rejects_a_train_gain_paid_for_by_a_holdout_loss() -> None:
    current = _scorecard("baseline", {"t1", "h1", "h2"})
    candidate = _scorecard("iter-001", {"t1", "t2"})

    verdict = decide(current=current, candidate=candidate)

    assert candidate.split_score(CaseSplit.TRAIN).passed > current.split_score(
        CaseSplit.TRAIN
    ).passed
    assert verdict.accepted is False
    assert verdict.delta == -1


def test_decide_rejects_an_unchanged_candidate_even_when_it_scores_higher() -> None:
    verdict = decide(
        current=_scorecard("baseline", {"t1"}),
        candidate=_scorecard("iter-001", {"t1", "t2", "h1", "h2"}),
        candidate_changed=False,
    )

    assert verdict.accepted is False
    assert verdict.reason == AcceptanceReason.NO_CANDIDATE_CHANGE


def test_is_complete_only_when_every_gated_case_passes() -> None:
    assert _scorecard("candidate", {"t1", "t2", "h1", "h2"}).is_complete() is True
    assert _scorecard("candidate", {"t1", "t2", "h1"}).is_complete() is False


def test_failed_cases_maps_results_back_to_case_book_entries() -> None:
    scorecard = _scorecard("baseline", {"t1", "h1"})

    failed = failed_cases(cases=CASES, scorecard=scorecard)

    assert [case.case_id for case in failed] == ["t2", "h2"]
