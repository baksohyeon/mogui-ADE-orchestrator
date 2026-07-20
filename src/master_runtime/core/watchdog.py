"""Watchdog helpers for polling worker progress logs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union


class StallStatus(str, Enum):
    """Possible watchdog outcomes."""

    OK = "OK"
    STALLED = "STALLED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class StallDecision:
    """Result of a stall check."""

    status: StallStatus
    idle_seconds: float | None
    last_progress_at: float | None
    reason: str

    @property
    def stalled(self) -> bool:
        """Return whether the worker should be treated as stalled."""

        return self.status == StallStatus.STALLED


ProgressPredicate = Callable[[str], Optional[Union[bool, int, float, datetime]]]


def check_stall(
    log_path: str | Path,
    max_idle_seconds: int = 360,
    progress_predicate: ProgressPredicate | None = None,
    now: Callable[[], float] | float | None = None,
) -> StallDecision:
    """Check whether a progress log is idle beyond the configured threshold."""

    current_time = _resolve_now(now)
    path = Path(log_path)
    if not path.exists():
        return StallDecision(
            status=StallStatus.MISSING,
            idle_seconds=None,
            last_progress_at=None,
            reason="LOG_MISSING",
        )

    last_progress_at = path.stat().st_mtime
    if progress_predicate is not None:
        parsed_progress_times = _progress_times(path, progress_predicate)
        if parsed_progress_times:
            last_progress_at = max(parsed_progress_times)

    idle_seconds = current_time - last_progress_at
    if idle_seconds > max_idle_seconds:
        return StallDecision(
            status=StallStatus.STALLED,
            idle_seconds=idle_seconds,
            last_progress_at=last_progress_at,
            reason="STALLED",
        )

    return StallDecision(
        status=StallStatus.OK,
        idle_seconds=idle_seconds,
        last_progress_at=last_progress_at,
        reason="OK",
    )


def _progress_times(
    log_path: Path,
    progress_predicate: ProgressPredicate,
) -> tuple[float, ...]:
    times: list[float] = []
    with log_path.open("r", encoding="utf-8") as log:
        for line in log:
            marker = progress_predicate(line)
            timestamp = _coerce_timestamp(marker)
            if timestamp is not None:
                times.append(timestamp)
    return tuple(times)


def _coerce_timestamp(marker: bool | int | float | datetime | None) -> float | None:
    if isinstance(marker, datetime):
        return marker.timestamp()
    if isinstance(marker, bool):
        return None
    if isinstance(marker, (int, float)):
        return float(marker)
    return None


def _resolve_now(now: Callable[[], float] | float | None) -> float:
    if now is None:
        return time.time()
    if callable(now):
        return float(now())
    return float(now)
