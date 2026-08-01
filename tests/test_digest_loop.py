from __future__ import annotations

import io
import json
from pathlib import Path

from master_runtime.core.digest_loop import (
    DigestConfig,
    JobObservation,
    JobStatus,
    RepoObservation,
    Snapshot,
    TriageClassification,
    baseline_with_expected_updates,
    build_digest_report,
    cli_main,
    render_digest,
    suggest_next_interval_seconds,
    triage_snapshot,
    _classify_job_log,
    _collect_jobs,
)


def test_echo_repo_drift_is_classified_from_ledger_tail() -> None:
    snapshot = Snapshot(
        repos=(
            RepoObservation(name="app", path="/work/app", head="new-head", dirty=False),
        ),
        ledger_entries=(
            {
                "decision": "ALLOW",
                "job_id": "job-1",
                "repo": "app",
                "new_head": "new-head",
            },
        ),
    )
    baseline = {
        "repos": {
            "app": {"path": "/work/app", "head": "old-head", "dirty": False},
        }
    }

    result = triage_snapshot(snapshot, baseline)

    assert [item.classification for item in result.items] == [
        TriageClassification.ECHO,
    ]
    assert result.has_unexplained is False


def test_expected_repo_drift_updates_baseline_target() -> None:
    snapshot = Snapshot(
        repos=(
            RepoObservation(name="app", path="/work/app", head="new-head", dirty=False),
        )
    )
    baseline = {
        "repos": {
            "app": {"path": "/work/app", "head": "old-head", "dirty": False},
        },
        "expected": {
            "repos": {
                "app": {"path": "/work/app", "head": "new-head", "dirty": False},
            }
        },
    }

    result = triage_snapshot(snapshot, baseline)
    updated = baseline_with_expected_updates(baseline, result)

    assert [item.classification for item in result.items] == [
        TriageClassification.EXPECTED,
    ]
    assert updated["repos"]["app"]["head"] == "new-head"
    assert "app" not in updated["expected"]["repos"]


def test_unexplained_repo_drift_is_reported_without_baseline_update() -> None:
    snapshot = Snapshot(
        repos=(
            RepoObservation(name="app", path="/work/app", head="new-head", dirty=False),
        )
    )
    baseline = {
        "repos": {
            "app": {"path": "/work/app", "head": "old-head", "dirty": False},
        }
    }

    result = triage_snapshot(snapshot, baseline)
    updated = baseline_with_expected_updates(baseline, result)

    assert [item.classification for item in result.items] == [
        TriageClassification.UNEXPLAINED,
    ]
    assert result.has_unexplained is True
    assert updated["repos"]["app"]["head"] == "old-head"


