"""Append-only lineage recorder.

Lineage is append-only observability metadata. It never feeds runtime decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Tuple


class LineageValidationError(ValueError):
    """Raised when a lineage entry violates the fixed schema."""


class LineageAppendError(RuntimeError):
    """Raised when append-only verification fails after a write."""


_REQUIRED_FIELDS = (
    "generation",
    "parent_session",
    "successor_session",
    "timestamp",
    "inherited_role",
    "succession_reason",
    "recovery_sources",
    "inherited_open_tracks",
    "verification",
    "repeated_question_count",
    "reopened_decision_count",
    "context_loss_summary",
    "predecessor_retirement_verified",
)
_TEXT_FIELDS = (
    "parent_session",
    "successor_session",
    "timestamp",
    "inherited_role",
    "succession_reason",
    "recovery_sources",
    "inherited_open_tracks",
    "context_loss_summary",
    "predecessor_retirement_verified",
)
_COUNT_FIELDS = (
    "generation",
    "repeated_question_count",
    "reopened_decision_count",
)
_VERIFICATION_VALUES = ("PASS", "PARTIAL", "FAILED")

_FIELD_LABELS = (
    ("generation", "Generation"),
    ("parent_session", "Parent Session"),
    ("successor_session", "Successor Session"),
    ("timestamp", "Timestamp"),
    ("inherited_role", "Inherited Role"),
    ("succession_reason", "Succession reason"),
    ("recovery_sources", "Recovery sources"),
    ("inherited_open_tracks", "Inherited open tracks"),
    ("verification", "Verification"),
    ("repeated_question_count", "Repeated-question count"),
    ("reopened_decision_count", "Reopened-decision count"),
    ("context_loss_summary", "Context-loss summary"),
    ("predecessor_retirement_verified", "Predecessor retirement verified"),
    ("notes", "Notes"),
)


def append_entry(path: Path, entry: Mapping[str, object]) -> None:
    """Validate and append one lineage entry to a markdown ledger."""

    _validate_entry(entry)
    lineage_path = Path(path)
    original = _read_bytes(lineage_path)
    generation = entry["generation"]

    if _generation_exists(original, generation):
        raise LineageValidationError(f"generation already exists: {generation}")

    section = _render_section(entry, has_existing_content=bool(original)).encode("utf-8")

    try:
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        with lineage_path.open("ab") as lineage_file:
            lineage_file.write(section)

        updated = lineage_path.read_bytes()
        if updated != original + section:
            raise LineageAppendError("lineage append-only verification failed")
    except Exception:
        _restore_bytes(lineage_path, original)
        raise


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""


def _restore_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _validate_entry(entry: Mapping[str, object]) -> None:
    if not isinstance(entry, Mapping):
        raise LineageValidationError("lineage entry must be a mapping")

    for field in _REQUIRED_FIELDS:
        if field not in entry:
            raise LineageValidationError(f"missing lineage field: {field}")

    for field in _COUNT_FIELDS:
        value = entry[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise LineageValidationError(f"lineage field must be int: {field}")
        if field != "generation" and value < 0:
            raise LineageValidationError(f"lineage count must be non-negative: {field}")

    if entry["generation"] < 0:
        raise LineageValidationError("generation must be non-negative")

    for field in _TEXT_FIELDS:
        if not isinstance(entry[field], str):
            raise LineageValidationError(f"lineage field must be str: {field}")

    verification = entry["verification"]
    if verification not in _VERIFICATION_VALUES:
        raise LineageValidationError(f"unknown verification value: {verification}")

    if "notes" in entry and not isinstance(entry["notes"], str):
        raise LineageValidationError("lineage field must be str: notes")


def _generation_exists(content: bytes, generation: object) -> bool:
    marker = ("- **Generation**: %s" % generation).encode("utf-8")
    return marker in content


def _render_section(entry: Mapping[str, object], has_existing_content: bool) -> str:
    lines = [
        "## Gen %s — %s" % (entry["generation"], entry["timestamp"]),
        "",
    ]

    for key, label in _FIELD_LABELS:
        if key == "notes" and key not in entry:
            continue
        lines.append("- **%s**: %s" % (label, _render_value(key, entry[key])))

    section = "\n".join(lines) + "\n"
    if has_existing_content:
        return "\n\n" + section
    return section


def _render_value(key: str, value: object) -> object:
    if key == "verification":
        return "**%s**" % value
    return value


__all__: Tuple[str, ...] = (
    "LineageAppendError",
    "LineageValidationError",
    "append_entry",
)
