"""Worktree isolation decision helper."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class IsolationMode(str, Enum):
    SHARED = "shared"
    WORKTREE = "worktree"


@dataclass(frozen=True)
class IsolationDecision:
    mode: IsolationMode
    reasons: Tuple[str, ...]


def needs_worktree(
    parallel_writes: bool,
    branch_anchor: Optional[str],
    tree_contention: bool,
    branch_switch: bool,
) -> IsolationDecision:
    reasons = []
    if parallel_writes:
        reasons.append("parallel_writes")
    if branch_anchor:
        reasons.append("branch_anchor")
    if tree_contention:
        reasons.append("tree_contention")
    if branch_switch:
        reasons.append("branch_switch")

    if not reasons:
        return IsolationDecision(mode=IsolationMode.SHARED, reasons=())
    return IsolationDecision(mode=IsolationMode.WORKTREE, reasons=tuple(reasons))

