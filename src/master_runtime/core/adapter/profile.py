"""Tool-neutral worker profile contracts."""

import abc
import json
import os
import re
from typing import List


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
