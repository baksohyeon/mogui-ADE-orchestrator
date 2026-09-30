# dispatch-timeline runbook

## What it does

**`scripts/dispatch-timeline <task_id|dispatch_id>`** joins three sources for
one dispatch into a single time-ordered table: the dispatch ledger row(s)
(`dispatch-gate register`, its host-diversity audit, and `worker-reap`'s reap
record), every matching line in the event log, and the current
`orca orchestration dispatch-show` record. A source with nothing matching is
named in `missing_sources` rather than left silently absent — the prior state
was a ledger, an event log, and Orca's own state with no tool joining them,
so a source going quiet looked identical to "nothing happened" and "this
could not be checked."

`--since <hours>` with no id lists every dispatch seen in the ledger or event
log within that window, each with its most recent event — the daily
accounting view across dispatches rather than a single dispatch's history.

## Event kinds

Emitted through `mogui_log.emit()` into the shared event log
(`~/.mogui/event-log.jsonl`), each carrying `dispatch_id`/`task_id` where
known:

| Event | Emitted by | When |
|---|---|---|
| `dispatch_registered` | `scripts/dispatch-gate register` | After every register call, allow or deny |
| `dispatch_launched` | `scripts/dispatch` | After a successful register, with dispatch id, task id, pane, pid (usually empty — `dispatch` creates the worker's terminal through an RPC, not a local process), and model |
| `wait_verdict` | `scripts/worker-wait` | Once per actionable row (`DEAD`, `STALL`, `OPEN_PANE`) in an accounting pass |
| `wait_wake` | `scripts/worker-wait` | Once per non-heartbeat delivery the wait loop receives, with the message type(s) and delivery id |
| `reaped` | `scripts/worker-reap` | After a real (non-dry-run) reap, with `actions_taken` |

`session_kind` on every event is `master` when the process's cwd is the
workspace root (`config/workspace-descriptor.json`'s `workspace_root`, or
`MOGUI_SEAT_ROOT` when set), `worker` when the cwd is inside a
`.orca/worktrees/` checkout or `ORCA_TASK_ID` is set, `unknown` otherwise.

## Usage

```bash
# One dispatch's full history, human-readable.
scripts/dispatch-timeline task_abc123

# Same, machine-readable.
scripts/dispatch-timeline ctx_def456 --json

# The daily accounting view: every dispatch seen in the last 24 hours.
scripts/dispatch-timeline --since 24 --json
```

An argument starting with `task_` is treated as a task id; anything else is
treated as a dispatch id. `--ledger` and `--event-log` override the default
paths (`~/.mogui/dispatch-ledger.jsonl` and `~/.mogui/event-log.jsonl`).

## Related docs

- `worker-wait.md` — `wait_verdict`/`wait_wake` and the
  `--reap` flag that folds `worker-reap`'s own record into an `OPEN_PANE` row.
- `../charter/05-dispatch-gate.md` — the register step `dispatch_registered`
  reports on.
