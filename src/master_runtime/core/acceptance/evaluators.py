"""Concrete evaluators for the acceptance loop.

The loop only needs a callable; these are the batteries-included implementations for
case books whose cases are plain commands.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple, Union

from master_runtime.core.acceptance.casebook import VerificationCase
from master_runtime.core.acceptance.verdict import CaseResult


DEFAULT_CASE_TIMEOUT_SECONDS = 15 * 60

CommandRunner = Callable[[Sequence[str], str, int], Tuple[int, str]]


def default_command_runner(
    argv: Sequence[str],
    cwd: str,
    timeout_seconds: int,
) -> Tuple[int, str]:
    """Run one verification command and return its exit code plus a short detail."""

    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, "case timed out after {0}s".format(exc.timeout)
    output = (completed.stdout or "").strip()
    return completed.returncode, output.splitlines()[-1] if output else ""


def command_evaluator(
    workspace_root: Union[str, Path],
    runner: Optional[CommandRunner] = None,
    timeout_seconds: int = DEFAULT_CASE_TIMEOUT_SECONDS,
    clock: Optional[Callable[[], float]] = None,
):
    """Build an evaluator that runs each case command in the workspace.

    A case with no command fails closed rather than counting as a pass.
    """

    run = runner or default_command_runner
    now = clock or time.monotonic
    cwd = str(workspace_root)

    def evaluate(candidate, cases: Sequence[VerificationCase]) -> Tuple[CaseResult, ...]:
        del candidate  # the workspace already holds the candidate under evaluation
        results = []
        for case in cases:
            if not case.command:
                results.append(
                    CaseResult(
                        case_id=case.case_id,
                        split=case.split,
                        stratum=case.stratum,
                        passed=False,
                        detail="case has no command",
                    )
                )
                continue
            started = float(now())
            returncode, detail = run(case.command, cwd, timeout_seconds)
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    split=case.split,
                    stratum=case.stratum,
                    passed=returncode == 0,
                    detail="" if returncode == 0 else detail or "exit {0}".format(returncode),
                    duration_s=float(now()) - started,
                )
            )
        return tuple(results)

    return evaluate
