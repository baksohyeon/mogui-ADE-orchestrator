# Harness self-check (scripts/harness-selfcheck.sh)

## What this checks

The harness self-check answers one question: is every component this workspace claims to have actually reachable by the host? This prevents silent failures where files exist on disk but are not wired to the host discovery paths. One layer, `Twins:`, goes further and checks entry-file content, not just reachability — see below.

The check measures five harness layers, four pass/fail and one warning-only (see "Required infrastructure" below):

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

### Required infrastructure: ctx, code-review-graph (#317 stage 1)
Four tools are required infra for this workspace: Orca and beads are covered by the `Orca:` and `Tracker:` checks above (pass/fail, unchanged). `ctx` and `code-review-graph` each get one `Infra:` line instead. Unlike every check above, an `Infra:` line only warns — it never changes the script's exit code, because this is a measure-and-warn stage; wiring either tool in by default is a later stage.

For each tool, the check stops at the first gap it finds (one reason per line):

1. **Runs.** The CLI is on `PATH` and a cheap, bounded (10s), network-free read command succeeds (`ctx status --format json`, `code-review-graph --version`). A shim error or non-zero exit reports its first line verbatim; an absent binary reports `absent from PATH`.
2. **Reachable from this host session.** Claude: a user-scope server (the top-level `mcpServers` in the file `CLAUDE_CONFIG_DIR` points an Orca profile's Claude CLI at) is always reachable. A project-scope server listed in `.mcp.json` additionally needs `enableAllProjectMcpServers` or `enabledMcpjsonServers` set in some settings file the session reads, and is rejected if **any** settings file (user `settings.json`, project `.claude/settings.json`, or project-local `.claude/settings.local.json`) lists it in `disabledMcpjsonServers` — a disabled entry wins regardless of which file sets it. Codex: its `config.toml` `[mcp_servers.<tool>]`. This never calls `claude mcp list`, which health-checks every server and is slow.
3. **Fresh and covering.**
   - `ctx`: every provider Orca's own agent-session index (`orca search --index-status --json`) reports sessions for among `claude` and `codex` must also appear in ctx's own indexed-providers list (`ctx status --format json`, `.daemon.jobs.*.progress.providers`). A missing provider is named, with the reason `ctx sources` prints for it when it prints one.
   - `code-review-graph`: every repository in its multi-repo registry (`~/.code-review-graph/registry.json`) must have a graph no older than `CODE_REVIEW_GRAPH_STALE_DAYS` (default 7). Read directly from the registry and each repo's `.code-review-graph/graph.db` mtime, not through the CLI, which needs a per-repo cwd to report status and is the exact tool a `Runs:` gap means may not run at all. A registry entry whose path no longer exists is named under "missing path".

A passing line reads `Infra: <tool> OK ...`; a gap reads `Infra: <tool> WARN <reason>`.

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

A passing line names the scope ("Skills: 3 reachable", "Hooks: 5 wired", "Tracker: resolves to..."). Exit 2 never prints a passing line. The `Infra:` lines (ctx, code-review-graph) are excluded from this table: a `WARN` never changes the exit code, at any of 0, 1, or 2.

## Important: reachability is not correctness

Skills, hooks, and the tracker are checked for **reachability only**. A reachable hook can still be wrong (bad path, wrong permissions, logic error). Proving a hook works requires feeding it a case it must reject. `Card:` and `Twins:` are the exception: they additionally validate entry-file content with a byte-for-byte comparison (`cmp -s`), because a reachable-but-stale or reachable-but-diverged card is exactly the silent failure those two checks exist to catch.

For self-test discipline and examples, see [Master Operations](../MASTER-OPERATIONS.md) section 8 (charted failure modes) and the existing hooks under `scripts/hooks/`.

## Template currency: retirements and unknown files

The `Template:` line's currency check (`scripts/template-check`, invoked at the
bottom of this script) compares the install against `MANIFEST.json`'s
required-files list. Two kinds of difference from that list do not count as
drift:

- **Files the install added.** `unknown_present` is still reported (count and
  list) but never fails the check. Installs accumulate contracts, lineage, and
  runbooks by design; the template only cares whether a required file is
  missing, not whether the install wrote extra ones.
- **Files the install retired on purpose.** List them in
  `config/template-retirements.json` (install-owned, gitignored, path
  overridable with `--retirements`): a JSON array of
  `{"path": "<manifest path>", "since": "<YYYY-MM-DD>", "why": "<one
  sentence>"}`. A listed path that is in the manifest is reported under
  `retired` instead of `absent_required`. A listed path that is not in the
  manifest is reported under `retirements_unknown` and does not fail either —
  it just means the retirement note is stale or premature. A malformed
  retirements file (bad JSON, wrong shape) is reported as
  `retirements_status: malformed` and does fail the check, the same as a
  genuinely missing required path.

The passing line reads `Template: <ver> (matches template <tver>)`, or
`Template: <ver> (matches template <tver>, M retired)` when `M` retirements
apply. The failing line reads `Template: <ver> (manifest=<status>, absent=N,
retired=M, unknown=K) — run Upgrade mode`, or `Template: <ver> (manifest=ok,
retirements=malformed) — run Upgrade mode` for a broken retirements file.

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

`scripts/test-harness-selfcheck-infra.sh` covers the `Infra:` lines separately: all present/registered/covering/fresh (no `WARN`); ctx missing a provider Orca reports sessions for; a graph older than the staleness threshold; a tool absent from `PATH`; a project-scope server disabled via `disabledMcpjsonServers` naming the settings file that disabled it; and that none of these change the exit code.

The check is read-only and does not modify any files.