def test_cli_tick_returns_exit_4_for_unexplained_and_writes_digest(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    digest_dir = tmp_path / "digests"
    config_path = tmp_path / "config.json"
    baseline_path.write_text(
        json.dumps(
            {
                "repos": {
                    "app": {
                        "path": "/work/app",
                        "head": "old-head",
                        "dirty": False,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "repos": [],
                "ledger_path": str(tmp_path / "ledger.jsonl"),
                "job_log_globs": [],
                "monitor_pgrep_patterns": [],
                "baseline_path": str(baseline_path),
                "digest_dir": str(digest_dir),
            }
        ),
        encoding="utf-8",
    )
    snapshot = Snapshot(
        repos=(
            RepoObservation(name="app", path="/work/app", head="new-head", dirty=False),
        )
    )
    stdout = io.StringIO()

    code = cli_main(
        ["tick", "--config", str(config_path)],
        collect_fn=lambda config: snapshot,
        stdout=stdout,
        now=lambda: 1_000.0,
    )

    digest_path = digest_dir / "l1-digest-1000.md"
    assert code == 4
    assert "## Unexplained" in stdout.getvalue()
    assert digest_path.read_text(encoding="utf-8") == stdout.getvalue()
    assert json.loads(baseline_path.read_text(encoding="utf-8"))["repos"]["app"][
        "head"
    ] == "old-head"


def test_digest_section_order_is_stop_reading_friendly() -> None:
    snapshot = Snapshot(
        repos=(
            RepoObservation(name="app", path="/work/app", head="new-head", dirty=False),
        ),
        jobs=(JobObservation(name="worker.log", path="/logs/worker.log", status=JobStatus.RUNNING),),
    )
    baseline = {
        "repos": {
            "app": {"path": "/work/app", "head": "old-head", "dirty": False},
        }
    }

    report = build_digest_report(snapshot, baseline, generated_at=1_000.0)
    digest = render_digest(report)

    assert digest.index("## Unexplained") < digest.index("## Job Status")
    assert digest.index("## Job Status") < digest.index("## Repo Drift")
    assert digest.index("## Repo Drift") < digest.index("## Ledger Summary")
    assert digest.index("## Ledger Summary") < digest.index("## Next Observation Interval")


def test_pace_is_short_with_active_jobs_and_long_when_idle() -> None:
    active = Snapshot(
        jobs=(
            JobObservation(name="worker.log", path="/logs/worker.log", status=JobStatus.RUNNING),
        )
    )
    idle = Snapshot()

    assert suggest_next_interval_seconds(active) == 600
    assert suggest_next_interval_seconds(idle) == 1800


def test_job_log_triage_classifies_dormant_finished_and_stalled(tmp_path: Path) -> None:
    dormant = tmp_path / "dormant.log"
    finished = tmp_path / "finished.log"
    stalled = tmp_path / "stalled.log"
    dormant.write_text("still old\n", encoding="utf-8")
    finished.write_text("log tail with only a completion summary\n", encoding="utf-8")
    finished.with_suffix(".json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )
    stalled.write_text("working\n", encoding="utf-8")
    old = 1_000.0
    recent_idle = 11_500.0
    now = 12_000.0
    for path in (dormant, finished):
        path.touch()
    stalled.touch()

    assert _classify_job_log(
        dormant,
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: now,
        stat_mtime=lambda path: old,
    ).classification == "dormant"
    assert _classify_job_log(
        finished,
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: now,
        stat_mtime=lambda path: old,
    ).classification == "finished"
    assert _classify_job_log(
        stalled,
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: now,
        stat_mtime=lambda path: recent_idle,
    ).classification == "stalled"


def test_collect_jobs_excludes_dormant_and_finished_logs(tmp_path: Path) -> None:
    dormant = tmp_path / "dormant.output"
    finished = tmp_path / "finished.output"
    stalled = tmp_path / "stalled.output"
    dormant.write_text("old progress\n", encoding="utf-8")
    finished.write_text("completion summary\n", encoding="utf-8")
    finished.with_suffix(".json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    stalled.write_text("active but idle\n", encoding="utf-8")

    jobs = _collect_jobs(
        (str(tmp_path / "*.output"),),
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: 12_000.0,
        stat_mtime=lambda path: 11_500.0
        if path.name == "stalled.output"
        else 1_000.0,
    )

    assert jobs == [
        JobObservation(
            name="stalled.output",
            path=str(stalled),
            status=JobStatus.STALLED,
            idle_seconds=500.0,
            reason="IDLE_TIMEOUT",
        )
    ]


def test_job_log_sidecar_status_marks_finished_before_text_or_mtime(tmp_path: Path) -> None:
    log_path = tmp_path / "task-mrsjvxwx-jxyb81.log"
    sidecar_path = tmp_path / "task-mrsjvxwx-jxyb81.json"
    log_path.write_text("log tail with only a completion summary\n", encoding="utf-8")
    sidecar_path.write_text(
        json.dumps({"status": "completed", "phase": "done"}),
        encoding="utf-8",
    )

    decision = _classify_job_log(
        log_path,
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: 12_000.0,
        stat_mtime=lambda path: 11_500.0,
    )

    assert decision.classification == "finished"
    assert decision.reason == "SIDECAR_STATUS"


def test_job_log_marker_is_fallback_when_sidecar_is_unreadable(tmp_path: Path) -> None:
    log_path = tmp_path / "task-mrsjvxwx-jxyb81.log"
    sidecar_path = tmp_path / "task-mrsjvxwx-jxyb81.json"
    log_path.write_text("worker cleanup finished\n", encoding="utf-8")
    sidecar_path.write_text("{not-json", encoding="utf-8")

    decision = _classify_job_log(
        log_path,
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("finished",),
        now=lambda: 12_000.0,
        stat_mtime=lambda path: 11_500.0,
    )

    assert decision.classification == "finished"
    assert decision.reason == "FINISHED_MARKER"


def test_collect_jobs_uses_json_sidecar_and_falls_back_when_absent(
    tmp_path: Path,
) -> None:
    finished = tmp_path / "finished.log"
    stalled = tmp_path / "stalled.log"
    finished.write_text("completion summary\n", encoding="utf-8")
    stalled.write_text("active but idle\n", encoding="utf-8")
    finished.with_suffix(".json").write_text(
        json.dumps({"status": "cancelled"}),
        encoding="utf-8",
    )

    jobs = _collect_jobs(
        (str(tmp_path / "*.log"),),
        max_idle_seconds=360,
        active_window_seconds=3_600,
        finished_markers=("completed", "cancelled"),
        now=lambda: 12_000.0,
        stat_mtime=lambda path: 11_500.0,
    )

    assert jobs == [
        JobObservation(
            name="stalled.log",
            path=str(stalled),
            status=JobStatus.STALLED,
            idle_seconds=500.0,
            reason="IDLE_TIMEOUT",
        )
    ]


def test_config_requires_contract_fields(tmp_path: Path) -> None:
    config = DigestConfig.from_mapping(
        {
            "repos": [],
            "ledger_path": str(tmp_path / "ledger.jsonl"),
            "job_log_globs": [],
            "monitor_pgrep_patterns": [],
            "baseline_path": str(tmp_path / "baseline.json"),
            "digest_dir": str(tmp_path / "digests"),
        }
    )

    assert config.baseline_path == tmp_path / "baseline.json"
    assert config.digest_dir == tmp_path / "digests"
    assert config.active_window_seconds == 21_600
    assert "completed" in config.finished_markers
