"""Shared Orca version cases for the preflight and surface checks."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "master-ops" / "scripts" / "orca-surface-baseline.json"
MINIMUM_ORCA_VERSION = json.loads(BASELINE.read_text(encoding="utf-8"))[
    "minimumAppVersion"
]
MINIMUM_PARTS = tuple(int(part, 10) for part in MINIMUM_ORCA_VERSION.split("."))
BELOW_VERSION = f"{MINIMUM_PARTS[0]}.{MINIMUM_PARTS[1]}.{MINIMUM_PARTS[2] - 1}"

VERSION_CASES = (
    (
        "higher_patch",
        f"{MINIMUM_PARTS[0]}.{MINIMUM_PARTS[1]}.1000",
        False,
    ),
    ("prerelease", f"{MINIMUM_ORCA_VERSION}-beta.1", True),
    (
        "leading_zero_patch",
        f"{MINIMUM_PARTS[0]}.{MINIMUM_PARTS[1]}.{MINIMUM_PARTS[2]:04d}",
        False,
    ),
    (
        "extra_text",
        f"orca version {MINIMUM_ORCA_VERSION} (build 123)",
        False,
    ),
)
