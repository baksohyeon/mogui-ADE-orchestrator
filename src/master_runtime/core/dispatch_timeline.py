"""Join the ledger, the event log, and the live dispatch-show record for one dispatch.

Three sources, three different shapes, one time-ordered table:
- the dispatch ledger (``~/.mogui/dispatch-ledger.jsonl``), rows keyed on
  ``job_id``/``orchestration_task`` (dispatch-gate register, host-diversity
  audits) or ``dispatch_id``/``task_id`` (worker-reap's reap records)
- the event log (``~/.mogui/event-log.jsonl``), lines keyed on
  ``dispatch_id``/``task_id`` when known
- ``orca orchestration dispatch-show``, the current snapshot, not a series

A source with zero matching rows is named in ``missing_sources`` rather than
silently absent from the table: the contract this module exists for was
written because a prior tool's silence looked identical to "nothing
happened" and "I could not check."
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from master_runtime.core.worker_reap import resolve_task_id_from_dispatch_id


LEDGER_SOURCE = "ledger"
EVENT_LOG_SOURCE = "event-log"
DISPATCH_SHOW_SOURCE = "dispatch-show"
ALL_SOURCES = (LEDGER_SOURCE, EVENT_LOG_SOURCE, DISPATCH_SHOW_SOURCE)


@dataclass(frozen=True)
class TimelineRow:
    """One row in the joined, time-ordered table."""

    timestamp: float
    source: str
    event: str
    outcome: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "event": self.event,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Timeline:
    """A joined timeline plus which sources contributed nothing."""

    rows: tuple[TimelineRow, ...]
    missing_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "missing_sources": list(self.missing_sources),
        }


def default_ledger_path() -> Path:
    return Path.home() / ".mogui" / "dispatch-ledger.jsonl"


def default_event_log_path() -> Path:
    return Path.home() / ".mogui" / "event-log.jsonl"


class DispatchTimelineBuilder:
    """Builds a `Timeline` for one dispatch, or a `--since` listing across many."""

    def __init__(
        self,
        orca_runner: Optional[callable] = None,
        ledger_path: Optional[Path] = None,
        event_log_path: Optional[Path] = None,
    ) -> None:
        self.orca_runner = orca_runner or self._run_subprocess
        self.ledger_path = ledger_path or default_ledger_path()
        self.event_log_path = event_log_path or default_event_log_path()

    def build(
        self, task_id: Optional[str] = None, dispatch_id: Optional[str] = None
    ) -> Timeline:
        """Join every source's rows for this task/dispatch into one timeline."""

        if not task_id and not dispatch_id:
            raise ValueError("Either task_id or dispatch_id must be provided")

        rows: list[TimelineRow] = []
        missing: list[str] = []

        ledger_rows = self._ledger_rows_for(task_id, dispatch_id)
        if ledger_rows:
            rows.extend(ledger_rows)
        else:
            missing.append(LEDGER_SOURCE)

        event_rows = self._event_log_rows_for(task_id, dispatch_id)
        if event_rows:
            rows.extend(event_rows)
        else:
            missing.append(EVENT_LOG_SOURCE)

        show_row = self._dispatch_show_row(task_id, dispatch_id)
        if show_row is not None:
            rows.append(show_row)
        else:
            missing.append(DISPATCH_SHOW_SOURCE)

        rows.sort(key=lambda row: row.timestamp)
        return Timeline(rows=tuple(rows), missing_sources=tuple(missing))

    def list_since(self, hours: float) -> list[dict[str, object]]:
        """Every dispatch seen (ledger or event log) in the last `hours`, with its last event."""

        cutoff = time.time() - (hours * 3600)
        last_seen: dict[str, dict[str, object]] = {}

        def _note(dispatch_id: str, task_id: str, ts: float, event: str, outcome: str) -> None:
            if ts < cutoff:
                return
            prior = last_seen.get(dispatch_id)
            if prior is None or ts >= prior["last_ts"]:
                last_seen[dispatch_id] = {
                    "dispatch_id": dispatch_id,
                    "task_id": task_id,
                    "last_event": event,
                    "last_outcome": outcome,
                    "last_ts": ts,
                }

        for entry in _read_jsonl(self.ledger_path):
            dispatch_id = str(entry.get("job_id") or entry.get("dispatch_id") or "")
            if not dispatch_id:
                continue
            task_id = str(entry.get("orchestration_task") or entry.get("task_id") or "")
            ts = _to_epoch(entry.get("ts"))
            if ts is None:
                continue
            event = str(entry.get("kind") or entry.get("event") or entry.get("decision") or "ledger")
            outcome = str(entry.get("decision") or entry.get("event") or "")
            _note(dispatch_id, task_id, ts, event, outcome)

        for entry in _read_jsonl(self.event_log_path):
            dispatch_id = str(entry.get("dispatch_id") or "")
            if not dispatch_id:
                continue
            task_id = str(entry.get("task_id") or "")
            ts = _to_epoch(entry.get("ts"))
            if ts is None:
                continue
            event = str(entry.get("event") or "")
            outcome = str(entry.get("outcome") or "")
            _note(dispatch_id, task_id, ts, event, outcome)

        return sorted(last_seen.values(), key=lambda row: row["last_ts"], reverse=True)

    # --- ledger -----------------------------------------------------------

    def _ledger_rows_for(
        self, task_id: Optional[str], dispatch_id: Optional[str]
    ) -> list[TimelineRow]:
        rows: list[TimelineRow] = []
        for entry in _read_jsonl(self.ledger_path):
            entry_dispatch = str(entry.get("job_id") or entry.get("dispatch_id") or "")
            entry_task = str(entry.get("orchestration_task") or entry.get("task_id") or "")
            if dispatch_id and entry_dispatch != dispatch_id:
                continue
            if not dispatch_id and task_id and entry_task != task_id:
                continue
            if not entry_dispatch and not entry_task:
                continue
            ts = _to_epoch(entry.get("ts"))
            if ts is None:
                continue
            event = str(entry.get("kind") or entry.get("event") or entry.get("decision") or "ledger")
            outcome = str(entry.get("decision") or entry.get("actions_taken") or "")
            rows.append(
                TimelineRow(
                    timestamp=ts,
                    source=LEDGER_SOURCE,
                    event=event,
                    outcome=outcome,
                    detail=json.dumps(entry, sort_keys=True, separators=(",", ":")),
                )
            )
        return rows

    def _dispatch_ids_for_task(self, task_id: str) -> set[str]:
        """Every dispatch id the ledger has linked to this task id."""
        ids: set[str] = set()
        for entry in _read_jsonl(self.ledger_path):
            entry_task = str(entry.get("orchestration_task") or entry.get("task_id") or "")
            if entry_task != task_id:
                continue
            entry_dispatch = str(entry.get("job_id") or entry.get("dispatch_id") or "")
            if entry_dispatch:
                ids.add(entry_dispatch)
        return ids

    # --- event log ----------------------------------------------------------

    def _event_log_rows_for(
        self, task_id: Optional[str], dispatch_id: Optional[str]
    ) -> list[TimelineRow]:
        rows: list[TimelineRow] = []
        # An event carrying only a dispatch id (no task id) still belongs to
        # this task's timeline when the ledger has already linked that
        # dispatch to the requested task.
        linked_dispatch_ids: set[str] = set()
        if not dispatch_id and task_id:
            linked_dispatch_ids = self._dispatch_ids_for_task(task_id)
        for entry in _read_jsonl(self.event_log_path):
            entry_dispatch = str(entry.get("dispatch_id") or "")
            entry_task = str(entry.get("task_id") or "")
            if dispatch_id and entry_dispatch != dispatch_id:
                continue
            if not dispatch_id and task_id:
                matches_task = entry_task == task_id
                matches_linked_dispatch = bool(entry_dispatch) and (
                    entry_dispatch in linked_dispatch_ids
                )
                if not (matches_task or matches_linked_dispatch):
                    continue
            if not entry_dispatch and not entry_task:
                continue
            ts = _to_epoch(entry.get("ts"))
            if ts is None:
                continue
            rows.append(
                TimelineRow(
                    timestamp=ts,
                    source=EVENT_LOG_SOURCE,
                    event=str(entry.get("event") or ""),
                    outcome=str(entry.get("outcome") or ""),
                    detail=json.dumps(entry, sort_keys=True, separators=(",", ":")),
                )
            )
        return rows

    # --- dispatch-show --------------------------------------------------------

    def _dispatch_show_row(
        self, task_id: Optional[str], dispatch_id: Optional[str]
    ) -> Optional[TimelineRow]:
        # dispatch-show only reliably serves the live snapshot by --task;
        # resolve a bare dispatch id to its task id first, the same way
        # worker_reap.py does, rather than passing --dispatch straight through.
        if not task_id and dispatch_id:
            task_id = resolve_task_id_from_dispatch_id(self.orca_runner, dispatch_id)
        cmd = ["orca", "orchestration", "dispatch-show", "--json"]
        if task_id:
            cmd.extend(["--task", task_id])
        elif dispatch_id:
            cmd.extend(["--dispatch", dispatch_id])
        code, stdout, _stderr = self.orca_runner(cmd)
        if code != 0:
            return None
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        result = payload.get("result") if isinstance(payload, dict) else None
        dispatch = result.get("dispatch") if isinstance(result, dict) else None
        if not isinstance(dispatch, dict):
            return None
        status = str(dispatch.get("status", ""))
        # An `or` chain would discard a real epoch-0 timestamp (falsy 0.0)
        # and fall through to the next field, or to "now" — explicit `None`
        # checks so only unparseable values are skipped.
        ts = next(
            (
                candidate
                for candidate in (
                    _to_epoch(dispatch.get("last_heartbeat_at")),
                    _to_epoch(dispatch.get("completed_at")),
                    _to_epoch(dispatch.get("dispatched_at")),
                )
                if candidate is not None
            ),
            time.time(),
        )
        return TimelineRow(
            timestamp=ts,
            source=DISPATCH_SHOW_SOURCE,
            event=f"status:{status}",
            outcome=status,
            detail=json.dumps(dispatch, sort_keys=True, separators=(",", ":")),
        )

    def _run_subprocess(self, command: list[str]) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out: {' '.join(command)}"
        except Exception as e:  # noqa: BLE001 - report, never raise, to the caller
            return 1, "", str(e)


def _read_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _to_epoch(value: object) -> Optional[float]:
    """Accept a unix timestamp (int/float, seconds) or an ISO 8601 string."""

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None
