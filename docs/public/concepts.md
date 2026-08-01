This guide defines the vocabulary the rest of the public documentation uses: how evidence is labelled, what the runtime units are, and which mechanism covers each capability area.

# Concepts

A master session is an operating role, not a process. That single choice drives everything else here: if the role outlives any one process, then state has to live outside the process, handoffs have to be verified rather than trusted, and every capability has to be describable as "which mechanism, and what evidence."

## Evidence Labels

The public docs use four implementation status labels:

| Label | Meaning |
| --- | --- |
| Configured | A file, script, hook, setting, or static contract exists in the repository or workspace. |
| Intended | The design contract is documented, but this page is not claiming live runtime evidence. |
| Observed | Git state, local execution, logs, ledgers, process state, or probes have shown the behavior outside an agent self-report. |
| Unknown | The current evidence does not prove the behavior, or the behavior sits outside the public surface. |

The distinction matters because configured does not mean operating. A hook file, descriptor, or command can exist without proving that every worker path is forced through it. These pages keep C/I/O/U separate instead of turning "present" into "working."

One consequence worth stating plainly: a passing test suite is local execution evidence for the unit under test, and nothing more. It does not show that an operating workspace routes real work through that unit.

## Capability Areas

Five areas cover what a master has to do. Each row names the mechanism in this repository and the strongest label the evidence supports.

| Area | Mechanism here | Label | Evidence and limits |
| --- | --- | --- | --- |
| Execution environment | Orca terminal sessions, `scripts/` entry points, `adapter/dispatch`, git worktrees via `adapter/isolation` | Observed | The unit suite covers the entry points and isolation planning. Terminal placement is host behavior, not code in this repository. |
| Context management | `bootstrap.py` and `bootstrap_live.py` L0/L1 block, Role State parsing, issue-tracker memory audit, compaction recall probe | Observed | The suite runs the boot block, Role State parsing, and compaction suppression locally. The memory audit calls an external tracker command; without one it degrades and still exits clean. |
| Delegation | `dispatch_gate.py` check/register, worker contract file, `adapter/dispatch`, JSONL gate ledger | Observed | Gate decisions and ledger writes are observable after the fact. Whether *every* worker-creation path in a given workspace goes through the gate is Unknown from this repository alone; that is a workspace wiring property. |
| Steering | `approval/registry.py` and `approval/gates.py`, Role State file, role lock, separated review lenses | Mixed | The approval registry is Observed (gated actions must match an approved proposal). Role lock and review lenses are Intended; they are operating policy, not enforcement code. |
| Repository filesystem model | `context/resolver.py` path resolution, per-repository worktrees, sensitive-lane routing | Mixed | Path resolution and worktree planning are Observed. Sensitive-lane separation is Intended *in this repository*; it is a routing rule, and the blocking that enforces it lives in a workspace's own host hooks, outside this public surface. |

That last row is a deliberate split. Operating workspaces do enforce the sensitive lane with host-level hooks, and that enforcement has been observed live; but this repository ships the rule, not the block. Claiming otherwise would put someone else's hook configuration in our status table.

## Runtime Units

The master is easier to test when its responsibilities are named as runtime units, even if early implementations share one process or one CLI. The unit numbers are design vocabulary. The module layout is what exists.

| Unit | Name | Responsibility | Module |
| --- | --- | --- | --- |
| U1 | Bootstrap | Load the minimum L0/L1 context needed to start safely. | `bootstrap.py`, `bootstrap_live.py` |
| U2 | Context Resolver | Decide whether a request belongs to the workspace, a repository, a worktree, or an external system. | `context/` |
| U3 | Workspace Runtime | Own tracks, cross-repository state, and long-lived execution records. | `work_ledger.py` (`WorkspaceRuntime`) |
| U4 | Repository Runtime Loader | Load only the Repository Harness needed for the resolved target. | none (design only) |
| U5 | Worker Scheduler | Issue worker leases, choose isolation, dispatch workers, enforce budget, and reap resources. | partial: `dispatch_gate.py`, `adapter/dispatch.py`, `adapter/isolation.py`; no lease or reap module |
| U6 | Approval Manager | Classify action risk and bind execution to a valid approval state. | `approval/` |
| U7 | Role Runtime | Keep one active role, role lock, and role transition state. | partial: `RoleState` is parsed in `bootstrap.py`; the lock itself is policy |
| U8 | Recovery Manager | Reattach, resume once, or reconstruct state before spawning a replacement session. | `recovery.py` |
| U9 | Succession Manager | Freeze mutable work, write a thin handoff, verify the successor, and retire the predecessor. | `succession.py` |
| U10 | Lineage Recorder | Append audit metadata about succession quality without making lineage a bootstrap source. | `lineage.py` |
| U11 | Observability | Record probes, alerts, context quality, model identity, and acceptance evidence. | partial: `digest_loop.py`, `watchdog.py`, `acceptance/` |
| U12 | Adapter Layer | Isolate product-specific CLIs and file formats behind common contracts. | `adapter/` |

