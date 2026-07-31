from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from master_runtime.core.acceptance.process import (
    NOT_FOUND_RETURNCODE,
    TIMEOUT_RETURNCODE,
    ProcessResult,
    resolve_runner,
    run_process,
)


def test_run_process_reports_a_clean_exit(tmp_path: Path) -> None:
    result = run_process(["true"], tmp_path)

    assert result.ok is True
    assert result.returncode == 0
    assert result.argv == ("true",)


def test_run_process_reports_a_non_zero_exit(tmp_path: Path) -> None:
    result = run_process(["false"], tmp_path)

    assert result.ok is False
    assert result.returncode != 0


def test_run_process_maps_a_missing_binary_onto_an_exit_code(tmp_path: Path) -> None:
    result = run_process(["mogui-no-such-binary"], tmp_path)

    assert result.returncode == NOT_FOUND_RETURNCODE
    assert result.tail()


def test_run_process_maps_a_timeout_onto_an_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_process(["sleep", "60"], tmp_path, timeout_seconds=1)

    assert result.returncode == TIMEOUT_RETURNCODE
    assert "timed out after 1s" in result.stderr


def test_run_process_captures_stdout(tmp_path: Path) -> None:
    result = run_process(["echo", "hello"], tmp_path)

    assert result.tail() == "hello"


def test_tail_prefers_stderr_and_skips_trailing_blank_lines() -> None:
    result = ProcessResult(
        argv=("x",), returncode=1, stdout="out line\n", stderr="boom\n\n\n"
    )

    assert result.tail() == "boom"


def test_tail_returns_the_last_line_of_a_multi_line_buffer() -> None:
    result = ProcessResult(argv=("x",), returncode=1, stdout="first\nsecond\nthird\n")

    assert result.tail() == "third"


def test_tail_is_empty_for_a_silent_process() -> None:
    assert ProcessResult(argv=("x",), returncode=0).tail() == ""


def test_resolve_runner_returns_the_injected_runner() -> None:
    def runner(argv, cwd, timeout_seconds):
        return ProcessResult(argv=tuple(argv), returncode=0)

    assert resolve_runner(runner) is runner
    assert resolve_runner(None) is run_process


def test_process_result_serializes_the_command_it_ran() -> None:
    payload = ProcessResult(argv=("a", "b"), returncode=2).to_dict()

    assert payload == {"argv": ["a", "b"], "returncode": 2, "ok": False}
