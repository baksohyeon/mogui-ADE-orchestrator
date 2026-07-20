"""Live wiring for the master bootstrap SessionStart hook.

Reuses the U1 bootstrap Role State parser and dual-instance detection to
emit a small dynamic block (~1KB) at master session boot. This module
never re-publishes memory bodies; it only audits the bd prime block.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from master_runtime.core.bootstrap import _role_state_block


def latest_handoff(handoff_dir: Path) -> Optional[Path]:
    """Return the lexicographically greatest ``*.md`` handoff, or None."""

    directory = Path(handoff_dir)
    try:
        candidates = [p for p in directory.glob("*.md") if p.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def load_role_state(handoff_dir: Path) -> Tuple[Optional[str], List[str]]:
    """Load the Role State block from the latest handoff.

    Returns ``(block_text, alerts)``. On any absence or parse failure the
    block is ``None`` and a ``[AUDIT-ALERT] role-state: <reason>`` line is
    appended to ``alerts``.
    """

    alerts: List[str] = []
    path = latest_handoff(handoff_dir)
    if path is None:
        alerts.append("[AUDIT-ALERT] role-state: handoff 부재 (" + str(handoff_dir) + ")")
        return None, alerts

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        alerts.append("[AUDIT-ALERT] role-state: 읽기 실패 " + exc.__class__.__name__)
        return None, alerts

    block = _role_state_block(text)
    if block is None:
        alerts.append("[AUDIT-ALERT] role-state: Role State 블록 없음 (" + path.name + ")")
        return None, alerts

    return block, alerts
