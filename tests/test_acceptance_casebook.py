from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_runtime.core.acceptance.casebook import (
    VISIBLE_SPLITS,
    CaseBook,
    CaseBookError,
    CaseOrigin,
    CaseSplit,
    RegressionLog,
    VerificationCase,
    is_visible_split,
    load_casebook,
    normalize_split,
    read_casebook,
    render_split_markdown,
)


def _case(
    case_id: str,
    split: CaseSplit,
    stratum: str = "unit",
    origin: CaseOrigin = CaseOrigin.SEED,
) -> VerificationCase:
    return VerificationCase(
        case_id=case_id,
        split=split,
        stratum=stratum,
        command=("true",),
        origin=origin,
    )


def _valid_book() -> CaseBook:
    return CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN, "unit"),
            _case("t2", CaseSplit.TRAIN, "io"),
            _case("h1", CaseSplit.HOLDOUT, "unit"),
            _case("h2", CaseSplit.HOLDOUT, "io"),
        )
    )


def test_normalize_split_applies_aliases() -> None:
    assert normalize_split("visible") == CaseSplit.TRAIN
    assert normalize_split("private") == CaseSplit.HOLDOUT
    assert normalize_split("acceptance") == CaseSplit.SCORECARD
    assert normalize_split(CaseSplit.TRAIN) == CaseSplit.TRAIN


def test_normalize_split_rejects_unknown_value() -> None:
    with pytest.raises(CaseBookError):
        normalize_split("smoke")


def test_visible_and_private_partition_the_book() -> None:
    book = _valid_book()

    assert [case.case_id for case in book.visible_cases()] == ["t1", "t2"]
    assert [case.case_id for case in book.private_cases()] == ["h1", "h2"]
    assert [case.case_id for case in book.gated_cases()] == ["t1", "t2", "h1", "h2"]


def test_visible_manifest_never_exposes_holdout_case_ids() -> None:
    manifest = json.dumps(_valid_book().visible_manifest())

    assert "t1" in manifest
    assert "h1" not in manifest
    assert "h2" not in manifest


def test_validate_rejects_empty_book() -> None:
    with pytest.raises(CaseBookError):
        CaseBook().validate()


def test_validate_rejects_duplicate_case_ids() -> None:
    book = CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN),
            _case("t1", CaseSplit.HOLDOUT),
        )
    )

    with pytest.raises(CaseBookError, match="duplicate case_id"):
        book.validate()


def test_validate_requires_a_holdout_split() -> None:
    book = CaseBook(cases=(_case("t1", CaseSplit.TRAIN),))

    with pytest.raises(CaseBookError, match="holdout"):
        book.validate()


def test_validate_requires_matching_seed_strata() -> None:
    book = CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN, "unit"),
            _case("h1", CaseSplit.HOLDOUT, "io"),
        )
    )

    with pytest.raises(CaseBookError, match="same seed strata"):
        book.validate()


def test_validate_ignores_regression_cases_when_comparing_strata() -> None:
    book = _valid_book().with_cases(
        (_case("r1", CaseSplit.HOLDOUT, "adhoc", origin=CaseOrigin.REGRESSION),)
    )

    book.validate()


def test_with_cases_keeps_the_first_definition_of_a_case_id() -> None:
    book = _valid_book().with_cases((_case("t1", CaseSplit.HOLDOUT, "io"),))

    assert len(book.cases) == 4
    assert book.cases[0].split == CaseSplit.TRAIN


def test_load_casebook_reads_split_aliases_and_defaults_origin() -> None:
    book = load_casebook(
        {
            "cases": [
                {"case_id": "t1", "split": "visible", "stratum": "unit"},
                {"case_id": "h1", "split": "private", "stratum": "unit"},
            ]
        }
    )

    assert book.cases[0].split == CaseSplit.TRAIN
    assert book.cases[0].origin == CaseOrigin.SEED
    assert book.cases[1].split == CaseSplit.HOLDOUT


def test_load_casebook_rejects_a_case_without_a_stratum() -> None:
    with pytest.raises(CaseBookError, match="stratum"):
        load_casebook({"cases": [{"case_id": "t1", "split": "train"}]})


def test_read_casebook_reads_a_json_file(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {"cases": [{"case_id": "t1", "split": "train", "stratum": "unit"}]}
        ),
        encoding="utf-8",
    )

    assert read_casebook(path).case_ids() == ("t1",)


