from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_runtime.core.acceptance.loop import read_candidate
from master_runtime.core.acceptance.models import CANDIDATE_FILENAME
from master_runtime.core.acceptance.proposer import (
    ProposerError,
    ProposerRequest,
    ProposerResult,
    build_proposer_argv,
    invoke_cli_proposer,
)


def test_build_argv_for_the_claude_cli() -> None:
    assert build_proposer_argv("claude", "fix the failures") == (
        "claude",
        "-p",
        "fix the failures",
    )


def test_build_argv_for_the_codex_cli_with_a_model() -> None:
    assert build_proposer_argv("codex", "fix it", model="gpt-5-codex") == (
        "codex",
        "exec",
        "--model",
        "gpt-5-codex",
        "fix it",
    )


def test_build_argv_for_the_cursor_agent_cli() -> None:
    assert build_proposer_argv("cursor-agent", "fix it") == (
        "cursor-agent",
        "-p",
        "--trust",
        "--force",
        "fix it",
    )


def test_build_argv_is_case_insensitive_on_runtime() -> None:
    assert build_proposer_argv("Claude", "fix it")[0] == "claude"


def test_build_argv_rejects_an_unsupported_runtime() -> None:
    with pytest.raises(ProposerError, match="unsupported proposer runtime"):
        build_proposer_argv("gemini", "fix it")


def test_build_argv_rejects_an_empty_prompt() -> None:
    with pytest.raises(ProposerError, match="prompt is empty"):
        build_proposer_argv("claude", "   ")


def test_prompt_is_passed_as_a_single_argv_element_never_a_shell_string() -> None:
    argv = build_proposer_argv("claude", "rm -rf / ; echo pwned")

    assert argv[-1] == "rm -rf / ; echo pwned"
    assert len(argv) == 3


def test_invoke_cli_proposer_uses_the_injected_runner(tmp_path: Path) -> None:
    seen = {}

    def runner(argv, cwd, timeout_seconds):
        seen["argv"] = tuple(argv)
        seen["cwd"] = cwd
        seen["timeout"] = timeout_seconds
        return ProposerResult(runtime=argv[0], argv=tuple(argv), returncode=0, stdout="done")

    result = invoke_cli_proposer(
        ProposerRequest(
            runtime="claude",
            prompt="fix it",
            cwd=tmp_path,
            timeout_seconds=42,
        ),
        runner=runner,
    )

    assert seen["argv"] == ("claude", "-p", "fix it")
    assert seen["cwd"] == str(tmp_path)
    assert seen["timeout"] == 42
    assert result.ok is True


def test_proposer_result_detail_prefers_stderr() -> None:
    result = ProposerResult(
        runtime="claude", argv=("claude",), returncode=1, stdout="out", stderr="boom"
    )

    assert result.ok is False
    assert result.detail() == "boom"


def test_read_candidate_returns_none_when_the_declaration_is_missing(tmp_path: Path) -> None:
    assert read_candidate(tmp_path, "iter-001") is None


def test_read_candidate_fails_closed_on_an_empty_surface_list(tmp_path: Path) -> None:
    (tmp_path / CANDIDATE_FILENAME).write_text(
        json.dumps({"surfaces": [], "summary": "nothing"}), encoding="utf-8"
    )

    assert read_candidate(tmp_path, "iter-001") is None


def test_read_candidate_fails_closed_on_invalid_json(tmp_path: Path) -> None:
    (tmp_path / CANDIDATE_FILENAME).write_text("{broken", encoding="utf-8")

    assert read_candidate(tmp_path, "iter-001") is None


def test_read_candidate_reads_declared_surfaces_and_summary(tmp_path: Path) -> None:
    (tmp_path / CANDIDATE_FILENAME).write_text(
        json.dumps({"surfaces": ["src/a.py", "src/b.py"], "summary": "widened guard"}),
        encoding="utf-8",
    )

    candidate = read_candidate(tmp_path, "iter-001")

    assert candidate is not None
    assert candidate.label == "iter-001"
    assert candidate.surfaces == ("src/a.py", "src/b.py")
    assert candidate.summary == "widened guard"
    assert candidate.changed is True


def test_read_candidate_falls_back_to_the_proposal_file_for_a_summary(tmp_path: Path) -> None:
    (tmp_path / CANDIDATE_FILENAME).write_text(
        json.dumps({"surfaces": ["src/a.py"]}), encoding="utf-8"
    )
    (tmp_path / "proposal.md").write_text("# Proposal\n\nwidened guard\n", encoding="utf-8")

    candidate = read_candidate(tmp_path, "iter-001")

    assert candidate is not None
    assert "widened guard" in candidate.summary
