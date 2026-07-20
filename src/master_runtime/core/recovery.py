"""Read-only Recovery Flow 0-6 executor."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from master_runtime.core.bootstrap import (
    BootstrapConfig,
    BootstrapError,
    BootstrapResult,
    bootstrap,
)
from master_runtime.core.work_ledger import JsonlWorkLedger, TrackState


STATUS_OK = "OK"
STATUS_MISS = "MISS"
STATUS_WARN = "WARN"
STATUS_SKIP = "SKIP"


@dataclass(frozen=True)
class RecoveryConfig:
    """Inputs for the read-only recovery executor."""

    charter_path: Path
    handoff_path: Path
    ledger_path: Optional[Path]
    repo_paths: Sequence[Path]
    monitor_pgrep_patterns: Sequence[str]
    session_id: Optional[str] = None


@dataclass(frozen=True)
class RecoveryStep:
    """One Recovery Flow step result."""

    step: str
    status: str
    evidence: str
    manual_actions: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryObservation:
    """Observed Git SSOT state for one repository."""

    path: str
    head: Optional[str]
    branch: Optional[str]
    dirty: Optional[bool]
    status: str
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MonitorObservation:
    """Observed monitor process for one pgrep pattern."""

    pattern: str
    status: str
    evidence: str
    matches: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryReport:
    """Recovery Flow report with JSON-serializable content."""

    steps: Tuple[RecoveryStep, ...]
    repositories: Tuple[RepositoryObservation, ...] = ()
    monitors: Tuple[MonitorObservation, ...] = ()
    active_tracks: Tuple[Mapping[str, object], ...] = ()
    manual_actions: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "repositories": [repo.to_dict() for repo in self.repositories],
            "monitors": [monitor.to_dict() for monitor in self.monitors],
            "active_tracks": [dict(track) for track in self.active_tracks],
            "manual_actions": list(self.manual_actions),
        }


CommandRunner = Callable[[Sequence[str]], Tuple[int, str, str]]
ProcessProbe = Callable[[str], Tuple[int, str, str]]
BootstrapFn = Callable[[BootstrapConfig], BootstrapResult]


def recover(
    config: RecoveryConfig,
    command_runner: Optional[CommandRunner] = None,
    process_probe: Optional[ProcessProbe] = None,
    bootstrap_fn: BootstrapFn = bootstrap,
) -> RecoveryReport:
    """Run Recovery Flow 0-6 without writing files or mutating processes."""

    steps: List[RecoveryStep] = []
    manual_actions: List[str] = []
    misses: List[str] = []

    bootstrap_result = _run_bootstrap(config, bootstrap_fn)
    step0 = _step0(config, bootstrap_result)
    steps.append(step0)
    manual_actions.extend(step0.manual_actions)
    if step0.status == STATUS_MISS:
        misses.append("step 0: " + step0.evidence)

    if step0.status == STATUS_MISS:
        step1, active_tracks = _step1_fail_closed(config)
        repositories: Tuple[RepositoryObservation, ...] = ()
        monitors: Tuple[MonitorObservation, ...] = ()
    else:
        step1, ledger_step, active_tracks = _step1(config)
        if step1.status == STATUS_MISS:
            misses.append("step 1: " + step1.evidence)
        steps.append(step1)
        if ledger_step is not None:
            steps.append(ledger_step)

        repositories = tuple(
            _observe_repo(path, command_runner or _default_command_runner)
            for path in config.repo_paths
        )
        repo_status = STATUS_OK
        if any(repo.status == STATUS_WARN for repo in repositories):
            repo_status = STATUS_WARN
        steps.append(
            RecoveryStep(
                step="2-3",
                status=repo_status,
                evidence=_repo_evidence(repositories),
            )
        )

        monitors = tuple(
            _observe_monitor(pattern, process_probe or _default_process_probe)
            for pattern in config.monitor_pgrep_patterns
        )
    if step0.status == STATUS_MISS:
        steps.append(step1)
        steps.append(
            RecoveryStep(
                step="2-3",
                status=STATUS_SKIP,
                evidence="fail-closed after step 0 MISS",
            )
        )

    if step0.status != STATUS_MISS:
        for repo in repositories:
            if repo.status == STATUS_WARN:
                misses.append("repo " + repo.path + ": " + repo.evidence)

    step4 = RecoveryStep(
        step="4",
        status=STATUS_OK if not misses else STATUS_WARN,
        evidence=_miss_evidence(misses),
        manual_actions=("Trace Archive search is manual; no automatic search was run.",),
    )
    steps.append(step4)
    manual_actions.extend(step4.manual_actions)

    if step0.status == STATUS_MISS:
        steps.append(
            RecoveryStep(
                step="5",
                status=STATUS_SKIP,
                evidence="fail-closed after step 0 MISS",
            )
        )
    else:
        monitor_actions = tuple(
            "Terminate then re-arm monitor pattern '{0}' after takeover.".format(
                monitor.pattern
            )
            for monitor in monitors
            if monitor.matches
        )
        step5_status = STATUS_OK
        if monitor_actions or any(monitor.status == STATUS_WARN for monitor in monitors):
            step5_status = STATUS_WARN
        step5 = RecoveryStep(
            step="5",
            status=step5_status,
            evidence=_monitor_evidence(monitors),
            manual_actions=monitor_actions,
        )
        steps.append(step5)
        manual_actions.extend(step5.manual_actions)

    checklist = _successor_checklist(active_tracks)
    step6 = RecoveryStep(
        step="6",
        status=STATUS_OK,
        evidence="successor verification checklist generated",
        manual_actions=checklist,
    )
    steps.append(step6)
    manual_actions.extend(checklist)

    return RecoveryReport(
        steps=tuple(steps),
        repositories=repositories,
        monitors=monitors,
        active_tracks=active_tracks,
        manual_actions=tuple(manual_actions),
    )


def _run_bootstrap(
    config: RecoveryConfig,
    bootstrap_fn: BootstrapFn,
) -> Optional[BootstrapResult]:
    if not Path(config.charter_path).exists():
        return None
    try:
        return bootstrap_fn(
            BootstrapConfig(
                charter_path=config.charter_path,
                handoff_path=config.handoff_path,
                session_id=config.session_id,
            )
        )
    except BootstrapError:
        return None


def _step0(
    config: RecoveryConfig,
    bootstrap_result: Optional[BootstrapResult],
) -> RecoveryStep:
    if not Path(config.charter_path).exists():
        return RecoveryStep(
            step="0",
            status=STATUS_MISS,
            evidence="Charter missing: " + str(config.charter_path),
            manual_actions=("Stop recovery until the charter path is restored.",),
        )
    if bootstrap_result is None:
        return RecoveryStep(
            step="0",
            status=STATUS_MISS,
            evidence="Bootstrap failed for charter: " + str(config.charter_path),
            manual_actions=("Stop recovery until bootstrap can restore Role State.",),
        )

    warnings = list(bootstrap_result.warnings)
    role_state = bootstrap_result.role_state
    evidence = "charter exists; "
    if role_state is None:
        evidence += "Role State missing"
        return RecoveryStep(
            step="0",
            status=STATUS_WARN,
            evidence=evidence,
            manual_actions=("Manually restore Role State before acting.",),
        )

    evidence += "Role State restored: " + role_state.role
    if warnings:
        evidence += "; warnings=" + ",".join(warnings)
    status = STATUS_WARN if warnings else STATUS_OK
    actions = tuple(
        "Session lease warning: " + warning
        for warning in warnings
        if warning.startswith("DUAL_INSTANCE:")
    )
    return RecoveryStep(step="0", status=status, evidence=evidence, manual_actions=actions)


def _step1_fail_closed(
    config: RecoveryConfig,
) -> Tuple[RecoveryStep, Tuple[Mapping[str, object], ...]]:
    return (
        RecoveryStep(
            step="1",
            status=STATUS_SKIP,
            evidence="fail-closed after step 0 MISS",
        ),
        (),
    )


def _step1(
    config: RecoveryConfig,
) -> Tuple[RecoveryStep, Optional[RecoveryStep], Tuple[Mapping[str, object], ...]]:
    handoff = Path(config.handoff_path)
    if not handoff.exists():
        return (
            RecoveryStep(
                step="1",
                status=STATUS_MISS,
                evidence="Handoff missing: " + str(handoff),
                manual_actions=("Restore the handoff before continuing recovery.",),
            ),
            None,
            (),
        )

    text = handoff.read_text(encoding="utf-8")
    has_body = bool(text.strip())
    has_role_state = "Current Role:" in text and "Role Lock:" in text
    status = STATUS_OK if has_body and has_role_state else STATUS_WARN
    evidence = "handoff exists; "
    evidence += "Role State block present" if has_role_state else "Role State block missing"
    evidence += "; body present" if has_body else "; body empty"

    active_tracks: Tuple[Mapping[str, object], ...]
    ledger_step: Optional[RecoveryStep] = None
    if config.ledger_path is None:
        active_tracks = ()
        ledger_step = RecoveryStep(
            step="1-ledger",
            status=STATUS_SKIP,
            evidence="work ledger SKIP: no ledger_path",
        )
    else:
        ledger = JsonlWorkLedger(config.ledger_path)
        active_tracks = tuple(
            _track_to_dict(track)
            for track in ledger.active_tracks().values()
        )
        ledger_step = RecoveryStep(
            step="1-ledger",
            status=STATUS_OK,
            evidence="active tracks={0}".format(len(active_tracks)),
        )
        if ledger.warnings:
            status = STATUS_WARN
            ledger_step = RecoveryStep(
                step="1-ledger",
                status=STATUS_WARN,
                evidence="active tracks={0}; ledger warnings={1}".format(
                    len(active_tracks),
                    ",".join(ledger.warnings),
                ),
            )

    return (
        RecoveryStep(step="1", status=status, evidence=evidence),
        ledger_step,
        active_tracks,
    )


def _observe_repo(path: Path, runner: CommandRunner) -> RepositoryObservation:
    repo_path = Path(path)
    head = runner(("git", "-C", str(repo_path), "rev-parse", "--short=8", "HEAD"))
    if head[0] != 0:
        return RepositoryObservation(
            path=str(repo_path),
            head=None,
            branch=None,
            dirty=None,
            status=STATUS_WARN,
            evidence=head[2].strip() or head[1].strip() or "git HEAD unavailable",
        )

    branch = runner(("git", "-C", str(repo_path), "branch", "--show-current"))
    status = runner(("git", "-C", str(repo_path), "status", "--porcelain"))
    warn_parts = []
    if branch[0] != 0:
        warn_parts.append(branch[2].strip() or "branch unavailable")
    if status[0] != 0:
        warn_parts.append(status[2].strip() or "dirty check unavailable")
    return RepositoryObservation(
        path=str(repo_path),
        head=head[1].strip(),
        branch=branch[1].strip() if branch[0] == 0 else None,
        dirty=bool(status[1].strip()) if status[0] == 0 else None,
        status=STATUS_WARN if warn_parts else STATUS_OK,
        evidence="; ".join(warn_parts) if warn_parts else "git state observed",
    )


def _observe_monitor(pattern: str, probe: ProcessProbe) -> MonitorObservation:
    code, stdout, stderr = probe(pattern)
    if code == 0:
        matches = filter_running_monitor_processes(pattern, stdout)
        return MonitorObservation(
            pattern=pattern,
            status=STATUS_WARN if matches else STATUS_OK,
            evidence="running monitor matches={0}".format(len(matches)),
            matches=matches,
        )
    if code == 1:
        return MonitorObservation(
            pattern=pattern,
            status=STATUS_OK,
            evidence="no process found",
        )
    return MonitorObservation(
        pattern=pattern,
        status=STATUS_WARN,
        evidence=stderr.strip() or stdout.strip() or "pgrep failed",
    )


def filter_running_monitor_processes(pattern: str, pgrep_output: str) -> Tuple[str, ...]:
    """Return pgrep rows whose command executes the matched script."""

    return tuple(
        line
        for line in pgrep_output.splitlines()
        if _is_running_monitor_process(pattern, line)
    )


def _is_running_monitor_process(pattern: str, pgrep_line: str) -> bool:
    line = pgrep_line.strip()
    if not line:
        return False
    pid, command = _split_pgrep_line(line)
    if pid is None or command is None:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) < 2:
        return False
    executable = os.path.basename(argv[0])
    if executable in ("pgrep", "grep", "rg"):
        return False
    interpreters = ("sh", "bash", "zsh", "python", "python2", "python3")
    if executable not in interpreters:
        return False
    for argument in argv[1:]:
        if argument.startswith("-"):
            continue
        if _argument_executes_pattern(argument, pattern):
            return True
        return False
    return False


def _split_pgrep_line(line: str) -> Tuple[Optional[int], Optional[str]]:
    parts = line.split(None, 1)
    if len(parts) != 2:
        return None, None
    if not parts[0].isdigit():
        return None, None
    return int(parts[0]), parts[1]


def _argument_executes_pattern(argument: str, pattern: str) -> bool:
    argument_name = os.path.basename(argument)
    pattern_name = os.path.basename(pattern)
    return argument == pattern or argument_name == pattern_name


def _repo_evidence(repositories: Sequence[RepositoryObservation]) -> str:
    if not repositories:
        return "no repo paths configured"
    return "; ".join(
        "{0} head={1} branch={2} dirty={3} status={4}".format(
            repo.path,
            repo.head,
            repo.branch,
            repo.dirty,
            repo.status,
        )
        for repo in repositories
    )


def _miss_evidence(misses: Sequence[str]) -> str:
    if not misses:
        return "no misses collected; Trace Archive search is manual"
    return "misses: " + " | ".join(misses) + "; Trace Archive search is manual"


def _monitor_evidence(monitors: Sequence[MonitorObservation]) -> str:
    if not monitors:
        return "no monitor patterns configured"
    return "; ".join(
        "{0}: {1}".format(monitor.pattern, monitor.evidence)
        for monitor in monitors
    )


def _successor_checklist(
    active_tracks: Sequence[Mapping[str, object]],
) -> Tuple[str, ...]:
    actions = [
        "Recite active tracks: " + _active_track_names(active_tracks),
        "Compare predecessor PID command lines before terminating anything.",
        "Append the succession lineage entry after verification.",
    ]
    return tuple(actions)


def _active_track_names(active_tracks: Sequence[Mapping[str, object]]) -> str:
    if not active_tracks:
        return "none"
    return ", ".join(
        "{0} ({1})".format(track.get("track_id"), track.get("title"))
        for track in active_tracks
    )


def _track_to_dict(track: TrackState) -> Mapping[str, object]:
    return {
        "track_id": track.track_id,
        "title": track.title,
        "refs": list(track.refs),
        "status": track.status,
        "note": track.note,
        "resolution": track.resolution,
        "registered_at": track.registered_at,
        "updated_at": track.updated_at,
        "closed_at": track.closed_at,
    }


def _default_command_runner(command: Sequence[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _default_process_probe(pattern: str) -> Tuple[int, str, str]:
    return _process_probe_from_runner(pattern, _default_command_runner)


def _process_probe_from_runner(
    pattern: str,
    runner: CommandRunner,
) -> Tuple[int, str, str]:
    pgrep = runner(("pgrep", "-f", pattern))
    if pgrep[0] != 0:
        return pgrep

    rows: List[str] = []
    errors: List[str] = []
    for pid in _pgrep_pids(pgrep[1]):
        ps = runner(("ps", "-p", pid, "-o", "pid=,command="))
        if ps[0] == 0:
            rows.extend(line.strip() for line in ps[1].splitlines() if line.strip())
        else:
            error = ps[2].strip() or ps[1].strip()
            if error:
                errors.append(error)

    if not rows and errors:
        return 3, "", "\n".join(errors)
    stdout = "\n".join(rows)
    if stdout:
        stdout += "\n"
    return 0, stdout, "\n".join(errors)


def _pgrep_pids(output: str) -> Tuple[str, ...]:
    return tuple(
        line.strip()
        for line in output.splitlines()
        if line.strip().isdigit()
    )
