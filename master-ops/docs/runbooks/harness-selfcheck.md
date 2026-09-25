# Harness self-check (scripts/harness-selfcheck.sh)

## What this checks

The harness self-check answers one question: is every component this workspace claims to have actually reachable by the host? This prevents silent failures where files exist on disk but are not wired to the host discovery paths. One layer, `Twins:`, goes further and checks entry-file content, not just reachability — see below.

The check measures four harness layers:

### Skills reachability
Verifies each skill directory under `skills/` is reachable at the workspace discovery path (`<workspace>/.claude/skills/<name>`) and contains the entry file the host expects (`SKILL.md`). A skill on disk but unwired or missing its entry file fails the check.

### Hooks wiring
Verifies each hook command referenced in the workspace settings file:
- The script exists and is executable
- It is referenced (wired) in the settings file

Also detects hook scripts under `scripts/hooks/` that exist but are not wired to any event, since an unwired guard is the failure this whole check exists for.

### Tracker resolution
Confirms the tracker (`bd where`) resolves from the workspace root to the ops repository, and that `BEADS_DIR` (if set) points to the correct location. Reuses the logic from `scripts/hooks/tracker-check.sh`.

### Twins: entry-file agreement
`CLAUDE.md` and `AGENTS.md` are twins: a master hosted by Claude reads one, a master hosted by Codex reads the other, and they must carry the same card. The `Twins:` check, in `twins_probe()`, confirms three pairs stay byte-identical — the canonical pair under `workspace-card/`, the deployed `AGENTS.md` at the workspace root against its canonical copy, and this repository's own `CLAUDE.md`/`AGENTS.md` at its root. A diverged pair means a codex-hosted master boots with a different session card than a claude-hosted one, silently.

## Running the check

```bash
bash scripts/harness-selfcheck.sh
```

## Exit codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | All components reachable; check names what was covered (counts) | All clear |
| 1 | Gap detected: skill unreachable, hook missing, script unwired, tracker misresolved, or an entry-file pair diverged/undeployed | Fix the gap; see details in output |
| 2 | Check could not measure (settings file unreadable, etc.) | Investigate blocker; rerun after fixing |

A passing line names the scope ("Skills: 3 reachable", "Hooks: 5 wired", "Tracker: resolves to..."). Exit 2 never prints a passing line.

## Important: reachability is not correctness

Skills, hooks, and the tracker are checked for **reachability only**. A reachable hook can still be wrong (bad path, wrong permissions, logic error). Proving a hook works requires feeding it a case it must reject. `Card:` and `Twins:` are the exception: they additionally validate entry-file content with a byte-for-byte comparison (`cmp -s`), because a reachable-but-stale or reachable-but-diverged card is exactly the silent failure those two checks exist to catch.

For self-test discipline and examples, see [Master Operations](../MASTER-OPERATIONS.md) section 8 (charted failure modes) and the existing hooks under `scripts/hooks/`.

## Common gaps

### Skill discovered but SKILL.md missing
**Problem:** Skill directory exists but lacks `SKILL.md` entry file.
**Fix:** Add `SKILL.md` to the skill directory. See an existing skill (e.g., `skills/anti-slop/SKILL.md`) for format.

### Hook wired but script missing
**Problem:** Settings references a script path that does not exist.
**Fix:** Create the script at the referenced path, or update the settings to point to an existing script.

### Script present but not wired
**Problem:** Script exists in `scripts/hooks/` but no event in settings references it.
**Fix:** Either wire the script to an event in settings, or delete the script if it is not needed.

### Tracker does not resolve
**Problem:** `bd where` does not show `{{OPS_REPO}}/.beads`.
**Fix:** Check `BEADS_DIR` environment variable and `.beads/config` file. See [tracker-check.sh](./tracker-check.sh) for diagnosis.

## Self-test: three cases

This check was tested with:

1. **Pass with counts (exit 0):** All components reachable. Output names the scope.
2. **Detect unreachable skill (exit 1):** Skill directory on disk but missing entry file is detected as unreachable.
3. **Undecided on settings failure (exit 2):** When settings file is unreadable, exit 2 without printing a passing line.

The check is read-only and does not modify any files.
