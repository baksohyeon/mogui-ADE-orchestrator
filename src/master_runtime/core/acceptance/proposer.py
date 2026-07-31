"""Single seam for invoking a candidate proposer.

Every model call in the acceptance loop goes through :func:`invoke_cli_proposer`. The
loop never imports a vendor SDK and never reads an API key: proposers are subscription
CLIs driven as subprocesses, so tests replace this one function.

Which CLIs exist and what flags they take is not decided here. That lives behind
``core/adapter``'s ``SyncCliProfile``, and :func:`require_sync_cli_profile` is the single
place a runtime name is accepted or rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

from master_runtime.core.acceptance.process import (
    DEFAULT_PROCESS_TIMEOUT_SECONDS,
    ProcessResult,
    ProcessRunner,
    resolve_runner,
)
from master_runtime.core.adapter.profile import (
    SyncCliProfile,
    resolve_sync_cli_profile,
    sync_cli_runtimes,
)


DEFAULT_PROPOSER_TIMEOUT_SECONDS = 30 * 60


class ProposerError(RuntimeError):
    """Raised when a proposer runtime cannot be resolved or invoked."""


@dataclass(frozen=True)
class ProposerRequest:
    """One candidate-proposal invocation."""

    runtime: str
    prompt: str
    cwd: Union[str, Path]
    model: Optional[str] = None
    timeout_seconds: int = DEFAULT_PROPOSER_TIMEOUT_SECONDS


def require_sync_cli_profile(runtime: str) -> SyncCliProfile:
    """Resolve one runtime name to its CLI profile, or fail with the known names."""

    profile = resolve_sync_cli_profile(runtime)
    if profile is None:
        raise ProposerError(
            "unsupported proposer runtime {0!r}; expected one of {1}".format(
                runtime, ", ".join(sync_cli_runtimes())
            )
        )
    return profile


def build_proposer_argv(
    runtime: str,
    prompt: str,
    model: Optional[str] = None,
) -> Tuple[str, ...]:
    """Return the subscription-CLI argv for one proposer runtime.

    The prompt is always passed as a single argv element, never through a shell.
    """

    if not prompt.strip():
        raise ProposerError("proposer prompt is empty")
    return tuple(require_sync_cli_profile(runtime).build_argv(prompt, model))


def invoke_cli_proposer(
    request: ProposerRequest,
    runner: Optional[ProcessRunner] = None,
) -> ProcessResult:
    """Invoke one proposer runtime. This is the only model call in the loop."""

    argv = build_proposer_argv(request.runtime, request.prompt, request.model)
    timeout_seconds = request.timeout_seconds or DEFAULT_PROCESS_TIMEOUT_SECONDS
    return resolve_runner(runner)(argv, str(request.cwd), timeout_seconds)
