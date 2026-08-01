"""Installed-tool measurement for adapter profiles."""

import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Tuple



@dataclass(frozen=True)
class RunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    probe_cmd: Optional[Tuple[str, ...]] = None
    path: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.probe_cmd is None) == (self.path is None):
            raise ValueError("ProbeCheck requires exactly one of probe_cmd or path")


@dataclass(frozen=True)
class CheckResult:
    name: str
    present: bool
    detail: str
    probe_cmd: Optional[Tuple[str, ...]] = None
    path: Optional[str] = None


@dataclass(frozen=True)
class DoctorReport:
    results: Tuple[CheckResult, ...]

    @property
    def present_names(self) -> Tuple[str, ...]:
        return tuple(result.name for result in self.results if result.present)

    @property
    def missing_names(self) -> Tuple[str, ...]:
        return tuple(result.name for result in self.results if not result.present)


Runner = Callable[[Sequence[str], Optional[str]], RunResult]
PathExists = Callable[[str], bool]


def default_runner(cmd: Sequence[str], cwd: Optional[str] = None) -> RunResult:
    try:
        completed = subprocess.run(
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return RunResult(exit_code=127, stderr=str(exc))
    return RunResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


DEFAULT_CHECKS = (
    ProbeCheck(name="git", probe_cmd=("git", "--version")),
    ProbeCheck(name="node", probe_cmd=("node", "--version")),
    ProbeCheck(name="orca", probe_cmd=("orca", "--version")),
    ProbeCheck(name="bd", probe_cmd=("bd", "--version")),
)


def doctor(
    checks: Optional[Iterable[ProbeCheck]] = None,
    runner: Optional[Runner] = None,
    path_exists: Optional[PathExists] = None,
    cwd: Optional[str] = None,
) -> DoctorReport:
    selected_checks = tuple(checks if checks is not None else DEFAULT_CHECKS)
    run = runner if runner is not None else default_runner
    exists = path_exists if path_exists is not None else os.path.exists
    results = []

    for check in selected_checks:
        if check.path is not None:
            expanded_path = os.path.expanduser(check.path)
            present = exists(expanded_path)
            detail = "present" if present else "missing"
            results.append(
                CheckResult(
                    name=check.name,
                    present=present,
                    detail=detail,
                    path=expanded_path,
                )
            )
            continue

        assert check.probe_cmd is not None
        result = run(check.probe_cmd, cwd)
        output = result.stdout.strip() or result.stderr.strip()
        present = result.exit_code == 0
        detail = output if output else ("present" if present else "missing")
        results.append(
            CheckResult(
                name=check.name,
                present=present,
                detail=detail,
                probe_cmd=check.probe_cmd,
            )
        )

    return DoctorReport(results=tuple(results))

