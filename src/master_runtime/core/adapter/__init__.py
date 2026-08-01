"""Adapter layer public API."""

from master_runtime.core.adapter.doctor import (
    CheckResult,
    DoctorReport,
    ProbeCheck,
    RunResult,
    doctor as run_doctor,
)
from master_runtime.core.adapter.profile import (
    ClaudeCliProfile,
    CodexExecProfile,
    CursorAgentProfile,
    ProfileError,
    SyncCliProfile,
    resolve_sync_cli_profile,
)

__all__ = [
    "CheckResult",
    "ClaudeCliProfile",
    "CodexExecProfile",
    "CursorAgentProfile",
    "DoctorReport",
    "ProbeCheck",
    "ProfileError",
    "RunResult",
    "SyncCliProfile",
    "resolve_sync_cli_profile",
    "run_doctor",
]
