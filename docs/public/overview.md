mogui-ADE-orchestrator is a session-level orchestration harness for coordinating long-lived AI engineering work across real repositories, terminals, and successor sessions.

# Overview

Most coding agents are strongest inside one repository, one terminal, and one context window. Workspace orchestration is a different problem. A master session has to remember active tracks, route work to isolated workers, verify outputs, survive compaction, and hand control to a clean successor when a session should end.

mogui-ADE-orchestrator runs at that orchestration layer on Orca ADE. It does not call model APIs and it is not an in-process agent framework. It manages sessions of AI agents, git repositories, terminals, operational records, approval gates, and succession records.

## The Problem

A single coding-agent session can coordinate a lot of work, but three failure modes become visible in multi-repository workspaces.

Context runs out before the work ends. Summaries help, but they do not prove that role state, accepted decisions, and active work all survived.

Session state is volatile. A crash, manual clear, compaction, or stale terminal can leave the next session with only a partial memory of the work.

Delegation needs supervision. It is easy to start worker sessions, but the master still needs to know which contract was dispatched, where it ran, what evidence came back, and whether the result was independently accepted.

Those problems became concrete in a Polsia workspace. Product work crossed planning, `polsia-api`, frontend, and `polsia-ops` repositories; API contract changes had to propagate across repository boundaries; and long-running sessions kept approaching context limits before the work was ready to stop. A separate failure mode came from unsupervised workers: a worker could claim completion, repeat a self-invented instruction, or touch a checkout outside the intended review lane unless the master treated the report as a claim and required external evidence.

The harness exists because these failures combine. Context durability, repository routing, worker dispatch, evidence review, and succession are not independent conveniences when the same track outlives one session.

## The Approach

This repository treats the master as a long-lived operating role rather than a single process that must last forever.

The master session owns planning, task decomposition, review, acceptance, and cross-repository coordination. Worker sessions receive narrow contracts and return artifacts plus evidence. The master accepts only after independent verification.

The operating state is promoted out of chat into durable stores. Execution state belongs in an issue tracker or ledger. Long-term procedures, decisions, runbooks, and lineage belong in git documents. Chat context stays useful, but it is not the only source of truth.

Succession is explicit. A current master can build a thin handoff, spawn a clean successor, verify that the successor recovered the inherited state, then retire the predecessor. Advisory signals can propose succession, but the current implementation does not auto-succeed a master without an explicit trigger.

> Note: The public docs describe the control model. Host-specific wiring, workspace path policy, and sensitive-lane implementation sit outside this public surface.

## When It Is Worth It

This design is useful when at least two pressures show up together: tracks last longer than a single session, one task spans repositories such as `polsia-api` and `polsia-ops`, several workers can run at once, or the work touches production-facing authority. In those cases, a ledger, thin handoff, worker lease, evidence bundle, approval gate, and recovery path reduce repeated explanation and make acceptance auditable.

The design is too heavy for a short task in one repository with one agent. In that case, a repository instruction file, an issue tracker entry, and a current session summary may be enough. The smallest transferable rules are: keep the source of truth outside the chat, treat succession as a normal lifecycle event, and never use an agent's self-report as completion evidence.

## Core Capabilities

Execution environment: Orca-managed terminals and git worktrees are the real execution boundary. The adapter layer can decide whether a worker can share a checkout or needs a separate worktree.

Context management: bootstrap code loads a bounded L0/L1 context block, parses Role State, audits issue-tracker memory summaries when available, and includes compaction-specific recall probes.

Delegation: the dispatch gate follows `check -> dispatch -> register`. A readable worker contract is checked before dispatch, and a job is registered only after a probe verifies the job identity.

Steering: the operating rule is `Proposal -> Approval -> Execution`. Role State limits which kind of work the master may perform, and non-trivial acceptance can use separated review lenses.

Filesystem model: this project does not provide a virtual filesystem. Its analogue is repository-level isolation: path resolution, per-repository worktrees, and operating rules that keep sensitive lanes separate from ordinary implementation work.

## Related Work

This section was written after this project was built, not as a starting point for it. The two designs converged; one did not follow the other. The repository history is consistent with that reading and `git log -S deepagents --reverse` shows when the comparison entered.

LangChain's [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) solves an adjacent reliability problem inside an agent application. It is a standalone library built on LangChain's core agent building blocks that uses the LangGraph runtime for durable execution, streaming, and human-in-the-loop. Its documentation organizes a harness around four areas: execution environment (tools, virtual filesystem, optional sandbox, REPL), context management (skills, memory, summarization, context offloading, prompt caching), delegation (subagent spawning and optional task planning), and steering (approval and interrupts). These are implemented as middleware such as `FilesystemMiddleware`, `TodoListMiddleware`, and `SubAgentMiddleware` over pluggable filesystem backends. *(Source: the linked overview page, read 2026-07-31. This project has not audited the deepagents source; claims here are limited to that page.)*

The four areas are a good decomposition, and this project arrives at nearly the same list. If you are willing to hold an API key, deepagents is the better answer and this page is not trying to talk you out of it. The difference below matters only if you are not.

deepagents assumes model API access from inside a Python process. The harness owns the graph, the tools, and the filesystem abstraction, so a subagent is an in-process actor, a filesystem is a pluggable backend, and an interrupt is a runtime callback.

mogui-ADE-orchestrator assumes no model API at all. It never calls a model endpoint and holds no API key; its execution substrate is subscription CLI agents running in real terminals against real git checkouts. So the same four areas resolve differently: a subagent is an actual CLI session dispatched under a contract and confirmed by an artifact probe, a filesystem is a git worktree, and an interrupt is an approval gate a human holds. Succession, replacing the orchestrator session itself while the work continues, has no counterpart in the in-process model, because a process that owns the graph cannot hand the graph to its successor.

Same failure modes, different control plane, and a different cost model: one is bought per token through an SDK, the other is built on top of subscriptions that were already paid for.

## Where To Go Next

Start with [Getting Started](getting-started.md) for the shortest path into the repository. Read [Concepts](concepts.md) for the vocabulary, evidence labels, runtime units, and which mechanism covers each capability area, then [Master Lifecycle](master-lifecycle.md) for boot and succession, [Delegation and Review](delegation-and-review.md) for worker contracts and acceptance, and [Reference](reference.md) for script entry points.
