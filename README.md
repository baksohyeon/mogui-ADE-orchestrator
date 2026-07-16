# mogui-ADE-orchestrator

> A multi-repository **Master Runtime and orchestration layer** for long-lived AI engineering workspaces — role/runtime state, approval gates, succession, lineage, and cross-repo verification. Optimized for **Orca, Claude Code, and Codex** through pluggable, implementation-independent repository-runtime adapters.

Sibling product of [mogui-agent-harness](https://github.com/baksohyeon/mogui-agent-harness):

| | mogui-agent-harness | mogui-ADE-orchestrator (this repo) |
|---|---|---|
| Layer | Repository Harness (repo-local runtime) | Workspace Master Runtime |
| Unit of operation | one repository | a workspace of many repositories |
| Owns | repo-local rules, hooks, wiki, runbooks | orchestration state, roles, succession, lineage |

## Status

**Pre-implementation.** Architecture is frozen upstream (AHE + Master Runtime Charter — maintained in a separate workspace; concept docs will be published separately). This repo starts from the Reference Implementation plan in [`docs/planning/`](./docs/planning/).

First vertical slice: **U2 Context Resolver** — `resolve(path, workspace_manifest) -> ContextDescriptor`.

## Core / Adapter boundary

- `src/master_runtime/core/` — tool-name-free implementation of the frozen runtime units (context, bootstrap, workspace, repository, scheduler, approval, role, recovery, succession, lineage, observability). All external contact goes through core-declared contracts. Core must be fully testable with in-memory fakes.
- `src/master_runtime/adapters/` — first reference adapter set: `orca` (execution substrate), `claude` (orchestrator host), `codex` (delegated executor), `beads` (work ledger), `ctx` (trace archive), `git` (knowledge store), `repository_harness` (repo runtime conventions).
- Boundary test: deleting `adapters/` entirely must leave every core test green.

Orca / Claude / Codex are the first adapter set, **not** required abstractions of the core.

## Prerequisites

- Python **3.10+** (explicit prerequisite — stdlib only at runtime; `mypy` is an optional dev check)
- No package installation required to run tests: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

## Non-goals

repo-local rules/wiki/hooks/skills, repository harness installation, repository implementation knowledge. Those belong to repository harness products. Connection is adapter/contract only — no source-tree coupling (submodules only ever appear as pinned example/e2e fixtures, never as core dependencies).

## License

MIT
