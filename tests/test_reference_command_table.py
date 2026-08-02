"""The reference table lists commands; this pins that list to the scripts that exist.

The table sat behind an `AUTO-GENERATED from scripts/ --help` marker whose generator
was never in the repository. Nothing measured it, so it drifted in silence: by the
time anyone compared, `codex-worker-pretrust`, `onboarding-preflight.sh`, and
`redaction-inventory` were absent from the page, and so was `dispatch-gate report`.

The prose columns stay hand-written, because `--help` does not carry purpose and a
generator that emitted it would emit worse prose than a person. What a machine can
hold is the inventory, so the inventory is held here instead of in a generator.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
REFERENCE = REPO_ROOT / "docs" / "public" / "reference.md"

# argparse prints its subcommand choices as {a,b,c} in the usage line. Scripts with
# no subparsers print no such group and stand as a single command.
SUBCOMMAND_GROUP = re.compile(r"\{([a-z0-9][a-z0-9,_-]+)\}")

# | `scripts/x` | `x sub` | purpose | key options |
TABLE_ROW = re.compile(r"^\|\s*`(scripts/[^`]+)`\s*\|\s*`([^`]+)`\s*\|")


def _executables() -> list[Path]:
    return sorted(p for p in SCRIPTS_DIR.iterdir() if p.is_file() and p.stat().st_mode & 0o100)


def _subcommands(script: Path) -> list[str]:
    """Read a script's own help output. A script that refuses --help still prints usage."""
    proc = subprocess.run(
        [str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    match = SUBCOMMAND_GROUP.search(proc.stdout + proc.stderr)
    return match.group(1).split(",") if match else []


def measured_surface() -> set[tuple[str, str]]:
    surface = set()
    for script in _executables():
        rel = f"scripts/{script.name}"
        subs = _subcommands(script)
        if subs:
            surface.update((rel, f"{script.name} {sub}") for sub in subs)
        else:
            surface.add((rel, script.name))
    return surface


def documented_surface() -> set[tuple[str, str]]:
    text = REFERENCE.read_text(encoding="utf-8")
    return {(m.group(1), m.group(2)) for m in (TABLE_ROW.match(line) for line in text.splitlines()) if m}


def test_reference_table_matches_the_script_surface() -> None:
    measured = measured_surface()
    documented = documented_surface()

    missing = sorted(measured - documented)
    stale = sorted(documented - measured)

    assert not missing, (
        "commands exist in scripts/ but are absent from docs/public/reference.md: "
        f"{missing}. Add a row for each, or drop the command."
    )
    assert not stale, (
        "docs/public/reference.md documents commands that scripts/ no longer exposes: "
        f"{stale}. Remove the row, or restore the command."
    )


def test_the_check_can_fail() -> None:
    """A comparison that cannot fail is indistinguishable from one that is not running.

    Zero drift above proves nothing unless a fabricated gap is caught, so one is.
    """
    measured = measured_surface()
    documented = documented_surface()
    assert measured, "no executables discovered under scripts/; the comparison had nothing to compare"

    victim = ("scripts/dispatch-gate", "dispatch-gate check")
    assert victim in measured and victim in documented
    assert victim not in measured - documented
    assert victim in measured - (documented - {victim})
