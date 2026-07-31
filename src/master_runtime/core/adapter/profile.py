"""Tool-neutral worker profile contracts."""

import abc
import json
import os
import re
from typing import Dict, List, Optional, Tuple


DEFAULT_CODEX_COMPANION_MJS = "~/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/codex-companion.mjs"


class ProfileError(Exception):
    """Raised when a tool profile cannot build or parse its contract."""


class ToolProfile(abc.ABC):
    """Neutral interface for a worker runtime profile."""

    @abc.abstractmethod
    def build_worker_cmd(self, contract_path: str, cwd: str) -> List[str]:
        """Return the command that starts a worker for a contract."""

    @abc.abstractmethod
    def build_probe_cmd(self, job_id: str, cwd: str) -> List[str]:
        """Return the command that probes a dispatched job."""

    @abc.abstractmethod
    def parse_job_id(self, stdout: str) -> str:
        """Extract a worker job id from worker stdout."""


class SyncCliProfile(abc.ABC):
    """Neutral interface for a synchronous one-shot CLI worker runtime.

    ``ToolProfile`` covers asynchronous dispatch, where a worker returns a job id that
    is probed later. Subscription CLIs run to completion in the foreground and have no
    job id, so they get their own contract instead of being forced into that shape.
    Every vendor flag lives behind this interface, never in the calling core module.
    """

    name = ""

    @abc.abstractmethod
    def build_argv(self, prompt: str, model: Optional[str] = None) -> List[str]:
        """Return the argv that runs one prompt to completion."""


class ClaudeCliProfile(SyncCliProfile):
    """Reference profile for the Claude Code CLI."""

    name = "claude"

    def build_argv(self, prompt: str, model: Optional[str] = None) -> List[str]:
        argv = [self.name, "-p", prompt]
        if model:
            argv.extend(["--model", model])
        return argv


class CodexExecProfile(SyncCliProfile):
    """Reference profile for the Codex CLI in one-shot exec mode."""

    name = "codex"

    def build_argv(self, prompt: str, model: Optional[str] = None) -> List[str]:
        argv = [self.name, "exec"]
        if model:
            argv.extend(["--model", model])
        argv.append(prompt)
        return argv


class CursorAgentProfile(SyncCliProfile):
    """Reference profile for the Cursor agent CLI."""

    name = "cursor-agent"

    def build_argv(self, prompt: str, model: Optional[str] = None) -> List[str]:
        argv = [self.name, "-p", "--trust", "--force"]
        if model:
            argv.extend(["--model", model])
        argv.append(prompt)
        return argv


SYNC_CLI_PROFILES: Dict[str, SyncCliProfile] = {
    profile.name: profile
    for profile in (ClaudeCliProfile(), CodexExecProfile(), CursorAgentProfile())
}


def resolve_sync_cli_profile(runtime: str) -> Optional[SyncCliProfile]:
    """Return the profile for one runtime name, or None when it is unknown."""

    return SYNC_CLI_PROFILES.get((runtime or "").strip().lower())


def sync_cli_runtimes() -> Tuple[str, ...]:
    """Return every known synchronous CLI runtime name."""

    return tuple(sorted(SYNC_CLI_PROFILES))


class CodexCompanionProfile(ToolProfile):
    """Reference profile for a Codex companion mjs runtime."""

    def __init__(self, companion_mjs: str = DEFAULT_CODEX_COMPANION_MJS, node_cmd: str = "node"):
        self.companion_mjs = os.path.expanduser(companion_mjs)
        self.node_cmd = node_cmd

    def build_worker_cmd(self, contract_path: str, cwd: str) -> List[str]:
        return [
            self.node_cmd,
            self.companion_mjs,
            "dispatch",
            "--contract",
            contract_path,
            "--cwd",
            cwd,
        ]

    def build_probe_cmd(self, job_id: str, cwd: str) -> List[str]:
        return [
            self.node_cmd,
            self.companion_mjs,
            "probe",
            "--job-id",
            job_id,
            "--cwd",
            cwd,
        ]

    def parse_job_id(self, stdout: str) -> str:
        text = stdout.strip()
        if not text:
            raise ProfileError("job-id-not-found")

        try:
            payload = json.loads(text)
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            value = payload.get("job_id") or payload.get("jobId") or payload.get("id")
            if isinstance(value, str) and value.strip():
                return value.strip()

        for line in text.splitlines():
            match = re.search(r"\bjob[_-]?id\s*[:=]\s*([A-Za-z0-9_.:-]+)", line)
            if match:
                return match.group(1)

        raise ProfileError("job-id-not-found")
