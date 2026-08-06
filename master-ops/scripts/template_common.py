"""Shared constants for template-check and template-apply.

Import from sibling scripts so refusal names and placeholders cannot drift.
"""

from __future__ import annotations

INSTANCE_OWNED_PREFIXES = (
    "docs/lineage/",
    ".beads/",
    "config/",
    "contracts/",
)
INSTANCE_OWNED_EXACT = frozenset(
    {
        "docs/runbooks/role-state.md",
    }
)

PLACEHOLDERS = (
    "{{WORKSPACE_NAME}}",
    "{{WORKSPACE_ROOT}}",
    "{{OPS_REPO}}",
    "{{MONITOR_NS}}",
    "{{MODEL_ID}}",
    "{{REPO_LIST}}",
    "{{RUNTIME_ROOT}}",
    "{{TEMPLATE_VERSION}}",
)


def is_instance_owned(rel: str) -> bool:
    if rel in INSTANCE_OWNED_EXACT:
        return True
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in INSTANCE_OWNED_PREFIXES)