def test_read_casebook_fails_closed_on_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CaseBookError):
        read_casebook(path)


def test_regression_log_promotes_each_failure_once(tmp_path: Path) -> None:
    log = RegressionLog(tmp_path / "regressions.jsonl", clock=lambda: 1_000.0)
    failures = (_case("t2", CaseSplit.TRAIN, "io"), _case("h2", CaseSplit.HOLDOUT, "io"))

    first = log.promote(failures, iteration=1)
    second = log.promote(failures, iteration=2)

    assert [case.case_id for case in first] == ["t2", "h2"]
    assert second == ()
    lines = (tmp_path / "regressions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["origin"] == CaseOrigin.REGRESSION.value
    assert json.loads(lines[0])["iteration"] == 1


def test_regression_log_pins_a_dropped_case_back_as_private(tmp_path: Path) -> None:
    log = RegressionLog(tmp_path / "regressions.jsonl", clock=lambda: 1_000.0)
    log.promote((_case("t2", CaseSplit.TRAIN, "io"),), iteration=1)

    shrunk = CaseBook(
        cases=(
            _case("t1", CaseSplit.TRAIN, "unit"),
            _case("h1", CaseSplit.HOLDOUT, "unit"),
        )
    )
    merged = log.apply(shrunk)

    readmitted = [case for case in merged.cases if case.case_id == "t2"]
    assert len(readmitted) == 1
    assert readmitted[0].split == CaseSplit.HOLDOUT
    assert readmitted[0].origin == CaseOrigin.REGRESSION
    assert readmitted[0].command == ("true",)


def test_regression_log_keeps_the_configured_split_for_a_still_present_case(
    tmp_path: Path,
) -> None:
    log = RegressionLog(tmp_path / "regressions.jsonl", clock=lambda: 1_000.0)
    log.promote((_case("t2", CaseSplit.TRAIN, "io"),), iteration=1)

    merged = log.apply(_valid_book())

    kept = [case for case in merged.cases if case.case_id == "t2"]
    assert len(kept) == 1
    assert kept[0].split == CaseSplit.TRAIN


def test_regression_log_skips_unreadable_lines(tmp_path: Path) -> None:
    path = tmp_path / "regressions.jsonl"
    path.write_text('{"case_id": "t2", "split": "train", "stratum": "io"}\nnot json\n', encoding="utf-8")

    assert RegressionLog(path).cases()[0].case_id == "t2"


def test_render_split_markdown_labels_visibility() -> None:
    rendered = render_split_markdown(_valid_book())

    assert "## train (visible)" in rendered
    assert "## holdout (private)" in rendered


def test_is_visible_split_is_the_only_visibility_reader() -> None:
    assert is_visible_split(CaseSplit.TRAIN) is True
    assert is_visible_split(CaseSplit.HOLDOUT) is False
    assert is_visible_split(CaseSplit.SCORECARD) is False
    assert VISIBLE_SPLITS == frozenset({CaseSplit.TRAIN})


def test_case_visibility_follows_the_predicate(monkeypatch) -> None:
    import master_runtime.core.acceptance.casebook as casebook_module

    holdout_case = _case("h1", CaseSplit.HOLDOUT)
    assert holdout_case.is_visible is False

    monkeypatch.setattr(
        casebook_module,
        "VISIBLE_SPLITS",
        frozenset({CaseSplit.TRAIN, CaseSplit.HOLDOUT}),
    )

    assert holdout_case.is_visible is True


def test_visible_manifest_is_derived_from_the_visible_cases(monkeypatch) -> None:
    import master_runtime.core.acceptance.casebook as casebook_module

    book = _valid_book()
    assert set(book.visible_manifest()) == {"train"}

    monkeypatch.setattr(
        casebook_module,
        "VISIBLE_SPLITS",
        frozenset({CaseSplit.TRAIN, CaseSplit.HOLDOUT}),
    )

    assert set(book.visible_manifest()) == {"train", "holdout"}


def test_seed_strata_excludes_pinned_regressions() -> None:
    book = _valid_book().with_cases(
        (_case("r1", CaseSplit.HOLDOUT, "adhoc", origin=CaseOrigin.REGRESSION),)
    )

    assert book.seed_strata(CaseSplit.HOLDOUT) == frozenset({"unit", "io"})
