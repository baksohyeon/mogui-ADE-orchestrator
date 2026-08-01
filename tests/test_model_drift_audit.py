from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "model-drift-audit"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_single_model_session_reports_no_transition() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_single.jsonl"))

    assert result.returncode == 0
    assert "no transition" in result.stdout
    assert "claude-fable-5=3" in result.stdout


def test_midsession_switch_is_found_even_when_the_tail_is_homogeneous() -> None:
    """The failure this script exists for.

    The last ten turns are all one model, so a tail sample reports a clean
    session. The switch happened before that window.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_midsession.jsonl"))

    assert result.returncode == 1
    assert "transitions: 1" in result.stdout
    assert "claude-fable-5 -> claude-opus-5" in result.stdout


def test_expected_model_mismatch_fails_even_without_a_transition() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_single.jsonl"),
        "--expect",
        "claude-opus-5",
    )

    assert result.returncode == 1
    assert "MISMATCH" in result.stdout


def test_expected_model_match_passes() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_single.jsonl"),
        "--expect",
        "claude-fable-5",
    )

    assert result.returncode == 0
    assert "match" in result.stdout


def test_ignore_synthetic_keeps_the_transition_it_bridges() -> None:
    """Dropping synthetic turns must not drop the change across them.

    A -> synthetic -> B is an A -> B change once the synthetic turns are
    removed. Erasing the transition along with the turns is how the original
    drift went unnoticed.
    """
    fixture = str(FIXTURES / "model_drift_audit_synthetic_bridge.jsonl")

    with_synthetic = run("--transcript", fixture)
    without_synthetic = run("--transcript", fixture, "--ignore-synthetic")

    assert with_synthetic.returncode == 1
    assert without_synthetic.returncode == 1
    assert "claude-fable-5 -> claude-opus-5" in without_synthetic.stdout


def test_zero_assistant_turns_is_undecidable_not_clean() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_no_assistant.jsonl"))

    assert result.returncode == 2
    assert "undecidable" in result.stderr


def test_missing_transcript_is_undecidable_not_clean() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_does_not_exist.jsonl"))

    assert result.returncode == 2
    assert "no transcript found" in result.stderr


def test_json_output_carries_transitions_and_counts() -> None:
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_midsession.jsonl"),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["drift"] is True
    assert payload["counts"]["claude-fable-5"] == 2
    assert payload["counts"]["claude-opus-5"] == 10
    assert payload["transitions"][0]["from"] == "claude-fable-5"
    assert payload["transitions"][0]["to"] == "claude-opus-5"


def test_no_expected_model_is_baked_in() -> None:
    """A default expectation would assert one installation's policy as everyone's."""
    result = run("--transcript", str(FIXTURES / "model_drift_audit_single.jsonl"))

    assert result.returncode == 0
    assert "expected" not in result.stdout


def test_all_synthetic_session_is_undecidable_not_a_match() -> None:
    """No real model was ever observed, so there is nothing to match against.

    Counting synthetic turns as evidence would report "expected X: match" for a
    session where X never appeared. That is the failure this whole script was
    written to refuse.
    """
    result = run(
        "--transcript",
        str(FIXTURES / "model_drift_audit_all_synthetic.jsonl"),
        "--expect",
        "claude-opus-5",
    )

    assert result.returncode == 2
    assert "no real model observed" in result.stderr
    assert "match" not in result.stdout


def test_malformed_lines_are_skipped_rather_than_raising() -> None:
    """A transcript may be mid-write, and a line can be JSON without being an object.

    An uncaught exception exits 1, and 1 already means "transition found", so a
    crash here would be indistinguishable from a real verdict.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_malformed_lines.jsonl"))

    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert "claude-fable-5=2" in result.stdout


def test_missing_timestamp_degrades_to_a_placeholder() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_no_timestamp.jsonl"))

    assert result.returncode == 0
    assert "claude-fable-5=1" in result.stdout


def test_json_expect_mismatch_field_tracks_the_expectation() -> None:
    """The JSON payload is the machine contract and needs its own coverage.

    Asserting only on the text output lets the JSON field rot silently.
    """
    fixture = str(FIXTURES / "model_drift_audit_single.jsonl")

    mismatched = json.loads(run("--transcript", fixture, "--json", "--expect", "other").stdout)
    matched = json.loads(
        run("--transcript", fixture, "--json", "--expect", "claude-fable-5").stdout
    )

    assert mismatched["expect_mismatch"] is True
    assert matched["expect_mismatch"] is False


def test_json_transitions_honour_ignore_synthetic() -> None:
    """--ignore-synthetic has to mean the same thing in both output modes.

    The unfiltered sequence is still available, under a key that says so.
    """
    fixture = str(FIXTURES / "model_drift_audit_synthetic_bridge.jsonl")

    payload = json.loads(run("--transcript", fixture, "--json", "--ignore-synthetic").stdout)

    assert [(t["from"], t["to"]) for t in payload["transitions"]] == [
        ("claude-fable-5", "claude-opus-5")
    ]
    assert len(payload["transitions_including_synthetic"]) == 2


