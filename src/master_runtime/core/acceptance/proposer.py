"""Single seam for invoking a candidate proposer.

Every model call in the acceptance loop goes through :func:`invoke_cli_proposer`.
The loop itself never imports a vendor SDK and never reads an API key: proposers are
subscription CLIs driven as subprocesses, so tests replace this one function.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Tuple, Union


DEFAULT_PROPOSER_TIMEOUT_SECONDS = 30 * 60
CLAUDE_RUNTIME = "claude"
CODEX_RUNTIME = "codex"
CURSOR_RUNTIME = "cursor-agent"
SUPPORTED_RUNTIMES = (CLAUDE_RUNTIME, CODEX_RUNTIME, CURSOR_RUNTIME)


class ProposerError(RuntimeError):
    """Raised when a proposer runtime cannot be built or invoked."""


@dataclass(frozen=True)
class ProposerRequest:
    """One candidate-proposal invocation."""

    runtime: str
    prompt: str
    cwd: Union[str, Path]
    model: Optional[str] = None
    timeout_seconds: int = DEFAULT_PROPOSER_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ProposerResult:
    """Raw outcome of one proposer invocation."""

    runtime: str
    argv: Tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the proposer exited cleanly."""

        return self.returncode == 0

    def detail(self) -> str:
        """Return the most useful single-line failure detail."""

        return (
            self.stderr.strip()
            or self.stdout.strip()
            or "proposer exited with {0}".format(self.returncode)
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialize the result."""

        return {
            "runtime": self.runtime,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "ok": self.ok,
        }


CliRunner = Callable[[Sequence[str], str, int], ProposerResult]


def build_proposer_argv(
    runtime: str,
    prompt: str,
    model: Optional[str] = None,
) -> Tuple[str, ...]:
    """Return the subscription-CLI argv for one proposer runtime.

    The prompt is always passed as a single argv element, never through a shell.
    """

    normalized = (runtime or "").strip().lower()
    if not prompt.strip():
        raise ProposerError("proposer prompt is empty")

    if normalized == CLAUDE_RUNTIME:
        argv = [CLAUDE_RUNTIME, "-p", prompt]
        if model:
            argv.extend(["--model", model])
        return tuple(argv)

    if normalized == CODEX_RUNTIME:
        argv = [CODEX_RUNTIME, "exec"]
        if model:
            argv.extend(["--model", model])
        argv.append(prompt)
        return tuple(argv)

    if normalized == CURSOR_RUNTIME:
        argv = [CURSOR_RUNTIME, "-p", "--trust", "--force"]
        if model:
            argv.extend(["--model", model])
        argv.append(prompt)
        return tuple(argv)

    raise ProposerError(
        "unsupported proposer runtime {0!r}; expected one of {1}".format(
            runtime, ", ".join(SUPPORTED_RUNTIMES)
        )
    )


def default_cli_runner(
    argv: Sequence[str],
    cwd: str,
    timeout_seconds: int,
) -> ProposerResult:
    """Run one proposer CLI as a subprocess."""

    runtime = argv[0] if argv else ""
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return ProposerResult(runtime=runtime, argv=tuple(argv), returncode=127, stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return ProposerResult(
            runtime=runtime,
            argv=tuple(argv),
            returncode=124,
            stderr="proposer timed out after {0}s".format(exc.timeout),
        )
    return ProposerResult(
        runtime=runtime,
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def invoke_cli_proposer(
    request: ProposerRequest,
    runner: Optional[CliRunner] = None,
) -> ProposerResult:
    """Invoke one proposer runtime. This is the only model call in the loop."""

    argv = build_proposer_argv(request.runtime, request.prompt, request.model)
    run = runner or default_cli_runner
    return run(argv, str(request.cwd), request.timeout_seconds)
