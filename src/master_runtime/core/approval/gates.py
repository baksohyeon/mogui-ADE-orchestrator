"""Approval gate classification primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateClass(str, Enum):
    """Approval gate classes ordered by required authority."""

    G0_READ_ONLY = "G0_READ_ONLY"
    G1_REVERSIBLE_LOCAL = "G1_REVERSIBLE_LOCAL"
    G2_SHARED_STATE = "G2_SHARED_STATE"
    G3_IRREVERSIBLE = "G3_IRREVERSIBLE"


@dataclass(frozen=True)
class ActionSpec:
    """Action facts used to classify required approval."""

    read_only: bool
    writes_local: bool
    writes_shared: bool
    irreversible: bool
    description: str


def classify(action: ActionSpec) -> GateClass:
    """Classify an action into the strictest required approval gate."""

    if action.read_only and (
        action.writes_local or action.writes_shared or action.irreversible
    ):
        raise ValueError("read_only actions cannot write or be irreversible")

    if action.irreversible:
        return GateClass.G3_IRREVERSIBLE
    if action.writes_shared:
        return GateClass.G2_SHARED_STATE
    if action.writes_local:
        return GateClass.G1_REVERSIBLE_LOCAL
    return GateClass.G0_READ_ONLY
