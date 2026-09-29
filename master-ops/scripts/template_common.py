"""Shared constants for template-check and template-apply.

Import from sibling scripts so refusal names and placeholders cannot drift.

The changelog fragment name grammar below is the canonical copy. The two
repo-root changelog scripts outside this template tree cannot import this
module without a sys.path hack across the template boundary, so they each
keep a string-identical duplicate instead; tests/test_changelog_release.py
asserts the duplicates match this pattern.
"""

from __future__ import annotations

import re
from datetime import date

FRAGMENT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.md$")


def parse_fragment_date(name: str) -> date:
    """Return a fragment file name's date, or raise ValueError if invalid."""
    match = FRAGMENT_NAME_RE.match(name)
    if not match:
        raise ValueError(f"bad fragment name: {name}")
    return date.fromisoformat(match.group(1))


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
