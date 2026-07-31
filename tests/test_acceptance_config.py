from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_runtime.core.acceptance.casebook import CaseSplit
from master_runtime.core.acceptance.config import (
    AcceptanceConfigError,
    load_acceptance_config,
)
from master_runtime.core.acceptance.evaluators import command_evaluator
from master_runtime.core.acceptance.models import Candidate
from master_runtime.core.acceptance.verdict import score_results


def _payload(**overrides) -> dict:
    payload = {
        "name": "dz-bwh-demo",
        "workspace_root": "workspace",
        "run_dir": "run",
        "max_iterations": 2,
        "proposer": {"runtime": "codex", "model": "gpt-5-codex", "timeout_seconds": 60},
        "cases": [
            {"case_id": "t1", "split": "train", "stratum": "unit", "command": ["true"]},
            {"case_id": "h1", "split": "holdout", "stratum": "unit", "command": ["true"]},
        ],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_resolves_paths_against_the_config_file(tmp_path: Path) -> None:
    loaded = load_acceptance_config(_write(tmp_path, _payload()))

    assert Path(loaded.config.workspace_root) == (tmp_path / "workspace").resolve()
    assert Path(loaded.config.run_dir) == (tmp_path / "run").resolve()
    assert loaded.config.max_iterations == 2
    assert loaded.config.proposer_runtime == "codex"
    assert loaded.config.proposer_model == "gpt-5-codex"
    assert loaded.config.proposer_timeout_seconds == 60
    assert loaded.casebook.case_ids() == ("t1", "h1")
    assert loaded.regression_log is None


def test_load_wires_an_optional_regression_log(tmp_path: Path) -> None:
    loaded = load_acceptance_config(
        _write(tmp_path, _payload(regression_log="state/regressions.jsonl"))
    )

    assert loaded.regression_log is not None
    assert loaded.regression_log.path == (tmp_path / "state" / "regressions.jsonl").resolve()


def test_load_rejects_an_unsupported_proposer_runtime(tmp_path: Path) -> None:
    path = _write(tmp_path, _payload(proposer={"runtime": "gemini"}))

    with pytest.raises(AcceptanceConfigError, match="unsupported proposer runtime"):
        load_acceptance_config(path)


def test_load_rejects_a_missing_name(tmp_path: Path) -> None:
    payload = _payload()
    payload.pop("name")

    with pytest.raises(AcceptanceConfigError, match="name"):
        load_acceptance_config(_write(tmp_path, payload))


def test_load_rejects_a_non_positive_max_iterations(tmp_path: Path) -> None:
    with pytest.raises(AcceptanceConfigError, match="max_iterations"):
        load_acceptance_config(_write(tmp_path, _payload(max_iterations=0)))


def test_load_validates_the_case_book(tmp_path: Path) -> None:
    from master_runtime.core.acceptance.casebook import CaseBookError

    payload = _payload(
        cases=[{"case_id": "t1", "split": "train", "stratum": "unit"}]
    )

    with pytest.raises(CaseBookError, match="holdout"):
        load_acceptance_config(_write(tmp_path, payload))


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "acceptance.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(AcceptanceConfigError, match="invalid config JSON"):
        load_acceptance_config(path)


def test_command_evaluator_maps_exit_codes_to_pass_and_fail(tmp_path: Path) -> None:
    loaded = load_acceptance_config(
        _write(
            tmp_path,
            _payload(
                cases=[
                    {
                        "case_id": "t1",
                        "split": "train",
                        "stratum": "unit",
                        "command": ["true"],
                    },
                    {
                        "case_id": "h1",
                        "split": "holdout",
                        "stratum": "unit",
                        "command": ["false"],
                    },
                ]
            ),
        )
    )
    (tmp_path / "workspace").mkdir()

    evaluate = command_evaluator(loaded.config.workspace_root)
    results = evaluate(Candidate(label="baseline"), loaded.casebook.gated_cases())
    scorecard = score_results(
        label="baseline", cases=loaded.casebook.gated_cases(), results=results
    )

    assert scorecard.split_score(CaseSplit.TRAIN).passed == 1
    assert scorecard.split_score(CaseSplit.HOLDOUT).passed == 0
    assert scorecard.combined_passed() == 1


def test_command_evaluator_fails_closed_on_a_case_without_a_command(
    tmp_path: Path,
) -> None:
    loaded = load_acceptance_config(_write(tmp_path, _payload(
        cases=[
            {"case_id": "t1", "split": "train", "stratum": "unit"},
            {"case_id": "h1", "split": "holdout", "stratum": "unit"},
        ]
    )))
    (tmp_path / "workspace").mkdir()

    evaluate = command_evaluator(loaded.config.workspace_root)
    results = evaluate(Candidate(label="baseline"), loaded.casebook.gated_cases())

    assert all(result.passed is False for result in results)
    assert results[0].detail == "case has no command"


def test_command_evaluator_reports_a_missing_binary_as_a_failure(tmp_path: Path) -> None:
    loaded = load_acceptance_config(
        _write(
            tmp_path,
            _payload(
                cases=[
                    {
                        "case_id": "t1",
                        "split": "train",
                        "stratum": "unit",
                        "command": ["mogui-no-such-binary"],
                    },
                    {
                        "case_id": "h1",
                        "split": "holdout",
                        "stratum": "unit",
                        "command": ["true"],
                    },
                ]
            ),
        )
    )
    (tmp_path / "workspace").mkdir()

    evaluate = command_evaluator(loaded.config.workspace_root)
    results = evaluate(Candidate(label="baseline"), loaded.casebook.gated_cases())

    assert results[0].passed is False
    assert results[0].detail
