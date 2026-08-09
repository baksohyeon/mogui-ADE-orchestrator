"""Structured error types and exit-code vocabulary for mogui scripts."""

from dataclasses import dataclass, field


EXIT_PASS, EXIT_FINDING, EXIT_UNDETERMINED = 0, 1, 2


@dataclass
class MoguiError(Exception):
    """Harness error carrying the fields needed by the structured log."""

    event: str
    reason: str
    level: str = "error"
    component: str = "tool-impl"
    evidence: str = "observed"
    exit_code: int = EXIT_FINDING
    context: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.event}: {self.reason}"


class GateDenied(MoguiError):
    """A measured violation: the gate found a reason to deny (exit 1)."""

    def __init__(self, event, reason, **kwargs):
        super().__init__(event=event, reason=reason, exit_code=EXIT_FINDING, **kwargs)


class Undetermined(MoguiError):
    """The measurement could not establish an outcome (exit 2)."""

    def __init__(self, event, reason, **kwargs):
        kwargs.setdefault("evidence", "unknown")
        super().__init__(event=event, reason=reason,
                         level="warn", exit_code=EXIT_UNDETERMINED, **kwargs)


class StateIntegrityError(MoguiError):
    """A state-integrity failure is fatal and therefore undetermined (exit 2)."""

    def __init__(self, event, reason, **kwargs):
        super().__init__(event=event, reason=reason,
                         level="fatal", exit_code=EXIT_UNDETERMINED, **kwargs)
