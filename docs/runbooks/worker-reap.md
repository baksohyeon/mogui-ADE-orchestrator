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

### 2. Close the Terminal

If the dispatch is settled, the reaper will:
- Call `orca terminal close <terminal-id>` to shut down the worker session
- Append `terminal_closed:<terminal-id>` to the actions log

### 3. Check Worktree Safety

The reaper checks three conditions before removing the worktree:

1. **Git status is clean** — no uncommitted changes (`git status --porcelain` is empty)
2. **Current branch is merged** — the checked-out branch appears in `git branch -a --merged origin/main`
3. **Worktree exists** — the path on disk is accessible

If all three are true, the worktree is removed and `worktree_removed:<path>` is logged.

If **any** condition fails, the worktree is left in place and the reason is logged:
- `worktree_left:<path>` + reason
- Example: "Current branch feature/x is not merged to origin/main"

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

Output:
```json
{
  "record": {
    "task_id": "task_abc123",
    "dispatch_id": "dispatch_xyz",
    "terminal_id": "term_123",
    "worktree_path": "/path/to/worktree",
    "actions_taken": "terminal_closed:term_123;worktree_removed:/path/to/worktree",
    "timestamp": 1722787200.0
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
    "actions_taken": "terminal_closed:term_123;worktree_left:/path/to/worktree",
    "timestamp": 1722787200.0
  },
  "dry_run": false
}
```

The reap record is appended to the ledger:
```jsonl
{"event":"reap","ts":1722787200.0,"task_id":"task_abc123","dispatch_id":"dispatch_xyz","terminal_id":"term_123","worktree_path":"/path/to/worktree","actions_taken":"terminal_closed:term_123;worktree_left:/path/to/worktree"}
```

### Detect Unreaped Settled Leases

Use `dispatch-gate report` or a dedicated observability command to detect debris:

```bash
scripts/dispatch-gate report --ledger master-ops/ledger/dispatch-ledger.jsonl --unreaped-settled
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
    print(f"{dispatch_id}: {state.status} (unreap since {state.reaped_at})")
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

The feature branch exists but is not yet merged. Either:
1. Merge the branch to main, then reap
2. Manually verify and clean the worktree
3. Leave the worktree and reap only the terminal

The reaper will always leave the terminal closed (no open handles leak) and record the partial reap.

## See Also

- `charter/03-execution-principles.md` — Execution principles and worker routing
- `charter/04-worker-routing-review.md` — Worker dispatch and completion
- `scripts/dispatch-gate` — Dispatch gate verification and ledger reporting
- `docs/internal/specs/transcript-ledger-spec.md` — Ledger format and replay semantics
