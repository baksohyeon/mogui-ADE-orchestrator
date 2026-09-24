# Host harness inventory (measured 2026-08-03)

What is actually wired on this machine, so nobody re-invents an existing layer.
Re-measure on host changes; this is a snapshot, not a spec.

| Layer | Where | Does |
|---|---|---|
| gsd v1.9.1 | `~/.claude/hooks/` (global) | context/token monitor: reads statusline bridge `/tmp/claude-ctx-{session}.json`, injects WARNING at 35% remaining / CRITICAL at 25% on PostToolUse/Stop/SubagentStop/PreCompact; plus prompt/read/workflow guards, commit validation |
| ponytail 4.8.4 | plugin hook (SessionStart) | restraint persona ("PONYTAIL MODE ACTIVE" banner) |
| superpowers 6.x | plugin hook (SessionStart) | skill-first mandate block |
| ecc | `~/.claude/ecc` (installed 2026-04-16) | produced the `~/.claude/rules/` ruleset |
| gstack | SessionStart + `~/.gstack/analytics/` | skill usage/duration/outcome telemetry |
| orca agent-hooks | all events, delegated `claude-hook.sh` | host-Orca integration |
| this instance (2026-08-03) | workspace `.claude/settings.json` → ops `scripts/hooks/` | role-state inject (every turn), orchestration inbox warn (UserPromptSubmit mailbox count + up to 3 truncated subjects, fail-open), product-path hard block for inline edits and Bash git write commands (logged override), bash trim-warn, tracker check + protections briefing, PreCompact memory reinject; dispatch gate + ledger + `scripts/workstream-render.sh` + `skills/dispatch-board`; Orca surface fingerprint check (`scripts/orca-surface-check.sh`) at boot detects appVersion/schema drift |
| Worker host diversity guard | ops `scripts/dispatch` + `~/.mogui/dispatch-ledger.jsonl` | advisory runtime collision warning, installed alternative runtime listing, and same-host audit records |
| Harness self-check (`scripts/harness-selfcheck.sh`) | read-only verification | measures reachability of skills, hooks, and tracker; exit 0 (all reachable), 1 (gap found: skill unreachable, hook missing/unwired, tracker misresolved), 2 (settings unreadable); prevents silent wiring failures; no modifications made |

Division of labor: gsd owns context-total measurement; the instance layer owns
charter enforcement and dispatch provenance; gstack owns skill telemetry. No overlap
measured — check before adding anything to any of these lanes.

- 2026-08-03 measurement: `claude -p` from this worktree loads user-level `blame-agent` but not repository `skills/` entries, so same-name collision precedence is unresolved on that surface.
- Name policy for this harness: keep `blame-agent` as the default name. If a future collision measurement shows a concrete failure mode, a rename can only be proposed with that measurement and must wait for explicit owner approval before any file rename.
