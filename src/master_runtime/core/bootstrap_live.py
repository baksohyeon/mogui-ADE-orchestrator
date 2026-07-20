"""Live wiring for the master bootstrap SessionStart hook.

Reuses the U1 bootstrap Role State parser and dual-instance detection to
emit a small dynamic block (~1KB) at master session boot. This module
never re-publishes memory bodies; it only audits the bd prime block.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from master_runtime.core.bootstrap import _role_state_block


DEFAULT_MEMORY_CAP = 15
DEFAULT_BUDGET_CHARS = 12_000
_BLOCK_SPLIT = re.compile(r"(?m)^### ")


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


def audit_memories(
    memories_text: str,
    cap: int = DEFAULT_MEMORY_CAP,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
) -> Tuple[str, List[str]]:
    """Audit a ``bd prime --memories-only`` block by tier, cap and budget.

    Counts ``### <key>`` blocks and classifies each: ``[L0`` present => L0,
    else ``[L1`` present => L1, else untagged. Never re-emits memory bodies;
    returns a single summary line plus alert lines.
    """

    alerts: List[str] = []
    parts = _BLOCK_SPLIT.split(memories_text)
    blocks = [part for part in parts[1:] if part.strip()]
    count = len(blocks)

    l0 = 0
    l1 = 0
    untagged = 0
    for block in blocks:
        if "[L0" in block:
            l0 += 1
        elif "[L1" in block:
            l1 += 1
        else:
            untagged += 1

    block_chars = len(memories_text)
    block_kb = block_chars / 1024.0
    budget_kb = round(budget_chars / 1000.0)

    if untagged > 0:
        alerts.append("[AUDIT-ALERT] untagged 메모리 " + str(untagged) + "건")
    if count > cap:
        alerts.append("[AUDIT-ALERT] cap 초과: " + str(count) + " > " + str(cap))
    if block_chars > budget_chars:
        alerts.append(
            "[BUDGET-ALERT] bd-prime 블록 "
            + str(block_chars)
            + " chars > "
            + str(budget_chars)
        )

    status = "ALERT" if alerts else "OK"
    line = (
        "[BD-PRIME-AUDIT] memories="
        + str(count)
        + " (L0="
        + str(l0)
        + ", L1="
        + str(l1)
        + ", untagged="
        + str(untagged)
        + "), block="
        + ("%.1f" % block_kb)
        + "KB — "
        + status
        + " (budget "
        + str(budget_kb)
        + "KB)"
    )
    return line, alerts
