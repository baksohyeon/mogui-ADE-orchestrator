---
status: active
---

# Worker Reap — Lease Lifecycle Closure

## Rationale

The dispatch lease lifecycle has five states: `issued` → `running` → `submitted` → `accepted` → `reaped`. The reap stage was missing, leaving completed workers idling indefinitely and accumulating as system debris. This runbook defines the safe reap procedure and guards against mis-reaping.

**Core principle:** A wrong reap is expensive (lost work); a skipped reap is cheap. Every ambiguous case resolves to "leave it and report."

## Prerequisites

- The dispatch is in a settled state (completed, accepted, failed, or abandoned)
- The worker terminal and worktree are known and accessible
- `orca orchestration dispatch-show` and `orca terminal close` are available

## Reap Procedure

### 1. Verify Settled State

Before any reap action, confirm the dispatch is settled:

```bash
scripts/worker-reap --task-id <task-id> --dry-run
```

Or with dispatch ID:

```bash
scripts/worker-reap --dispatch-id <dispatch-id> --dry-run
```

If the status is `RUNNING` or `REGISTERED`, the reap is **refused** with exit code 3.

### 2. Close the Pane — Three Measurements, All Required

A settled dispatch does not close its pane on its own: the reaper measures
three conditions first, and closes only when all three hold.

1. **Present** — the terminal handle is still listed in `orca terminal list`.
   Absent (closed hours ago, or never existed) refuses with
   `terminal_left:<id>:pane_absent`.
2. **Not reused** — no row in `orca orchestration worker-list` (across every
   Run) has `dispatchStatus: dispatched` naming this same handle. A newer
   dispatch may have reused the pane before this one was reaped; closing it
   here would kill that live worker. Refuses with
   `terminal_left:<id>:reused_by:<dispatch-id>`.
3. **No agent process** — no process whose command is `claude`, `codex`,
   `cursor`, `cursor-agent`, `agy`, or `grok` has its current working directory inside the
   dispatch's worktree (`lsof -a -p <pid> -d cwd -Fn`, falling back to
   `/proc/<pid>/cwd`). A worker's own CLI session commonly stays open at an
   idle prompt after `worker_done` — this measurement refuses the close for
   as long as that session is alive, by design; the reaper never assumes an
   idle pane is a safe one. Refuses with `terminal_left:<id>:agent_process:<pid>:<comm>`.

Any measurement that could not be taken at all (an `orca` call failing, `ps`
missing) is a refusal too — `..._unmeasured` — never treated as a pass. Only
when all three clear does the reaper call `orca terminal close <terminal-id>`
and log `terminal_closed:<terminal-id>` (or, on `--dry-run`,
`would_close_terminal:<terminal-id>` — a dry run never prints
`terminal_closed`).

### 3. Check Worktree Safety

The reaper checks two conditions before removing the worktree:

1. **Git status is clean** — no uncommitted changes (`git status --porcelain`
   is empty; untracked `__pycache__/` litter does not by itself count as dirty)
2. **Current branch is included in `origin/main`** — either the checked-out branch appears in `git branch -a --merged origin/main`, or a virtual merge of `HEAD` into `origin/main` produces the same tree as `origin/main`

The worktree must also exist on disk to be a removal candidate at all.

If both are true, the worktree is removed and `worktree_removed:<path>` is
logged (`would_remove_worktree:<path>` on `--dry-run`).

If **any** condition fails, the worktree is left in place and the reason is logged:
- `worktree_left:<path>` + reason
- Example: "Current branch feature/x is not merged to origin/main (branch changes are not included in origin/main)"

### 4. Record the Reap

A reap record is appended to the dispatch ledger with:
- `task_id`, `dispatch_id`, `terminal_id`, `worktree_path`
- `actions_taken` (semicolon-separated list of actions)
- `timestamp` (Unix epoch)

## Safe Reap Guards

### Never Auto-Kill

Reaping is **never automatic** or timer-based. No sweeper or background job can reap. Only explicit operator or choreographed master-sequence invocation reaps.

### Never Reap Open Dispatches

The reaper verifies via `orca orchestration dispatch-show` that the dispatch is settled. Attempting to reap a `RUNNING` or `REGISTERED` dispatch is rejected with a clear error message.

### Ambiguous Worktrees Stay

If a worktree has:
- Uncommitted changes
- An unmerged branch
- A branch whose changes are not already present in `origin/main`
- Missing git metadata
- Any I/O error during inspection

…the worktree is left in place and the reason is reported. Manual cleanup is safer than automation in ambiguous cases.

### Ledger as Evidence

Every reap action is recorded in the dispatch ledger. This creates an audit trail and enables detection of unreaped settled leases.

## Usage Examples

### Reap a Settled Dispatch (Dry Run)

```bash
scripts/worker-reap --task-id task_abc123 --dry-run
```

Output (a dry run never prints `terminal_closed` or `worktree_removed`):
```json
{
  "record": {
    "task_id": "task_abc123",
    "dispatch_id": "dispatch_xyz",
    "terminal_id": "term_123",
    "worktree_path": "/path/to/worktree",
    "actions_taken": "would_close_terminal:term_123;would_remove_worktree:/path/to/worktree",
    "timestamp": 1722787200.0,
    "measurements": {
      "terminal_present": true,
      "terminal_reused_by": "",
      "agent_process": "",
      "worktree_clean": true,
      "worktree_merged": true
    }
  },
  "dry_run": true
}
```

