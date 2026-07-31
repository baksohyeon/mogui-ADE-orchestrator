This guide maps Deep Agents concepts to the workspace-level concepts implemented or specified by mogui-ADE-orchestrator.

# Concepts

Deep Agents describes an agent harness in terms of execution, context, delegation, steering, and virtual filesystem access. mogui-ADE-orchestrator uses a similar mental model, but applies it to real sessions and repositories instead of an in-process agent runtime.

| Deep Agents component | mogui-ADE-orchestrator counterpart | Current status |
| --- | --- | --- |
| Execution Environment | Orca terminal sessions, script entry points, adapter dispatch, git worktrees | Implemented entry points and core helpers |
| Context Management | L0/L1 bootstrap context, Role State, issue-tracker memory audit, compaction recall probe, operations documents | Implemented bootstrap and digest pieces; issue tracker selected during onboarding |
| Delegation | Dispatch gate, worker contract, adapter dispatch, registration probe, acceptance gate | Implemented gate and adapter flow |
| Steering | `Proposal -> Approval -> Execution`, Role State, role lock, separated review lenses | Approval registry implemented; role and review rules are operating policy |
| Virtual Filesystem | Repository worktrees, context resolver, path observations, sensitive lane separation | Worktree and path helpers implemented; sensitive lane separation is policy/design |

## Status Labels

The public docs use implementation status labels narrowly:

| Label | Meaning |
| --- | --- |
| Configured | A file, script, hook, setting, or static contract exists in the repository or workspace. |
| Intended | The design contract is documented, but this page is not claiming live runtime evidence. |
| Observed | Git state, local execution, logs, ledgers, process state, or probes have shown the behavior outside an agent self-report. |
| Unknown | The current evidence does not prove the behavior, or the behavior is deliberately outside the public surface. |

The distinction matters because configured does not mean operating. A hook file, descriptor, or command can exist without proving that every worker path is forced through it. Public documentation should keep C/I/O/U separate instead of turning "present" into "working."

## Runtime Units

The master is easier to test when its responsibilities are named as runtime units, even if early implementations share one process or one CLI.

| Unit | Name | Responsibility |
| --- | --- | --- |
| U1 | Bootstrap | Load the minimum L0/L1 context needed to start safely. |
| U2 | Context Resolver | Decide whether a request belongs to the workspace, a repository, a worktree, or an external system. |
| U3 | Workspace Runtime | Own tracks, cross-repository state, and long-lived execution records. |
| U4 | Repository Runtime Loader | Load only the Repository Harness needed for the resolved target. |
| U5 | Worker Scheduler | Issue worker leases, choose isolation, dispatch workers, enforce budget, and reap resources. |
| U6 | Approval Manager | Classify action risk and bind execution to a valid approval state. |
| U7 | Role Runtime | Keep one active role, role lock, and role transition state. |
| U8 | Recovery Manager | Reattach, resume once, or reconstruct state before spawning a replacement session. |
| U9 | Succession Manager | Freeze mutable work, write a thin handoff, verify the successor, and retire the predecessor. |
| U10 | Lineage Recorder | Append audit metadata about succession quality without making lineage a bootstrap source. |
| U11 | Observability | Record probes, alerts, context quality, model identity, and acceptance evidence. |
| U12 | Adapter Layer | Isolate product-specific CLIs and file formats behind common contracts. |

For example, Context Resolver can decide that a request targets `polsia-api` or spans `polsia-api` and `polsia-ops`, Repository Runtime Loader can page in only the needed repository rules, Worker Scheduler can create a scoped lease, and Approval Manager can refuse a production-facing action until the correct gate is satisfied.

## Execution Environment

In Deep Agents, the execution environment is where the agent uses tools, files, and code execution. In this repository, the execution environment is an actual workspace.

The master can operate through script entry points such as `scripts/master-bootstrap`, `scripts/master-succeed`, `scripts/dispatch-gate`, `scripts/adapter`, and `scripts/l1-digest`. Worker execution is routed through the adapter layer. When parallel writes, branch anchoring, tree contention, or branch switching make shared checkout work risky, the adapter can plan a git worktree for isolation.

Example:

```bash
scripts/adapter dispatch \
  --contract ./contracts/job.md \
  --repo ./polsia-api \
  --isolation auto \
  --runtime codex \
  --agents 1 \
  --est-chars 2000 \
  --dry-run
```

> Tip: Use `--dry-run` when you want to inspect the dispatch plan without starting a worker.

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

The core approval registry enforces that gated actions must match an approved proposal before execution. The role-state file keeps exactly one active role and freezes the others until an explicit role switch.

For non-trivial merges or direct shared-state changes, the operating guide recommends separated review lenses:

```text
general correctness
regression disproof
contract and scope
```

These lenses are a review discipline, not a separate consensus engine in the current code.

## Repository Filesystem Model

Deep Agents exposes a virtual filesystem backed by pluggable storage. mogui-ADE-orchestrator does not provide that abstraction.

Instead, it treats the real repository filesystem as the boundary. The context resolver observes repository paths and git worktrees. The adapter can plan a worker worktree under the target repository when isolation is needed. Sensitive lanes are separated by operating policy and by routing to dedicated sessions, not by a public virtual filesystem implementation.

Read next: [Delegation and Review](delegation-and-review.md), then [Master Lifecycle](master-lifecycle.md). See [Reference](reference.md) for the local script entry points.
