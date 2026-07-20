"""L1 read-only digest loop for resident orchestrator observations."""

from __future__ import annotations

import argparse
import copy
import glob
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple

from master_runtime.core.watchdog import StallStatus, check_stall


SHORT_INTERVAL_SECONDS = 600
LONG_INTERVAL_SECONDS = 1800
DEFAULT_LEDGER_TAIL_LIMIT = 20
DEFAULT_MAX_IDLE_SECONDS = 360


class TriageClassification(str, Enum):
    """Stable L1 triage classes."""

    ECHO = "echo"
    EXPECTED = "expected"
    UNEXPLAINED = "unexplained"


class JobStatus(str, Enum):
    """Digest-level job status."""

    RUNNING = "running"
    STALLED = "stalled"


class ProcessStatus(str, Enum):
    """Process liveness observed by pgrep."""

    RUNNING = "running"
    IDLE = "idle"


@dataclass(frozen=True)
class RepoConfig:
    """Repository configured for observation."""

    name: str
    path: Path


@dataclass(frozen=True)
class DigestConfig:
    """Config for one L1 digest tick."""

    repos: Tuple[RepoConfig, ...]
    ledger_path: Path
    job_log_globs: Tuple[str, ...]
    monitor_pgrep_patterns: Tuple[str, ...]
    baseline_path: Path
    digest_dir: Path
    ledger_tail_limit: int = DEFAULT_LEDGER_TAIL_LIMIT
    max_idle_seconds: int = DEFAULT_MAX_IDLE_SECONDS

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DigestConfig":
        required = (
            "repos",
            "ledger_path",
            "job_log_globs",
            "monitor_pgrep_patterns",
            "baseline_path",
            "digest_dir",
        )
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError("Missing digest config fields: " + ", ".join(missing))

        return cls(
            repos=tuple(_repo_config(repo) for repo in _sequence(value["repos"])),
            ledger_path=Path(str(value["ledger_path"])),
            job_log_globs=tuple(str(item) for item in _sequence(value["job_log_globs"])),
            monitor_pgrep_patterns=tuple(
                str(item) for item in _sequence(value["monitor_pgrep_patterns"])
            ),
            baseline_path=Path(str(value["baseline_path"])),
            digest_dir=Path(str(value["digest_dir"])),
            ledger_tail_limit=int(
                value.get("ledger_tail_limit", DEFAULT_LEDGER_TAIL_LIMIT)
            ),
            max_idle_seconds=int(value.get("max_idle_seconds", DEFAULT_MAX_IDLE_SECONDS)),
        )


