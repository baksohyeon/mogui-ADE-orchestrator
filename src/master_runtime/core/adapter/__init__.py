"""Adapter layer public API."""

from master_runtime.core.adapter.dispatch import (
    DispatchOutcome,
    DispatchRequest,
    dispatch as run_dispatch,
)
from master_runtime.core.adapter.doctor import (
    CheckResult,
    DoctorReport,
    ProbeCheck,
    RunResult,
    doctor as run_doctor,
)
from master_runtime.core.adapter.isolation import (
    IsolationDecision,
    IsolationMode,
    needs_worktree,
)
from master_runtime.core.adapter.profile import (
    CodexCompanionProfile,
    ProfileError,
    ToolProfile,
)

__all__ = [
    "CheckResult",
    "CodexCompanionProfile",
    "DispatchOutcome",
    "DispatchRequest",
    "DoctorReport",
    "IsolationDecision",
    "IsolationMode",
    "ProbeCheck",
    "ProfileError",
    "RunResult",
    "ToolProfile",
    "needs_worktree",
    "run_dispatch",
    "run_doctor",
]
