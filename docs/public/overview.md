mogui-ADE-orchestrator is a session-level orchestration harness for coordinating long-lived AI engineering work across real repositories, terminals, and successor sessions.

# Overview

Most coding agents are strongest inside one repository, one terminal, and one context window. Workspace orchestration is a different problem. A master session has to remember active tracks, route work to isolated workers, verify outputs, survive compaction, and hand control to a clean successor when a session should end.

mogui-ADE-orchestrator runs at that orchestration layer on Orca ADE. It does not call model APIs and it is not an in-process agent framework. It manages sessions of AI agents, git repositories, terminals, operational records, approval gates, and succession records.

## The Problem

A single coding-agent session can coordinate a lot of work, but three failure modes become visible in multi-repository workspaces.

Context runs out before the work ends. Summaries help, but they do not prove that role state, accepted decisions, and active work all survived.

Session state is volatile. A crash, manual clear, compaction, or stale terminal can leave the next session with only a partial memory of the work.

Delegation needs supervision. It is easy to start worker sessions, but the master still needs to know which contract was dispatched, where it ran, what evidence came back, and whether the result was independently accepted.

## The Approach

This repository treats the master as a long-lived operating role rather than a single process that must last forever.

The master session owns planning, task decomposition, review, acceptance, and cross-repository coordination. Worker sessions receive narrow contracts and return artifacts plus evidence. The master accepts only after independent verification.

The operating state is promoted out of chat into durable stores. Execution state belongs in an issue tracker or ledger. Long-term procedures, decisions, runbooks, and lineage belong in git documents. Chat context stays useful, but it is not the only source of truth.

Succession is explicit. A current master can build a thin handoff, spawn a clean successor, verify that the successor recovered the inherited state, then retire the predecessor. Advisory signals can propose succession, but the current implementation does not auto-succeed a master without an explicit trigger.

> Note: The public docs describe the control model. Host-specific wiring, workspace-specific path policy, and sensitive-lane implementation are intentionally outside this public surface.

## Core Capabilities

Execution environment: Orca-managed terminals and git worktrees are the real execution boundary. The adapter layer can decide whether a worker can share a checkout or needs a separate worktree.

Context management: bootstrap code loads a bounded L0/L1 context block, parses Role State, audits issue-tracker memory summaries when available, and includes compaction-specific recall probes.

Delegation: the dispatch gate follows `check -> dispatch -> register`. A readable worker contract is checked before dispatch, and a job is registered only after a probe verifies the job identity.

Steering: the operating rule is `Proposal -> Approval -> Execution`. Role State limits which kind of work the master may perform, and non-trivial acceptance can use separated review lenses.

Filesystem model: this project does not provide a virtual filesystem. Its analogue is repository-level isolation: path resolution, per-repository worktrees, and operating rules that keep sensitive lanes separate from ordinary implementation work.

## Related Work

[LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) addresses a similar reliability problem inside an agent application. It is a high-level abstraction built on the LangGraph runtime, with built-in support for an execution environment, context management, delegation, steering, and virtual filesystem access.

mogui-ADE-orchestrator works at a different layer. Deep Agents wires an execution graph inside a process. This project wires real agent sessions, validation steps, worker contracts, git checkouts, terminal placement, and succession loops through operating discipline and scriptable entry points. The problem space overlaps, but the control plane is different.

## Where To Go Next

Start with [Getting Started](getting-started.md) for the shortest path into the repository. Read [Concepts](concepts.md) for the component mapping, [Master Lifecycle](master-lifecycle.md) for boot and succession, and [Delegation and Review](delegation-and-review.md) for worker contracts and acceptance.
