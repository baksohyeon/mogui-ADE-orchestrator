"""One subprocess runner shared by the proposer seam and the case evaluators."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence, Tuple, Union
from pathlib import Path


DEFAULT_PROCESS_TIMEOUT_SECONDS = 15 * 60
NOT_FOUND_RETURNCODE = 127
TIMEOUT_RETURNCODE = 124


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of one subprocess invocation."""

    argv: Tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the process exited cleanly."""

        return self.returncode == 0

    def tail(self) -> str:
        """Return the last non-empty output line without copying the whole buffer."""

        return _tail_line(self.stderr) or _tail_line(self.stdout)

    def to_dict(self) -> Dict[str, object]:
        """Serialize the result."""

        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "ok": self.ok,
        }


ProcessRunner = Callable[[Sequence[str], str, int], ProcessResult]


def run_process(
    argv: Sequence[str],
    cwd: Union[str, Path],
    timeout_seconds: int = DEFAULT_PROCESS_TIMEOUT_SECONDS,
) -> ProcessResult:
    """Run one command, mapping a missing binary and a timeout onto exit codes."""

    frozen_argv = tuple(argv)
    try:
        completed = subprocess.run(
            list(frozen_argv),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return ProcessResult(argv=frozen_argv, returncode=NOT_FOUND_RETURNCODE, stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            argv=frozen_argv,
            returncode=TIMEOUT_RETURNCODE,
            stderr="timed out after {0}s".format(exc.timeout),
        )
    return ProcessResult(
        argv=frozen_argv,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def resolve_runner(runner: Optional[ProcessRunner]) -> ProcessRunner:
    """Return the injected runner or the default subprocess runner."""

    return runner or run_process


def _tail_line(text: str) -> str:
    end = len(text)
    while end > 0 and text[end - 1] in "\r\n":
        end -= 1
    if end == 0:
        return ""
    start = text.rfind("\n", 0, end) + 1
    return text[start:end].strip()
