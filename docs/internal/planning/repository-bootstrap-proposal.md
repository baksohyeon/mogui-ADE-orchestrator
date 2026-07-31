# Repository Bootstrap Proposal (accepted)

> Decision record, 2026-07-16: the Master Runtime is a separate product from the repository harness.

## Product boundary

- Owns: multi-repository workspace orchestration, master role/runtime state, repository resolution, worker scheduling, approval gates, recovery & succession, lineage, cross-repo verification/observability.
- Does not own: repo-local rules/wiki/ADR/runbooks/hooks/skills, repository implementation knowledge, harness installation. Repository harness products (e.g. mogui-agent-harness) remain independent.

## Harness connection decision

Compared: (A) git submodule, (B) optional adapter dependency, (C) external CLI/protocol.
**Adopted: B as the default, with C as B's transport.** The repository_harness adapter reads a target repo's published conventions at file/CLI level. Submodules are permitted only as pinned fixtures for examples/e2e — never as a core dependency. Core contracts stay implementation-independent; Orca/Claude/Codex are the first reference adapter set, not required abstractions.

## Relationship to mogui-agent-harness

No changes required there. The two repos never import each other's file structure; connection is versioned adapter contract or CLI protocol only.

## Workspace case studies

Real workspace coordinates never enter this repo. Public examples use a synthetic workspace (`examples/synthetic-workspace/` — backend/frontend/planning). Real workspaces are private local manifests or internal case studies.

## Naming

`mogui-ADE-orchestrator` (chosen by owner, 2026-07-16) — ADE = Agentic Development Environment. Repo starts private; public publication is a separate later gate (docs reviewed before publishing).
