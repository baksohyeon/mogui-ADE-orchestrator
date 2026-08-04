"""Workspace track ledger and session cache."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class TrackState:
    """Current replayed state for one workspace track."""

    track_id: str
    title: str
    refs: Tuple[str, ...] = ()
    status: str = "REGISTERED"
    note: str = ""
    resolution: Optional[str] = None
    registered_at: float = 0.0
    updated_at: float = 0.0
    closed_at: Optional[float] = None


class WorkLedger(ABC):
    """Durable source of truth for workspace track state."""

    @abstractmethod
    def register_track(
        self,
        track_id: str,
        title: str,
        refs: Sequence[str],
    ) -> TrackState:
        """Append a track registration event and return replayed state."""

    @abstractmethod
    def update_track(self, track_id: str, status: str, note: str) -> TrackState:
        """Append a track update event and return replayed state."""

    @abstractmethod
    def close_track(self, track_id: str, resolution: str) -> TrackState:
        """Append a track close event and return replayed state."""

    @abstractmethod
    def active_tracks(self) -> Mapping[str, TrackState]:
        """Return non-closed tracks derived from replay."""


class JsonlWorkLedger(WorkLedger):
    """Append-only JSONL work ledger.

    Each line is one JSON object with a float epoch ``ts`` and an ``event``
    value of ``register``, ``update``, or ``close``.
    """

    def __init__(
        self,
        ledger_path: Union[str, Path],
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self._clock = clock or time.time
        self._warnings = ()

    @property
    def warnings(self) -> Tuple[str, ...]:
        return self._warnings

    def register_track(
        self,
        track_id: str,
        title: str,
        refs: Sequence[str],
    ) -> TrackState:
        tracks = self._replay()
        if track_id in tracks and tracks[track_id].status != "CLOSED":
            raise ValueError("track already active: {0}".format(track_id))
        if not track_id:
            raise ValueError("track_id is required")
        if not title:
            raise ValueError("title is required")

        event = {
            "ts": float(self._clock()),
            "event": "register",
            "track_id": track_id,
            "title": title,
            "refs": list(refs),
        }
        self._append_event(event)
        return self._replay()[track_id]

    def update_track(self, track_id: str, status: str, note: str) -> TrackState:
        current = self._active_track(track_id)
        if not status:
            raise ValueError("status is required")

        event = {
            "ts": float(self._clock()),
            "event": "update",
            "track_id": current.track_id,
            "status": status,
            "note": note,
        }
        self._append_event(event)
        return self._replay()[track_id]

    def close_track(self, track_id: str, resolution: str) -> TrackState:
        current = self._active_track(track_id)
        if not resolution:
            raise ValueError("resolution is required")

        event = {
            "ts": float(self._clock()),
            "event": "close",
            "track_id": current.track_id,
            "resolution": resolution,
        }
        self._append_event(event)
        return self._replay()[track_id]

    def active_tracks(self) -> Mapping[str, TrackState]:
        return {
            track_id: track
            for track_id, track in self._replay().items()
            if track.status != "CLOSED"
        }

    def tracks(self) -> Mapping[str, TrackState]:
        return dict(self._replay())

    def _active_track(self, track_id: str) -> TrackState:
        tracks = self._replay()
        current = tracks.get(track_id)
        if current is None or current.status == "CLOSED":
            raise ValueError("unknown track: {0}".format(track_id))
        return current

    def _append_event(self, event: Mapping[str, object]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
            ledger.write("\n")

    def _replay(self) -> Dict[str, TrackState]:
        tracks: Dict[str, TrackState] = {}
        warnings = []
        for line_number, event in self._read_events(warnings):
            kind = _string_or_none(event.get("event"))
            track_id = _string_or_none(event.get("track_id"))
            if kind is None or track_id is None:
                warnings.append("line {0}: missing event or track_id".format(line_number))
                continue

            ts = _float_or_zero(event.get("ts"))
            if kind == "register":
                title = _string_or_none(event.get("title"))
                if title is None:
                    warnings.append("line {0}: missing title".format(line_number))
                    continue
                tracks[track_id] = TrackState(
                    track_id=track_id,
                    title=title,
                    refs=tuple(_string_items(event.get("refs"))),
                    registered_at=ts,
                    updated_at=ts,
                )
            elif kind == "update":
                current = tracks.get(track_id)
                if current is None or current.status == "CLOSED":
                    warnings.append("line {0}: update for unknown track".format(line_number))
                    continue
                tracks[track_id] = replace(
                    current,
                    status=_string_or_none(event.get("status")) or current.status,
                    note=_string_or_none(event.get("note")) or "",
                    updated_at=ts,
                )
            elif kind == "close":
                current = tracks.get(track_id)
                if current is None or current.status == "CLOSED":
                    warnings.append("line {0}: close for unknown track".format(line_number))
                    continue
                tracks[track_id] = replace(
                    current,
                    status="CLOSED",
                    resolution=_string_or_none(event.get("resolution")) or "",
                    updated_at=ts,
                    closed_at=ts,
                )
            else:
                warnings.append("line {0}: unknown event {1}".format(line_number, kind))
        self._warnings = tuple(warnings)
        return tracks

    def _read_events(
        self,
        warnings: list,
    ) -> Iterable[Tuple[int, Mapping[str, object]]]:
        if not self.ledger_path.exists():
            return

        with self.ledger_path.open("r", encoding="utf-8") as ledger:
            for line_number, raw_line in enumerate(ledger, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError as exc:
                    warnings.append(
                        "line {0}: invalid JSON ({1})".format(line_number, exc)
                    )
                    continue
                if not isinstance(event, dict):
                    warnings.append("line {0}: event is not an object".format(line_number))
                    continue
                yield line_number, event


class WorkspaceRuntime:
    """Session L1 cache derived from the work ledger."""

    def __init__(self, ledger: WorkLedger) -> None:
        self.ledger = ledger
        self._active_tracks = dict(ledger.active_tracks())

    def refresh(self) -> Mapping[str, TrackState]:
        self._active_tracks = dict(self.ledger.active_tracks())
        return self.active_tracks()

    def register_track(
        self,
        track_id: str,
        title: str,
        refs: Sequence[str],
    ) -> TrackState:
        state = self.ledger.register_track(track_id, title, refs)
        self._active_tracks[track_id] = state
        return state

    def update_track(self, track_id: str, status: str, note: str) -> TrackState:
        state = self.ledger.update_track(track_id, status, note)
        self._active_tracks[track_id] = state
        return state

    def close_track(self, track_id: str, resolution: str) -> TrackState:
        state = self.ledger.close_track(track_id, resolution)
        self._active_tracks.pop(track_id, None)
        return state

    def active_tracks(self) -> Mapping[str, TrackState]:
        return dict(self._active_tracks)

    def tracks(self) -> Mapping[str, TrackState]:
        tracks = getattr(self.ledger, "tracks", None)
        if tracks is None:
            return dict(self._active_tracks)
        return dict(tracks())


def _string_or_none(value: object) -> Optional[str]:
    if isinstance(value, str):
        return value
    return None


def _string_items(value: object) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _float_or_zero(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


@dataclass(frozen=True)
class DispatchReapState:
    """State of one dispatch for reap observability."""

    dispatch_id: str
    task_id: str
    status: str
    reaped_at: Optional[float] = None
    is_reaped: bool = False

    def is_unreaped_settled(self) -> bool:
        """True if dispatch is settled but has no reap record."""
        settled = self.status in ("COMPLETED", "ACCEPTED", "FAILED", "ABANDONED")
        return settled and not self.is_reaped


class ReapObservability:
    """Detect unreaped settled leases and track reap status."""

    def __init__(self, ledger_path: Union[str, Path]) -> None:
        self.ledger_path = Path(ledger_path)

    def unreaped_settled_leases(self) -> Mapping[str, DispatchReapState]:
        """Find all settled dispatches with no reap record."""
        dispatch_states: Dict[str, DispatchReapState] = {}

        if not self.ledger_path.exists():
            return dispatch_states

        with self.ledger_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                event_type = event.get("event")
                dispatch_id = event.get("dispatch_id")
                if not dispatch_id:
                    continue

                if event_type == "dispatch_submitted":
                    dispatch_states[dispatch_id] = DispatchReapState(
                        dispatch_id=dispatch_id,
                        task_id=str(event.get("task_id", "")),
                        status=str(event.get("status", "UNKNOWN")),
                        is_reaped=False,
                    )
                elif event_type == "dispatch_completed":
                    current = dispatch_states.get(dispatch_id)
                    if current:
                        dispatch_states[dispatch_id] = replace(
                            current,
                            status=str(event.get("status", "COMPLETED")),
                        )
                elif event_type == "reap":
                    if dispatch_id in dispatch_states:
                        current = dispatch_states[dispatch_id]
                        dispatch_states[dispatch_id] = replace(
                            current,
                            is_reaped=True,
                            reaped_at=float(event.get("ts", 0.0)),
                        )

        return {
            did: state
            for did, state in dispatch_states.items()
            if state.is_unreaped_settled()
        }
