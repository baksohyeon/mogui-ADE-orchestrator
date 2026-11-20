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
import subprocess
from datetime import date
from pathlib import Path

FRAGMENT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.md$")
TEMPLATE_VERSION_RE = re.compile(
    r"^v(?P<release>\d+(?:\.\d+){2,})(?:-(?P<distance>\d+)-g(?P<sha>[0-9a-f]+))?$"
)
TEMPLATE_VERSION_VALID_RE = re.compile(
    r"^v[0-9A-Za-z][0-9A-Za-z._-]*(?:-\d+-g[0-9a-f]+)?$"
)


def template_version_is_valid(value: str) -> bool:
    """Return whether a template stamp has a supported release-like form."""
    return TEMPLATE_VERSION_VALID_RE.fullmatch(value.strip()) is not None


def template_version_key(value: str) -> tuple[tuple[int, ...], int] | None:
    """Return the release and commit distance represented by a template stamp."""
    match = TEMPLATE_VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    release = tuple(int(part) for part in match.group("release").split("."))
    distance = int(match.group("distance") or 0)
    return release, distance


def template_version_base(value: str) -> str | None:
    """Return the release tag portion of a valid template stamp."""
    key = template_version_key(value)
    if key is None:
        return value.strip() if template_version_is_valid(value) else None
    release, _ = key
    return "v" + ".".join(str(part) for part in release)


def compare_template_versions(first: str, second: str) -> int | None:
    """Compare release and commit distance, or return None for an unknown form."""
    if first.strip() == second.strip():
        return 0
    first_key = template_version_key(first)
    second_key = template_version_key(second)
    if first_key is None or second_key is None:
        return None
    return (first_key > second_key) - (first_key < second_key)


def resolve_template_version(
    source_root: Path, plain_version: str
) -> tuple[str, str | None]:
    """Resolve the install stamp and a warning when git measurement is unsafe."""
    git_prefix = ["git", "-C", str(source_root)]
    try:
        inside = subprocess.run(
            [*git_prefix, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return plain_version, "git is unavailable; using TEMPLATE-VERSION " + plain_version
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return plain_version, None

    try:
        head = subprocess.run(
            [*git_prefix, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        tag_ref = f"{plain_version}^" + "{" + "commit}"
        tagged_head = subprocess.run(
            [*git_prefix, "rev-parse", tag_ref],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return (
            plain_version,
            "git could not resolve the TEMPLATE-VERSION tag; using TEMPLATE-VERSION "
            + plain_version,
        )

    if head == tagged_head:
        return plain_version, None

    try:
        described = subprocess.run(
            [*git_prefix, "describe", "--tags"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return (
            plain_version,
            "git describe --tags failed; using TEMPLATE-VERSION " + plain_version,
        )
    if not described or not template_version_is_valid(described):
        return (
            plain_version,
            "git describe --tags returned an unusable stamp; using TEMPLATE-VERSION "
            + plain_version,
        )
    return described, None


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
        "AGENTS.md",
        "CLAUDE.md",
        "docs/MASTER-OPERATIONS.md",
        "docs/evals/evidence.instance.json",
        "docs/decisions/closed-decisions-and-facts.md",
        "docs/research/literature/index.csv",
        "docs/runbooks/README.md",
        "docs/runbooks/boot-comparison-set.md",
        "docs/runbooks/role-state.md",
        "docs/runbooks/succession-boot-card.md",
        "scripts/compaction-probe.sh",
        "scripts/harness-selfcheck.sh",
        "workspace-card/LOCAL.md",
    }
)

# Built from split braces so neither template-apply substitution nor the
# step 05 Verify token scan sees a literal placeholder in this file.
def _token(name: str) -> str:
    return "{" "{" + name + "}" "}"


PLACEHOLDERS = (
    _token("WORKSPACE_NAME"),
    _token("WORKSPACE_ROOT"),
    _token("OPS_REPO"),
    _token("MONITOR_NS"),
    _token("MODEL_ID"),
    _token("REPO_LIST"),
    _token("RUNTIME_ROOT"),
    _token("TEMPLATE_VERSION"),
)

# Copied byte-identical. Substitution would destroy PLACEHOLDERS.
SKIP_SUBSTITUTE_PATHS = frozenset(
    {
        "scripts/template_common.py",
    }
)


def is_instance_owned(rel: str) -> bool:
    if rel in INSTANCE_OWNED_EXACT:
        return True
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in INSTANCE_OWNED_PREFIXES)
