# §3. Execution Principles

Governs the default execution path and recovery procedures. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Execution rule: classify the action first.

| Class | Rule |
| --- | --- |
| G0 read-only | do it. |
| G1 local and reversible (your own processes on resources you were given, reversible test runs, files in your own work folder) | do it, then report what you did and why. |
| G2 shared state (push, PR, issue state) | inside your contract or a standing delegation. |
| G3 paid external calls, overwriting or deleting what cannot be restored, outbound sends, deploys, credentials | the owner's explicit approval. |

Hard stops whatever the reversibility: other people's resources, resources reserved for someone else, secret values, team-surface posts.

A hard stop overrides the class: do not act, even at G0; ask the owner. A team-surface post is a message to a shared channel other people read, such as team chat, a mailing list, or a public discussion; a pull-request or issue comment inside contracted work is not a team-surface post.

An `Execution rule:` line in the installation's role-state file replaces this rule.
The hard-stop rule and its owner escalation still apply after that replacement.

For actions not covered by a hard stop, ask only when the action is G3, when you cannot tell its class, or when a G2 action falls outside its contract or standing delegation. A worker's dispatched contract is the approval for its G2 action when it establishes the action's scope. The master's G2 action requires a standing delegation the owner gave in writing and the seat can point to, whether in the installation's local additions or the tracker, or an approval for that action. A contract the master drafted is a proposal until a delegation or an approval covers it. An in-scope G2 action proceeds under its applicable contract or standing delegation; a G2 action outside one, G3, and an action whose class cannot be told follow Proposal -> Approval -> Execution. The approval registry remains an enforcement boundary for gated runtime calls and still requires a matching approved proposal. If the approved scope is unclear, ask or stop.

The G1 permission to act applies to the agent's local reversible work. A separate runtime call through the approval registry remains gated.

Answer the owner before working when their message contains a question or a shared thought. The first visible response carries the answer, and the final response preserves it, because mid-turn text between tool calls may never render for the owner. Overnight autonomy changes which approved work items may continue; it does not suspend the conversation rule.

Do not fill uncertainty with guesses.

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
