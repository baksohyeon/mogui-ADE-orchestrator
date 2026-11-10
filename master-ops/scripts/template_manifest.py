"""Where template-apply and template-check get their instance-owned list.

The manifest's `instance_owned` key is the data source: a list of path
prefixes (ending in "/") and exact paths, relative to the template root, that
the template never claims. A manifest written before that key existed has no
such list, so the code list in template_common (INSTANCE_OWNED_PREFIXES and
INSTANCE_OWNED_EXACT) is the fallback for it. The fallback is read when called,
not copied at import, so the two can never disagree inside one run.
"""

from __future__ import annotations

from typing import Callable

import template_common

MANIFEST_SOURCE = "manifest"
FALLBACK_SOURCE = "built-in list"


def _is_normalized(entry: object) -> bool:
    """A relative posix path with no empty, "." or ".." segment; a trailing "/" marks a prefix."""
    if not isinstance(entry, str) or not entry or "\\" in entry or entry.startswith("/"):
        return False
    # Reject null bytes the same way template-apply's normalize_rel does.
    if "\x00" in entry:
        return False
    body = entry[:-1] if entry.endswith("/") else entry
    return all(part not in ("", ".", "..") for part in body.split("/"))


def instance_owned_entries(manifest: dict | None) -> tuple[tuple[str, ...], str]:
    """Return (entries, source). Raise ValueError on a malformed key."""
    if isinstance(manifest, dict) and "instance_owned" in manifest:
        entries = manifest["instance_owned"]
        if not isinstance(entries, list) or not all(_is_normalized(e) for e in entries):
            raise ValueError("manifest instance_owned is not a list of normalized relative paths")
        return tuple(entries), MANIFEST_SOURCE
    fallback = (
        *template_common.INSTANCE_OWNED_PREFIXES,
        *sorted(template_common.INSTANCE_OWNED_EXACT),
    )
    return fallback, FALLBACK_SOURCE


def matches(rel: str, entries: tuple[str, ...]) -> bool:
    for entry in entries:
        if entry.endswith("/"):
            if rel == entry.rstrip("/") or rel.startswith(entry):
                return True
        elif rel == entry:
            return True
    return False


def instance_owned_predicate(manifest: dict | None) -> tuple[Callable[[str], bool], str]:
    """Return (is_owned, source) for one manifest."""
    entries, source = instance_owned_entries(manifest)
    return (lambda rel: matches(rel, entries)), source
