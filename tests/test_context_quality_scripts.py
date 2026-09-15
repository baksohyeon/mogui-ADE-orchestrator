from __future__ import annotations

import datetime as dt
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_BUDGET = REPO_ROOT / "master-ops" / "scripts" / "context-budget"
CONTEXT_LOG = REPO_ROOT / "master-ops" / "scripts" / "context-quality-log.sh"
CONTEXT_SAMPLER = REPO_ROOT / "master-ops" / "scripts" / "context-quality-sampler.sh"


def _run_budget(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTEXT_BUDGET), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _run_log(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(CONTEXT_LOG), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_sampler(*args: str, env: dict[str, str], cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(CONTEXT_SAMPLER), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_context_budget_default_glob_matches_dispatch_mangling():
    namespace = runpy.run_path(str(CONTEXT_BUDGET), run_name="context_budget_test")
    default_glob = namespace["default_glob"]
    assert default_glob("/a.b/c").endswith("/-a-b-c/*.jsonl")


def test_context_budget_reports_true_median_for_even_count(tmp_path: Path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for index, turn0 in enumerate((10, 20, 30, 40), start=1):
        session = sessions / f"session-{index}.jsonl"
        session.write_text(
            json.dumps({"message": {"usage": {"input_tokens": turn0}}}) + "\n",
            encoding="utf-8",
        )

    result = _run_budget("--glob", str(sessions / "*.jsonl"), "--limit", "4")
    assert result.returncode == 0, result.stderr
    assert "median 25" in result.stdout


def test_context_quality_log_summary_skips_non_object_lines(tmp_path: Path):
    ledger = tmp_path / "context-quality.jsonl"
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    ledger.write_text(
        "[]\n"
        + json.dumps(
            {
                "ts": ts,
                "session": "s-1",
                "event": "compact",
                "model": "m-1",
                "recall": {},
                "loss_notes": [],
                "proposed_succession": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CONTEXT_QUALITY_LOG"] = str(ledger)

    result = _run_log("--summary", env=env)
    assert result.returncode == 0, result.stderr
    assert "records: 1" in result.stdout
    assert "proposed_succession_true: 1" in result.stdout


def test_context_quality_log_accepts_proposed_succession_field(tmp_path: Path):
    ledger = tmp_path / "context-quality.jsonl"
    env = os.environ.copy()
    env["CONTEXT_QUALITY_LOG"] = str(ledger)
    payload = json.dumps(
        {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "session": "s-1",
            "event": "compact",
            "model": "m-1",
            "recall": {},
            "loss_notes": [],
            "proposed_succession": False,
        }
    )

    result = _run_log(payload, env=env)
    assert result.returncode == 0, result.stderr
    assert "appended:" in result.stdout


def test_context_quality_log_rejects_legacy_proposed_respawn_field(tmp_path: Path):
    ledger = tmp_path / "context-quality.jsonl"
    env = os.environ.copy()
    env["CONTEXT_QUALITY_LOG"] = str(ledger)
    payload = json.dumps(
        {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "session": "s-1",
            "event": "compact",
            "model": "m-1",
            "recall": {},
            "loss_notes": [],
            "proposed_respawn": False,
        }
    )

    result = _run_log(payload, env=env)
    assert result.returncode == 2
    assert "missing fields: proposed_succession" in result.stderr


def test_context_quality_sampler_normalizes_naive_closed_at(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    closed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    bd = fake_bin / "bd"
    bd.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"list\" ] && [ \"$2\" = \"--status=in_progress\" ] && [ \"$3\" = \"--json\" ]; then\n"
        "  printf '[]\\n'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"ready\" ] && [ \"$2\" = \"--json\" ]; then\n"
        "  printf '[]\\n'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"list\" ] && [ \"$2\" = \"--status=closed\" ] && [ \"$3\" = \"--json\" ]; then\n"
        f"  printf '[{{\"id\":\"closed-1\",\"priority\":1,\"title\":\"Closed item\",\"closed_at\":\"{closed_at}\"}}]\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    bd.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    result = _run_sampler(env=env)
    assert result.returncode == 0, result.stderr
    assert "## bd closed in last 24h\ncount: 1" in result.stdout


def test_context_quality_sampler_relative_anchor_git_log_works():
    env = os.environ.copy()
    env["CONTEXT_QUALITY_ANCHOR"] = "master-ops"
    result = _run_sampler(env=env)
    assert result.returncode == 0, result.stderr
    assert "## master-ops git log --oneline -5\nunavailable" not in result.stdout


def test_context_quality_sampler_no_python3_fallback_prints_notice(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "dirname").symlink_to("/usr/bin/dirname")
    (fake_bin / "basename").symlink_to("/usr/bin/basename")

    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    result = _run_sampler(env=env)
    assert result.returncode == 0, result.stderr
    assert "notice: bd unavailable; beads sections skipped" in result.stdout
