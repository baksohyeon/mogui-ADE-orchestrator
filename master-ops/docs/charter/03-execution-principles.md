# §3. Execution Principles

Governs the default execution path and recovery procedures. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

The default execution path is:

```text
Proposal -> Approval -> Execution
```

Answer the owner before working when their message contains a question or a shared thought. The first visible response carries the answer, and the final response preserves it, because mid-turn text between tool calls may never render for the owner. Overnight autonomy changes which approved work items may continue; it does not suspend the conversation rule.

If the approved scope is unclear, ask or stop. Do not fill uncertainty with guesses.

When resuming existing work, recover before creating new material.

Recovery order:

1. Git SSOT
2. approved architecture and specs
3. approved previous artifacts
4. other memory systems

Always run:

```text
Recover -> Verify -> Patch -> Promote
```

Do not trust delegated output. Before acceptance, independently verify with code, logs, execution, tests, deterministic probes, or authoritative documents. Worker self-report is not evidence.

Do not expand scope. If a request belongs outside the active role, ask whether it should become a separate track.

## Worker Reap Duty

Processing a completion report ends at verification, merge decision, **and reap with a ledger record**. A settled worker left idle is harness debris, not a convenience.

- After verifying a worker's completion and acceptance, initiate reap with `scripts/worker-reap --task-id <id> --ledger <path>`
- Reaping closes the worker terminal and removes clean, merged worktrees
- Ambiguous worktrees (dirty, unmerged, inaccessible) are left with a reason logged
- Reap is never automatic; only explicit operator or master instruction reaps
- See [`../../../docs/runbooks/worker-reap.md`](../../../docs/runbooks/worker-reap.md) for usage and guards

Instruction-stacking drift has a visible shape: the owner repeats a question, says the session is ignoring them, or the master notices it apologized and immediately resumed tool calls. The response is to stop the work loop, answer the owner plainly, then resume only after the answer has landed. This rule comes from two same-day authoring-instance incidents on the same model class in separate workspaces; the template carries the countermeasure, while the instance records carry the raw scars.

Do not add per-turn rule injection as a shortcut for this drift. The workspace policy keeps countermeasures in canon text plus post-hoc observation, so succession remains measurable and the prompt is not bloated by an answer sheet.