### Reap and Record (With Ledger)

```bash
scripts/worker-reap \
  --dispatch-id dispatch_xyz \
  --ledger master-ops/ledger/dispatch-ledger.jsonl
```

Output:
```json
{
  "record": {
    "task_id": "task_abc123",
    "dispatch_id": "dispatch_xyz",
    "terminal_id": "term_123",
    "worktree_path": "/path/to/worktree",
    "actions_taken": "terminal_closed:term_123;worktree_left:/path/to/worktree:Worktree has uncommitted changes",
    "timestamp": 1722787200.0,
    "measurements": {
      "terminal_present": true,
      "terminal_reused_by": "",
      "agent_process": "",
      "worktree_clean": false,
      "worktree_merged": false
    }
  },
  "dry_run": false
}
```

The reap record is appended to the ledger (fields alphabetical per `sort_keys=True`, includes both `ts` and `timestamp`, and the `measurements` object):
```jsonl
{"actions_taken":"terminal_closed:term_123;worktree_left:/path/to/worktree:Worktree has uncommitted changes","dispatch_id":"dispatch_xyz","event":"reap","measurements":{"agent_process":"","terminal_present":true,"terminal_reused_by":"","worktree_clean":false,"worktree_merged":false},"task_id":"task_abc123","terminal_id":"term_123","timestamp":1722787200.0,"ts":1722787200.0,"worktree_path":"/path/to/worktree"}
```

Also emitted through `mogui_log.emit()` into `~/.mogui/event-log.jsonl` as a
`reaped` event carrying `dispatch_id`, `task_id`, and `actions_taken` — see
`master-ops/docs/runbooks/dispatch-timeline.md` for reading these back joined
with the ledger and the live dispatch state.

### Detect Unreaped Settled Leases

Use the `ReapObservability` class to detect debris:

```python
from master_runtime.core.work_ledger import ReapObservability

obs = ReapObservability("master-ops/ledger/dispatch-ledger.jsonl")
unreaped = obs.unreaped_settled_leases()
for dispatch_id, state in unreaped.items():
    print(f"{dispatch_id}: {state.status} (settled, not yet reaped)")
```

Lists all settled dispatches with no reap record.

## Exit Codes

| Code | Reason |
|------|--------|
| 0 | Success |
| 2 | Missing task_id or dispatch_id |
| 3 | Dispatch is not settled; refusing to reap |
| 4 | Could not parse dispatch JSON |
| 1 | Other failure (terminal close, worktree issues, I/O) |

## Constitution Reference

See [charter/03-execution-principles.md](../charter/03-execution-principles.md) §3, clause on **Worker Reap Duty**: Processing a completion report ends at verification, merge decision, **and reap with a ledger record**; a settled worker left idle is harness debris, not a convenience.

## Observability and Debris Detection

The dispatch ledger records both dispatch lifecycle events and reap events. Debris observability queries the ledger for settled dispatches (`COMPLETED`, `ACCEPTED`, `FAILED`, `ABANDONED`) with no matching reap record.

Example absence query:

```python
from master_runtime.core.work_ledger import ReapObservability

obs = ReapObservability("master-ops/ledger/dispatch-ledger.jsonl")
unreaped = obs.unreaped_settled_leases()
for dispatch_id, state in unreaped.items():
    print(f"{dispatch_id}: {state.status} (settled, not yet reaped)")
```

This is the same pattern as detecting never-fired hooks: absence made visible.

## Troubleshooting

### "Dispatch is not settled; refusing to reap"

The dispatch is still running or waiting. Check:
```bash
orca orchestration dispatch-show --task <task-id> --json
```

Wait for the dispatch to complete, then reap.

### "Worktree has uncommitted changes"

The worktree has unsaved work. Either:
1. Commit and push the changes, then reap
2. Manually clean the worktree, then reap
3. Leave the worktree for manual inspection and use `--dispatch-id` with another settled dispatch

### "Current branch ... is not merged to origin/main"

The feature branch exists but is not yet merged and the reaper could not prove that a squash merge already carried its changes into `origin/main`. Either:
1. Merge the branch to main, then reap
2. Manually verify and clean the worktree
3. Leave the worktree and reap only the terminal

### Partial reap: a refused pane stays open

The pane and the worktree are each judged independently, so a reap can close
one and leave the other. A refused measurement — pane absent, reused by a
newer dispatch, an agent process (or an unresolved cwd for one) still in the
worktree, or the measurement itself failing — leaves the terminal open and
logs `terminal_left:<id>:<reason>`; it is not closed just because the
worktree side happened to be clean and removed, and the reverse holds too:
the terminal can close while the worktree is left in place. Both outcomes are
recorded in the same `actions_taken` list, so a settled dispatch's record can
read `terminal_left:...;worktree_removed:...` or
`terminal_closed:...;worktree_left:...` — either is a valid partial reap, not
a bug. Re-run `scripts/worker-reap --dry-run` after resolving the blocking
condition to finish the other half.

## See Also

- `charter/03-execution-principles.md` — Execution principles and worker routing
- `charter/04-worker-routing-review.md` — Worker dispatch and completion
- `scripts/dispatch-gate` — Dispatch gate verification and ledger reporting
- `docs/internal/specs/transcript-ledger-spec.md` — Ledger format and replay semantics
