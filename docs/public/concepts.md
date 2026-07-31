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

## Execution Environment

In Deep Agents, the execution environment is where the agent uses tools, files, and code execution. In this repository, the execution environment is an actual workspace.

The master can operate through script entry points such as `scripts/master-bootstrap`, `scripts/master-succeed`, `scripts/dispatch-gate`, `scripts/adapter`, and `scripts/l1-digest`. Worker execution is routed through the adapter layer. When parallel writes, branch anchoring, tree contention, or branch switching make shared checkout work risky, the adapter can plan a git worktree for isolation.

Example:

```bash
scripts/adapter dispatch \
  --contract ./contracts/job.md \
  --repo ./product-api \
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

Read next: [Delegation and Review](delegation-and-review.md), then [Master Lifecycle](master-lifecycle.md).
