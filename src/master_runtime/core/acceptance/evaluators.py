"""Concrete evaluators for the acceptance loop.

The loop only needs a callable; this is the batteries-included implementation for
case books whose cases are plain commands.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from master_runtime.core.acceptance.casebook import VerificationCase
from master_runtime.core.acceptance.models import Evaluator, mark_in_place
from master_runtime.core.acceptance.process import (
    DEFAULT_PROCESS_TIMEOUT_SECONDS,
    ProcessRunner,
    resolve_runner,
)
from master_runtime.core.acceptance.verdict import CaseResult


def command_evaluator(
    workspace_root: Union[str, Path],
    runner: Optional[ProcessRunner] = None,
    timeout_seconds: int = DEFAULT_PROCESS_TIMEOUT_SECONDS,
) -> Evaluator:
    """Build an evaluator that runs each case command in the workspace.

    The commands read whatever is currently in the workspace, so this evaluator
    declares in-place mutation: the loop refuses to iterate past a rejection unless a
    restore hook is supplied. A case with no command fails closed rather than passing.
    """

    run = resolve_runner(runner)
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
            started = time.monotonic()
            result = run(case.command, cwd, timeout_seconds)
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    split=case.split,
                    stratum=case.stratum,
                    passed=result.ok,
                    detail=""
                    if result.ok
                    else result.tail() or "exit {0}".format(result.returncode),
                    duration_s=time.monotonic() - started,
                )
            )
        return tuple(results)

    return mark_in_place(evaluate)
