"""The onboarding router names step files; this pins that structure to the files that exist.

The 2026-08-03 install run showed what a monolithic ONBOARDING.md does to an agent
mid-install, so the flow was split into a router plus one file per step. The split
buys progressive loading and pays for it with a cross-reference surface: a step
index in the router, a next-file pointer in every step file, a placeholder
allowlist, and required Owner script / Verify sections. Nothing else measures that
surface, and this repository has already watched an unmeasured doc inventory drift
in silence (see test_reference_command_table.py), so the inventory is held here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER = REPO_ROOT / "master-ops" / "ONBOARDING.md"
STEP_DIR = REPO_ROOT / "master-ops" / "onboarding"

ALLOWED_PLACEHOLDERS = {
    "{{WORKSPACE_NAME}}",
    "{{WORKSPACE_ROOT}}",
    "{{OPS_REPO}}",
    "{{MONITOR_NS}}",
    "{{MODEL_ID}}",
    "{{REPO_LIST}}",
    "{{RUNTIME_ROOT}}",
    "{{TEMPLATE_VERSION}}",
}

# 10-card-and-retire.md warns against inventing new placeholders by naming the
# shape itself; that literal is documentation, not a placeholder.
PLACEHOLDER_SHAPE_MENTION = "{{...}}"

INDEX_ROW = re.compile(r"^\|\s*(?:\d{2}|—)\s*\|\s*`onboarding/([a-z0-9-]+\.md)`\s*\|")
NEXT_POINTER = re.compile(r"Next file after Verify passes: `([a-z0-9-]+\.md)`")
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")


def indexed_files() -> list[str]:
    rows = [m.group(1) for m in map(INDEX_ROW.match, ROUTER.read_text().splitlines()) if m]
    assert rows, "router step index parsed to zero rows; the table format changed"
    return rows


def test_every_indexed_file_exists():
    for name in indexed_files():
        assert (STEP_DIR / name).is_file(), f"router index names onboarding/{name}, which does not exist"


def test_no_orphan_step_files():
    on_disk = {p.name for p in STEP_DIR.glob("*.md")}
    assert on_disk == set(indexed_files()), "step files on disk and the router index disagree"


def test_onboarding_inventory():
    """Pin the expected onboarding step files to catch silent drifts."""
    expected = {
        "00-orientation.md",
        "01-preflight.md",
        "02-workspace-facts.md",
        "03-ops-repo.md",
        "04-seat.md",
        "05-placeholders.md",
        "06-tracker.md",
        "07-user-rules.md",
        "08-settings-and-skills.md",
        "09-spawn.md",
        "10-card-and-retire.md",
        "reverify.md",
    }
    assert set(indexed_files()) == expected, f"onboarding inventory drifted; expected {expected}"


def test_next_pointers_follow_index_order():
    numbered = [n for n in indexed_files() if n[0].isdigit()]
    for current, expected_next in zip(numbered, numbered[1:]):
        text = (STEP_DIR / current).read_text()
        match = NEXT_POINTER.search(text)
        assert match, f"{current} has no next-file pointer"
        assert match.group(1) == expected_next, (
            f"{current} points to {match.group(1)}, but the router index orders {expected_next} next"
        )
    last = numbered[-1]
    assert NEXT_POINTER.search((STEP_DIR / last).read_text()) is None, (
        f"{last} is the last step but still carries a next-file pointer"
    )


def test_numbered_steps_carry_required_sections():
    for name in indexed_files():
        text = (STEP_DIR / name).read_text()
        if name[0].isdigit():
            assert "Verify" in text, f"{name} has no Verify section"
            assert "Owner script" in text, f"{name} has no Owner script block"
        else:
            # reverify.md is a mode file, not a numbered step: its body IS the
            # verification, structured as Checklist + Report.
            assert "Checklist" in text and "Report" in text, f"{name} lost its Checklist/Report structure"


def test_only_allowed_placeholders():
    for path in [ROUTER, *STEP_DIR.glob("*.md")]:
        found = set(PLACEHOLDER.findall(path.read_text())) - {PLACEHOLDER_SHAPE_MENTION}
        unknown = found - ALLOWED_PLACEHOLDERS
        assert not unknown, f"{path.name} uses placeholders outside the allowlist: {sorted(unknown)}"


def test_entry_files_stay_byte_identical():
    claude = (REPO_ROOT / "CLAUDE.md").read_bytes()
    agents = (REPO_ROOT / "AGENTS.md").read_bytes()
    assert claude == agents, "CLAUDE.md and AGENTS.md diverged; re-unify or record intended divergence"
