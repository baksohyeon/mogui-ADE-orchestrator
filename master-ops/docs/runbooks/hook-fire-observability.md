# Hook Fire Observability Runbook

## Purpose

The fire-log (`~/.mogui/hook-fire-log.jsonl`) records when ops hooks run, where they ran, and what runtime invoked them. It answers: **Which hooks actually fire in live operation?** across runtimes (Claude, Codex, Cursor, Grok, Antigravity/Gemini) and session kinds (master, dispatched worker). Product-path decisions (`command_class`, `target_scope`, `outcome`, and `reason`) are written to the separate `event-log.jsonl`.

## Design Decision

Observational fire-log first; active canaries later and only for hooks that never appear in the log. Principle borrowed from the AHE research program: with rare events you cannot distinguish "prevented" from "never happened"; the antidote is a guard-firing log.

## What the Log Answers

- Does a hook fire at all?
- How often?
- In what runtimes and session kinds?
- When was the last invocation?

## What the Log Cannot Answer

- A wired-but-broken hook (e.g., script exits early, condition never true) and a not-wired hook **both show zero fire-log entries**. Distinguishing them requires an active canary (deliberately deferred).
- Whether a hook's decision logic ran correctly (the log records only that the hook was invoked, not its outcome).
- The product-path guard's Bash rejection rate is unavailable until command-class observations exist; use `scripts/measure-product-path-guard.sh` and report `N/A (0/0; no command observations)` when none exist.

## Fire-Log Schema

One JSON line per hook invocation. Example:

```json
{"ts": 1722728400, "hook": "role-state-inject", "event": "UserPromptSubmit", "cwd": "{{WORKSPACE_ROOT}}", "runtime_hint": "claude", "session_kind": "master"}
```

| Field | Type | Meaning |
|-------|------|---------|
| `ts` | epoch seconds | When the hook fired (seconds since 1970-01-01) |
| `hook` | string | Name of the hook script (without `.sh`) |
| `event` | string | Hook event type (e.g., `SessionStart`, `UserPromptSubmit`, `PreToolUse`) |
| `cwd` | string | Working directory when hook fired |
| `runtime_hint` | string | Runtime identifier: `claude`, `codex`, `cursor`, `grok`, `antigravity`, or `unknown` |
| `session_kind` | string | `master` (ops repo root) or `worker` (in `.orca/worktrees`), or `unknown` |

## Log Location

```
${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}
```

Append-only; one line per invocation. Fails open (never blocks or breaks the hook if append fails).

## Reading the Log

### Manual inspection

```bash
tail -20 ~/.mogui/hook-fire-log.jsonl
jq '.hook' ~/.mogui/hook-fire-log.jsonl | sort | uniq -c
```

### Coverage report

```bash
scripts/hook-coverage-report
```

Prints a matrix of hook by (runtime_hint, session_kind) with last-fired timestamp and count. Lists hooks with zero entries (measurement targets).

### Product-path guard measurement

```bash
scripts/measure-product-path-guard.sh
```

This reads product-path decision events from the separate event log and reports the
number of usable Bash command observations, blocked decisions, and the numeric
rejection rate. The guard must not infer an allowlist from command
names: populate `scripts/hooks/product-path-guard-readonly-allowlist.txt` only from
measured read-only command classes. Until the log has command observations, the
correct report is `bash_command_observations=0`, `guard_rejections=0`, and
`rejection_rate=N/A (0/0; no command observations)`.

## Escalation Rule

A hook with **zero entries after days of normal operation** is a measurement target (a signal to investigate), not proof of breakage:

1. **High severity**: A hook marked SessionStart or UserPromptSubmit with zero entries after 3+ days of daily use -> escalate for canary investigation (verify wiring, check conditions, measure firing).
2. **Low severity**: A rarely-triggered hook (e.g., PreToolUse on edits to a path that hasn't been edited) with zero entries -> not actionable; wait for triggering event.

## Operational Workflow

### During session startup

The master session outputs active protections:

```
[protections] active: role-state inject (every turn) | product-path hard block (overrides logged: N) | bash trim-warn | dispatch gate+ledger (ops-policy decisions: M) | PreCompact memory reinject
```

This line confirms the harness state. If a protection is missing or logged counts diverge from expected operation, investigate the fire-log.

### When debugging a suspected hook failure

1. Check the fire-log for recent entries: `tail -50 ~/.mogui/hook-fire-log.jsonl | grep "<hook-name>"`
2. Run the coverage report: `scripts/hook-coverage-report`
3. If zero entries: check the host hook settings file. For Claude, that is usually `~/.claude/settings.json` (global) or `.claude/settings.json` (project-level). Hooks bind only at session start; settings changes mid-session are inert.
4. If recent entries but suspected misbehavior: the hook fired but may have a logic bug; review the script and run manual self-tests.

### Adding a new hook

1. Add the script to `scripts/hooks/<name>.sh`
2. Wire it in the appropriate settings file (global or project)
3. Add a `log_fire()` call at the top of the script body:
   ```bash
   log_fire() {
     local fire_log="${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}"
     mkdir -p "$(dirname "$fire_log")" 2>/dev/null || return 0
     local session_kind="unknown"
     if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
       session_kind="worker"
     elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
       session_kind="master"
     fi
     python3 - "<name>" "<event>" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" <<'PY' >> "$fire_log" 2>/dev/null || true
   import json
   import sys
   import time

   _, hook, event, cwd, runtime_hint, session_kind = sys.argv
   print(json.dumps({
       "ts": int(time.time()),
       "hook": hook,
       "event": event,
       "cwd": cwd,
       "runtime_hint": runtime_hint,
       "session_kind": session_kind,
   }, separators=(",", ":")))
   PY
   }
   ```
4. Call `log_fire` at the start of the script body (fail-open: never block if logging fails).
5. Self-test: invoke the hook the way the harness would, then verify the fire-log line appears.

## Constraints

- Appending to the fire-log must be fail-open (never block or fail the hook; `|| true` on every path).
- One line per invocation.
- No message bodies or secrets in the line.
- `session_kind=worker` is emitted when dispatch/task markers or `.orca/worktrees`
  identify a worker, `session_kind=master` is emitted when the hook runs from a
  directory that contains `docs/MASTER-OPERATIONS.md`, and `unknown` is the
  fallback.
- Hook's existing behavior must be byte-identical otherwise.

## Implementation Notes

- `session_kind` is derived cheaply: dispatch/task markers or `.orca/worktrees`
  in cwd = worker; `docs/MASTER-OPERATIONS.md` in cwd = master; otherwise
  unknown.
- `runtime_hint` is set via the `MOGUI_RUNTIME_HINT` environment variable (or defaults to `unknown`).
- Timestamp is Unix epoch seconds from the embedded Python `int(time.time())`.

## Further Reading

- Master operations: `docs/MASTER-OPERATIONS.md`
