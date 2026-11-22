"""Shared constants for template-check and template-apply.

Import from sibling scripts so refusal names and placeholders cannot drift.

The changelog fragment name grammar below is the canonical copy. The two
repo-root changelog scripts outside this template tree cannot import this
module without a sys.path hack across the template boundary, so they each
keep a string-identical duplicate instead; tests/test_changelog_release.py
asserts the duplicates match this pattern.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from datetime import date
from pathlib import Path

FRAGMENT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.md$")
TEMPLATE_VERSION_RE = re.compile(
    r"^v(?P<release>\d+(?:\.\d+){2,})(?:-(?P<distance>\d+)-g(?P<sha>[0-9a-f]+))?$"
)
TEMPLATE_VERSION_PATTERN = r"^v\d+(?:\.\d+){2,}(?:-\d+-g[0-9a-f]+)?$"
TEMPLATE_VERSION_VALID_RE = re.compile(TEMPLATE_VERSION_PATTERN)
TEMPLATE_RETIREMENTS_REL = Path("config/template-retirements.json")
# Inherited values in this set can redirect Git away from the repository named
# by a command's explicit -C path. Keep one shared set for production
# measurement and the fixture helpers that create repositories.
GIT_REPOSITORY_ENV_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }
)


def normalize_template_rel(rel: str) -> str | None:
    """Return a normalized safe relative path, or None when it escapes root."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")):
        return None
    if "\x00" in rel or ":" in rel:
        return None
    parts: list[str] = []
    for part in rel.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def template_version_is_valid(value: str) -> bool:
    """Return whether a template stamp has a measurable release-like form."""
    return TEMPLATE_VERSION_VALID_RE.fullmatch(value.strip()) is not None


def template_version_key(value: str) -> tuple[tuple[int, ...], int, str | None] | None:
    """Return the release and commit distance represented by a template stamp."""
    match = TEMPLATE_VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    release = tuple(int(part) for part in match.group("release").split("."))
    distance = int(match.group("distance") or 0)
    return release, distance, match.group("sha")


def template_version_base(value: str) -> str | None:
    """Return the release tag portion of a valid template stamp."""
    key = template_version_key(value)
    if key is None:
        return None
    release, _, _ = key
    return "v" + ".".join(str(part) for part in release)


def compare_template_versions(first: str, second: str) -> int | None:
    """Compare release and commit distance, or return None for an unknown form."""
    first_key = template_version_key(first)
    second_key = template_version_key(second)
    if first_key is None or second_key is None:
        return None
    if first_key[:2] != second_key[:2]:
        return (first_key[:2] > second_key[:2]) - (first_key[:2] < second_key[:2])
    if first_key[2] != second_key[2]:
        return None
    return 0


def load_template_retirements(path: Path) -> tuple[list[dict], str]:
    """Return (entries, status) for the shared install retirement record."""
    try:
        path_stat = path.stat()
    except FileNotFoundError:
        if path.is_symlink():
            return [], "malformed"
        return [], "absent"
    except OSError:
        return [], "malformed"
    if not stat.S_ISREG(path_stat.st_mode):
        return [], "malformed"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return [], "malformed"
    if not isinstance(data, list):
        return [], "malformed"
    entries: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            return [], "malformed"
        rel = item.get("path")
        since = item.get("since")
        why = item.get("why")
        if not isinstance(rel, str) or not rel.strip():
            return [], "malformed"
        normalized_rel = normalize_template_rel(rel.strip())
        if normalized_rel is None:
            return [], "malformed"
        if not isinstance(since, str):
            return [], "malformed"
        try:
            date.fromisoformat(since)
        except ValueError:
            return [], "malformed"
        if not isinstance(why, str) or not why.strip():
            return [], "malformed"
        entries.append({"path": normalized_rel, "since": since, "why": why})
    return entries, "ok"


def resolve_template_version(
    source_root: Path, plain_version: str
) -> tuple[str, str | None]:
    """Resolve the install stamp and a warning when git measurement is unsafe."""
    git_prefix = ["git", "-C", str(source_root)]
    git_env = {
        key: value
        for key, value in os.environ.items()
        if key not in GIT_REPOSITORY_ENV_VARS
    }
    try:
        repo_top = subprocess.run(
            [*git_prefix, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
        )
    except FileNotFoundError:
        return plain_version, "git is unavailable; using TEMPLATE-VERSION " + plain_version
    except subprocess.CalledProcessError:
        return plain_version, None

    repo_root = Path(repo_top.stdout.strip()).resolve()
    source_resolved = source_root.resolve()
    allowed_roots = (repo_root, repo_root / "master-ops")

    def same_path(left: Path, right: Path) -> bool:
        try:
            if left.samefile(right):
                return True
        except OSError:
            pass
        return os.path.normcase(str(left)) == os.path.normcase(str(right))

    if not any(
        same_path(source_resolved, candidate) for candidate in allowed_roots
    ):
        return plain_version, None

    try:
        head = subprocess.run(
            [*git_prefix, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
        ).stdout.strip()
        tag_ref = f"{plain_version}^" + "{" + "commit}"
        tagged_head = subprocess.run(
            [*git_prefix, "rev-parse", tag_ref],
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
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
            [*git_prefix, "describe", "--tags", "--match", plain_version],
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return (
            plain_version,
            "git describe --tags failed; using TEMPLATE-VERSION " + plain_version,
        )
    if (
        not described
        or not template_version_is_valid(described)
        or template_version_base(described) != template_version_base(plain_version)
    ):
        return (
            plain_version,
            "git describe --tags --match "
            + plain_version
            + " returned an unusable stamp; using TEMPLATE-VERSION "
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