@dataclass(frozen=True)
class RepoObservation:
    """Observed repository state."""

    name: str
    path: str
    head: Optional[str]
    dirty: bool
    error: Optional[str] = None

    def state(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "path": self.path,
            "head": self.head,
            "dirty": self.dirty,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass(frozen=True)
class JobObservation:
    """Observed worker job log status."""

    name: str
    path: str
    status: JobStatus
    idle_seconds: Optional[float] = None
    reason: str = "OK"


@dataclass(frozen=True)
class ProcessObservation:
    """Observed process liveness."""

    pattern: str
    status: ProcessStatus
    error: Optional[str] = None


@dataclass(frozen=True)
class Snapshot:
    """All observations from one SENSE phase."""

    repos: Tuple[RepoObservation, ...] = field(default_factory=tuple)
    ledger_entries: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    jobs: Tuple[JobObservation, ...] = field(default_factory=tuple)
    processes: Tuple[ProcessObservation, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TriageItem:
    """One classified observation."""

    classification: TriageClassification
    kind: str
    name: str
    summary: str
    state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TriageResult:
    """Pure triage output."""

    items: Tuple[TriageItem, ...]

    @property
    def has_unexplained(self) -> bool:
        return any(
            item.classification == TriageClassification.UNEXPLAINED
            for item in self.items
        )


@dataclass(frozen=True)
class DigestReport:
    """Rendered digest input."""

    generated_at: float
    snapshot: Snapshot
    triage: TriageResult
    next_interval_seconds: int


@dataclass(frozen=True)
class TickResult:
    """Result of one CLI tick."""

    exit_code: int
    digest_markdown: str
    digest_path: Path
    report: DigestReport


CollectFn = Callable[[DigestConfig], Snapshot]
NowFn = Callable[[], float]


def collect_observations(config: DigestConfig) -> Snapshot:
    """Collect SENSE observations using read-only local probes."""

    return Snapshot(
        repos=tuple(_collect_repo(repo) for repo in config.repos),
        ledger_entries=tuple(_tail_jsonl(config.ledger_path, config.ledger_tail_limit)),
        jobs=tuple(_collect_jobs(config.job_log_globs, config.max_idle_seconds)),
        processes=tuple(_collect_processes(config.monitor_pgrep_patterns)),
    )


def triage_snapshot(
    snapshot: Snapshot,
    baseline: Mapping[str, Any],
) -> TriageResult:
    """Classify repo drift without taking any response action."""

    items: List[TriageItem] = []
    baseline_repos = _mapping(baseline.get("repos"))

    for repo in snapshot.repos:
        current = repo.state()
        previous = _mapping(baseline_repos.get(repo.name))
        if previous and _repo_states_equal(previous, current):
            continue

        summary = _repo_drift_summary(repo.name, previous, current)
        if _is_ledger_echo(repo, snapshot.ledger_entries):
            items.append(
                TriageItem(
                    classification=TriageClassification.ECHO,
                    kind="repo",
                    name=repo.name,
                    summary=summary,
                    state=current,
                )
            )
        elif not previous or _is_expected_repo(repo, baseline):
            items.append(
                TriageItem(
                    classification=TriageClassification.EXPECTED,
                    kind="repo",
                    name=repo.name,
                    summary=summary,
                    state=current,
                )
            )
        else:
            items.append(
                TriageItem(
                    classification=TriageClassification.UNEXPLAINED,
                    kind="repo",
                    name=repo.name,
                    summary=summary,
                    state=current,
                )
            )

    return TriageResult(items=tuple(items))


def baseline_with_expected_updates(
    baseline: Mapping[str, Any],
    triage: TriageResult,
) -> Dict[str, Any]:
    """Return a baseline copy with only expected triage items applied."""

    updated = copy.deepcopy(dict(baseline))
    repos = updated.setdefault("repos", {})
    expected = _mutable_mapping(updated.get("expected"))
    expected_repos = _mutable_mapping(expected.get("repos"))

    for item in triage.items:
        if (
            item.classification == TriageClassification.EXPECTED
            and item.kind == "repo"
        ):
            repos[item.name] = dict(item.state)
            expected_repos.pop(item.name, None)

    if expected:
        expected["repos"] = expected_repos
        updated["expected"] = expected
    return updated


def build_digest_report(
    snapshot: Snapshot,
    baseline: Mapping[str, Any],
    generated_at: Optional[float] = None,
) -> DigestReport:
    """Build a report from injected observations."""

    triage = triage_snapshot(snapshot, baseline)
    return DigestReport(
        generated_at=time.time() if generated_at is None else float(generated_at),
        snapshot=snapshot,
        triage=triage,
        next_interval_seconds=suggest_next_interval_seconds(snapshot),
    )


def render_digest(report: DigestReport) -> str:
    """Render one stop-reading-friendly markdown digest."""

    lines: List[str] = [
        "# L1 Digest",
        "",
        "Generated: " + _utc_timestamp(report.generated_at),
        "",
    ]
    lines.extend(_render_unexplained(report.triage))
    lines.extend(_render_job_status(report.snapshot))
    lines.extend(_render_repo_drift(report.triage))
    lines.extend(_render_ledger_summary(report.snapshot.ledger_entries))
    lines.extend(
        [
            "## Next Observation Interval",
            "",
            "- %s seconds" % report.next_interval_seconds,
            "",
        ]
    )
    return "\n".join(lines)


def suggest_next_interval_seconds(snapshot: Snapshot) -> int:
    """Return only the next PACE suggestion; scheduling is caller-owned."""

    active_job = any(
        job.status in (JobStatus.RUNNING, JobStatus.STALLED) for job in snapshot.jobs
    )
    active_process = any(
        process.status == ProcessStatus.RUNNING for process in snapshot.processes
    )
    if active_job or active_process:
        return SHORT_INTERVAL_SECONDS
    return LONG_INTERVAL_SECONDS


def tick(
    config: DigestConfig,
    collect_fn: CollectFn = collect_observations,
    now: Optional[NowFn] = None,
) -> TickResult:
    """Run one SENSE/TRIAGE/RECORD/PACE tick."""

    current_time = _resolve_now(now)
    baseline = load_baseline(config.baseline_path)
    snapshot = collect_fn(config)
    report = build_digest_report(snapshot, baseline, generated_at=current_time)
    updated_baseline = baseline_with_expected_updates(baseline, report.triage)
    if updated_baseline != baseline:
        save_baseline(config.baseline_path, updated_baseline)

    digest_markdown = render_digest(report)
    digest_path = write_digest(config.digest_dir, digest_markdown, current_time)
    exit_code = 4 if report.triage.has_unexplained else 0
    return TickResult(
        exit_code=exit_code,
        digest_markdown=digest_markdown,
        digest_path=digest_path,
        report=report,
    )


def load_baseline(path: Path) -> Dict[str, Any]:
    """Load baseline JSON; missing baseline starts empty for bootstrap."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as baseline_file:
        data = json.load(baseline_file)
    if not isinstance(data, dict):
        raise ValueError("baseline JSON must be an object")
    return data


def save_baseline(path: Path, baseline: Mapping[str, Any]) -> None:
    """Write baseline JSON for expected observations only."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as baseline_file:
        json.dump(baseline, baseline_file, sort_keys=True, indent=2)
        baseline_file.write("\n")


def write_digest(digest_dir: Path, markdown: str, generated_at: float) -> Path:
    """Persist one markdown digest."""

    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / ("l1-digest-%d.md" % int(generated_at))
    digest_path.write_text(markdown, encoding="utf-8")
    return digest_path


def cli_main(
    argv: Optional[Sequence[str]] = None,
    collect_fn: CollectFn = collect_observations,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
    now: Optional[NowFn] = None,
) -> int:
    """CLI entry point for scripts/l1-digest."""

    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "tick":
        parser.print_help(err)
        return 2

    try:
        config = load_config(Path(args.config))
        result = tick(config, collect_fn=collect_fn, now=now)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=err)
        return 2

    out.write(result.digest_markdown)
    return result.exit_code


def load_config(path: Path) -> DigestConfig:
    with path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError("config JSON must be an object")
    return DigestConfig.from_mapping(data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l1-digest")
    subparsers = parser.add_subparsers(dest="command", required=True)
    tick_parser = subparsers.add_parser("tick")
    tick_parser.add_argument("--config", required=True)
    return parser


def _repo_config(value: Any) -> RepoConfig:
    if isinstance(value, str):
        path = Path(value)
        return RepoConfig(name=path.name, path=path)
    if isinstance(value, Mapping):
        if "path" not in value:
            raise ValueError("repo config requires path")
        path = Path(str(value["path"]))
        name = str(value.get("name") or path.name)
        return RepoConfig(name=name, path=path)
    raise ValueError("repo entries must be strings or objects")


def _collect_repo(repo: RepoConfig) -> RepoObservation:
    head_result = _run(["git", "-C", str(repo.path), "rev-parse", "HEAD"])
    if head_result.returncode != 0:
        return RepoObservation(
            name=repo.name,
            path=str(repo.path),
            head=None,
            dirty=False,
            error=head_result.stderr.strip() or "HEAD_UNREADABLE",
        )

    dirty_result = _run(["git", "-C", str(repo.path), "status", "--porcelain"])
    dirty = bool(dirty_result.stdout.strip()) if dirty_result.returncode == 0 else False
    error = None if dirty_result.returncode == 0 else dirty_result.stderr.strip()
    return RepoObservation(
        name=repo.name,
        path=str(repo.path),
        head=head_result.stdout.strip(),
        dirty=dirty,
        error=error,
    )


def _collect_jobs(patterns: Sequence[str], max_idle_seconds: int) -> List[JobObservation]:
    jobs: List[JobObservation] = []
    for pattern in patterns:
        for path_text in sorted(glob.glob(pattern)):
            path = Path(path_text)
            decision = check_stall(path, max_idle_seconds=max_idle_seconds)
            if decision.status == StallStatus.STALLED:
                status = JobStatus.STALLED
            elif decision.status == StallStatus.OK:
                status = JobStatus.RUNNING
            else:
                continue
            jobs.append(
                JobObservation(
                    name=path.name,
                    path=str(path),
                    status=status,
                    idle_seconds=decision.idle_seconds,
                    reason=decision.reason,
                )
            )
    return jobs


def _collect_processes(patterns: Sequence[str]) -> List[ProcessObservation]:
    processes: List[ProcessObservation] = []
    for pattern in patterns:
        try:
            result = _run(["pgrep", "-f", pattern])
        except OSError as exc:
            processes.append(
                ProcessObservation(
                    pattern=pattern,
                    status=ProcessStatus.IDLE,
                    error=str(exc),
                )
            )
            continue
        processes.append(
            ProcessObservation(
                pattern=pattern,
                status=ProcessStatus.RUNNING
                if result.returncode == 0
                else ProcessStatus.IDLE,
                error=None if result.returncode in (0, 1) else result.stderr.strip(),
            )
        )
    return processes


def _tail_jsonl(path: Path, limit: int) -> List[Mapping[str, Any]]:
    if not path.exists():
        return []
    entries: List[Mapping[str, Any]] = []
    with path.open("r", encoding="utf-8") as ledger:
        for line in ledger:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entries.append(value)
    return entries[-limit:]


def _is_ledger_echo(
    repo: RepoObservation,
    entries: Sequence[Mapping[str, Any]],
) -> bool:
    for entry in entries:
        if not _entry_mentions_repo(entry, repo):
            continue
        head = _first_text(
            entry,
            ("head", "new_head", "result_head", "after_head", "commit", "sha"),
        )
        if head is not None and head != repo.head:
            continue
        dirty = _first_bool(entry, ("dirty", "result_dirty", "repo_dirty"))
        if dirty is not None and dirty != repo.dirty:
            continue
        return True
    return False


def _entry_mentions_repo(entry: Mapping[str, Any], repo: RepoObservation) -> bool:
    names = ("repo", "repo_name", "repository", "name")
    paths = ("repo_path", "path", "cwd", "worktree")
    for key in names:
        value = entry.get(key)
        if isinstance(value, str) and value == repo.name:
            return True
    for key in paths:
        value = entry.get(key)
        if isinstance(value, str) and _same_path_text(value, repo.path):
            return True
    return False


def _is_expected_repo(repo: RepoObservation, baseline: Mapping[str, Any]) -> bool:
    expected = _mapping(baseline.get("expected"))
    repos = _mapping(expected.get("repos"))
    target = _mapping(repos.get(repo.name))
    return bool(target) and _repo_states_equal(target, repo.state())


def _repo_states_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return left.get("head") == right.get("head") and bool(left.get("dirty")) == bool(
        right.get("dirty")
    )


def _repo_drift_summary(
    name: str,
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> str:
    if not previous:
        return "%s baseline bootstrap: head=%s dirty=%s" % (
            name,
            current.get("head"),
            current.get("dirty"),
        )
    return "%s head %s -> %s; dirty %s -> %s" % (
        name,
        previous.get("head"),
        current.get("head"),
        bool(previous.get("dirty")),
        bool(current.get("dirty")),
    )


def _render_unexplained(triage: TriageResult) -> List[str]:
    unexplained = [
        item for item in triage.items if item.classification == TriageClassification.UNEXPLAINED
    ]
    lines = ["## Unexplained", ""]
    if unexplained:
        lines.extend("- %s" % item.summary for item in unexplained)
    else:
        lines.append("- None")
    lines.append("")
    return lines


def _render_job_status(snapshot: Snapshot) -> List[str]:
    lines = ["## Job Status", ""]
    if not snapshot.jobs and not snapshot.processes:
        lines.append("- No running or stalled jobs observed.")
    for job in snapshot.jobs:
        detail = "%s: %s" % (job.name, job.status.value)
        if job.idle_seconds is not None:
            detail += " (idle %.0fs)" % job.idle_seconds
        lines.append("- " + detail)
    for process in snapshot.processes:
        detail = "process %s: %s" % (process.pattern, process.status.value)
        if process.error:
            detail += " (%s)" % process.error
        lines.append("- " + detail)
    lines.append("")
    return lines


def _render_repo_drift(triage: TriageResult) -> List[str]:
    repo_items = [item for item in triage.items if item.kind == "repo"]
    lines = ["## Repo Drift", ""]
    if not repo_items:
        lines.append("- None")
    for item in repo_items:
        lines.append("- [%s] %s" % (item.classification.value, item.summary))
    lines.append("")
    return lines


def _render_ledger_summary(entries: Sequence[Mapping[str, Any]]) -> List[str]:
    lines = ["## Ledger Summary", ""]
    if not entries:
        lines.append("- No ledger entries observed.")
    for entry in entries[-5:]:
        lines.append("- " + _compact_entry(entry))
    lines.append("")
    return lines


def _compact_entry(entry: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("job_id", "decision", "reason", "repo", "repo_path", "new_head"):
        value = entry.get(key)
        if value is not None:
            parts.append("%s=%s" % (key, value))
    if parts:
        return " ".join(parts)
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _run(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
    )


def _utc_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _resolve_now(now: Optional[NowFn]) -> float:
    if now is None:
        return time.time()
    return float(now())


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("config field must be a sequence")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _mutable_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _first_text(entry: Mapping[str, Any], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str):
            return value
    return None


def _first_bool(entry: Mapping[str, Any], keys: Sequence[str]) -> Optional[bool]:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, bool):
            return value
    return None


def _same_path_text(left: str, right: str) -> bool:
    return str(Path(left)) == str(Path(right))


if __name__ == "__main__":
    raise SystemExit(cli_main())