def test_session_lookup_resolves_under_the_given_projects_dir(tmp_path) -> None:
    projects = tmp_path / "projects"
    (projects / "workspace-a").mkdir(parents=True)
    target = projects / "workspace-a" / "sess-1.jsonl"
    target.write_bytes((FIXTURES / "model_drift_audit_single.jsonl").read_bytes())

    result = run("--projects-dir", str(projects), "--session", "sess-1")

    assert result.returncode == 0
    assert "sess-1.jsonl" in result.stdout


def test_session_id_cannot_escape_the_projects_dir(tmp_path) -> None:
    """The session id is interpolated into a path, so separators are stripped."""
    projects = tmp_path / "projects"
    (projects / "workspace-a").mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes((FIXTURES / "model_drift_audit_single.jsonl").read_bytes())

    result = run("--projects-dir", str(projects), "--session", "../../outside")

    assert result.returncode == 2
    assert "no transcript found" in result.stderr


def test_workspace_lookup_picks_the_most_recent_transcript(tmp_path) -> None:
    projects = tmp_path / "projects"
    workspace = projects / "workspace-a"
    workspace.mkdir(parents=True)
    older = workspace / "older.jsonl"
    newer = workspace / "newer.jsonl"
    older.write_bytes((FIXTURES / "model_drift_audit_single.jsonl").read_bytes())
    newer.write_bytes((FIXTURES / "model_drift_audit_midsession.jsonl").read_bytes())
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))

    result = run("--projects-dir", str(projects), "--workspace-dir", "workspace-a")

    assert result.returncode == 1
    assert "newer.jsonl" in result.stdout


def test_assistant_turn_without_a_model_is_recorded_not_dropped() -> None:
    """A turn whose model cannot be read is still a turn.

    Dropping it exits 0 with "no transition" for a session that may have
    changed model inside exactly those turns. It is carried as <missing> so the
    gap appears in the sequence.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_missing_model.jsonl"))

    assert result.returncode == 1
    assert "<missing>" in result.stdout
    assert "claude-fable-5 -> <missing>" in result.stdout


def test_all_missing_session_is_undecidable() -> None:
    result = run("--transcript", str(FIXTURES / "model_drift_audit_all_missing.jsonl"))

    assert result.returncode == 2
    assert "no real model observed" in result.stderr


def test_flat_assistant_shape_is_read_like_the_sibling_probe() -> None:
    """Two tools reading one transcript must agree on which turns exist.

    model-identity-probe accepts a top-level role field and nested message,
    item, payload, and response objects. Requiring only a top-level type field
    would report zero assistant turns for a transcript the sibling reads fine.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_flat_shape.jsonl"))

    assert result.returncode == 1
    assert "claude-fable-5 -> claude-opus-5" in result.stdout


def test_invalid_utf8_is_undecidable_not_drift() -> None:
    """UnicodeDecodeError is a ValueError, so catching OSError alone misses it.

    An uncaught one exits 1, which callers read as a transition found.
    """
    result = run("--transcript", str(FIXTURES / "model_drift_audit_invalid_utf8.jsonl"))

    assert result.returncode == 2
    assert "cannot read transcript" in result.stderr


def test_unreadable_lookup_candidate_is_skipped(tmp_path) -> None:
    """A glob hit can be a dangling symlink, and stat on it raises.

    Outside the read guard, that exits 1 and looks like drift.
    """
    projects = tmp_path / "projects"
    workspace = projects / "workspace-a"
    workspace.mkdir(parents=True)
    (workspace / "dead.jsonl").symlink_to(tmp_path / "nothing-here.jsonl")

    result = run("--projects-dir", str(projects), "--workspace-dir", "workspace-a")

    assert result.returncode == 2
    assert "no transcript found" in result.stderr


def test_readable_candidate_still_wins_over_an_unreadable_one(tmp_path) -> None:
    projects = tmp_path / "projects"
    workspace = projects / "workspace-a"
    workspace.mkdir(parents=True)
    (workspace / "dead.jsonl").symlink_to(tmp_path / "nothing-here.jsonl")
    good = workspace / "good.jsonl"
    good.write_bytes((FIXTURES / "model_drift_audit_single.jsonl").read_bytes())

    result = run("--projects-dir", str(projects), "--workspace-dir", "workspace-a")

    assert result.returncode == 0
    assert "good.jsonl" in result.stdout


def test_lookup_without_a_projects_dir_is_undecidable() -> None:
    """No host layout is assumed, so a bare --session cannot resolve to anything."""
    result = run("--session", "sess-1")

    assert result.returncode == 2
    assert "no transcript found" in result.stderr
