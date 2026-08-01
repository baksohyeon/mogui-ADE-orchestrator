"""Tool-neutral worker profile contracts."""

import abc
import json
import os
import re
from typing import Dict, List, Optional, Tuple




class ProfileError(Exception):
    """Raised when a tool profile cannot build or parse its contract."""



class SyncCliProfile(abc.ABC):
    """Neutral interface for a synchronous one-shot CLI worker runtime.

    Subscription CLIs run to completion in the foreground and return no job id.
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