Two units have no module and two more are partial. That is the honest state, and it is the reason the table above exists: a unit number is a place to put a responsibility, not a claim that the responsibility is implemented.

For example, Context Resolver can decide that a request targets `polsia-api` or spans `polsia-api` and `polsia-ops`, Worker Scheduler can create a scoped dispatch, and Approval Manager can refuse a production-facing action until the correct gate is satisfied.

## Execution Environment

The execution environment is an actual workspace: real checkouts, real terminals, real CLI agent sessions.

The master can operate through script entry points such as `scripts/master-bootstrap`, `scripts/master-succeed`, `scripts/dispatch-gate`, `scripts/adapter`, `scripts/acceptance-loop`, and `scripts/l1-digest`. A worker is a CLI session started in an Orca pane, and `scripts/dispatch-gate` decides whether that dispatch may proceed.

## Context Management

The master starts from durable context, not only from chat history.

L0 is the stable operating frame: the charter, role rules, and standing coordination rules. L1 is active working context: current tracks, handoff state, digest observations, and recent operational evidence. `scripts/master-bootstrap` loads a bounded L0/L1 block and parses Role State from a handoff when one is present.

`scripts/master-bootstrap-live` is the session-start entry point. It loads Role State, collects active-track lines through the issue tracker command when available, audits memory summaries, and emits a small bootstrap block. On compaction, it suppresses role and track details first so the continuing session must recall them before comparing against durable state.

Example:

```bash
scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

> Note: The compaction behavior is a recall probe, not a data-loss recovery system. Accepted state still has to be promoted into the issue tracker or git documents.

## Delegation

Delegation is contract based. The master does not send an open-ended instruction and trust the worker report.

The dispatch gate evaluates a readable contract before a worker starts. The adapter can then launch a worker command. After the worker reports a job id, the register step accepts the dispatch only if an independent probe confirms the job id appears in an expected artifact.

The public concept is simple:

```text
check -> dispatch -> register -> independent verification -> acceptance
```

This keeps the master able to answer four questions: what was dispatched, which contract authorized it, where it ran, and which evidence justified acceptance.

## Steering

Steering is the human and policy layer that decides what the master may do.

The operating rule is:

```text
Proposal -> Approval -> Execution
```

The core approval registry enforces that gated actions must match an approved proposal before execution. The role-state file keeps one active role and freezes the others until someone switches it.

For non-trivial merges or direct shared-state changes, the operating guide recommends separated review lenses:

```text
general correctness
regression disproof
contract and scope
```

These lenses are a review discipline, not a separate consensus engine in the current code.

## Repository Filesystem Model

There is no virtual filesystem here. The real repository filesystem is the boundary.

The context resolver observes repository paths and git worktrees. The adapter can plan a worker worktree under the target repository when isolation is needed. The operating rule routes sensitive lanes to dedicated sessions. What enforces that rule is host-level hook configuration in the operating workspace, not code in this repository.

## Acceptance

Acceptance is a separate step from worker completion, and it has its own machinery. `acceptance/` evaluates a candidate against a casebook: raw case results and aggregated scores are distinct types, the casebook, not the evaluator, owns which split each case belongs to, and a single predicate decides holdout visibility, so nobody can loosen the private-holdout invariant by editing a second copy of the rule. A candidate that changes nothing still produces a decision record, so "we looked and did nothing" stays auditable.

Read next: [Delegation and Review](delegation-and-review.md), then [Master Lifecycle](master-lifecycle.md). See [Reference](reference.md) for the local script entry points, and [Overview](overview.md#related-work) for how this compares to in-process agent harnesses.
