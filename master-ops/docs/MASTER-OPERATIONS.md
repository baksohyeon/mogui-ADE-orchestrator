---
status: active
---

# MASTER-OPERATIONS

This is the master operations source of truth for the `mogui-master` workspace. It contains only currently active operating rules. Narrative logs, incident raw material, and product-specific specs live in their own files and are linked when needed.

Change rule: do not change this document without explicit user approval or an accepted decision record. When this document changes, check the related issue-tracker memory pointers and hook paths in the same change.

## The Master Operations Charter

The charter consists of nine sections covering the master's role, execution, and governance. Load one section at a time using the table below; sections not needed for your current task stay closed.

| Section | Topic | When to open | File |
|---------|-------|--------------|------|
| §1 | Document Map | Planning or orientation | [docs/charter/01-document-map.md](docs/charter/01-document-map.md) — maps current state and document ownership |
| §2 | Role Constitution | Role switch or Role Lock question | [docs/charter/02-role-constitution.md](docs/charter/02-role-constitution.md) — defines the master's role, allowed roles, and role-state format |
| §3 | Execution Principles | Proposal/Approval questions or scope drift | [docs/charter/03-execution-principles.md](docs/charter/03-execution-principles.md) — governs the default execution path and recovery procedures |
| §4 | Worker Routing and Review | Dispatch planning or worker evaluation | [docs/charter/04-worker-routing-review.md](docs/charter/04-worker-routing-review.md) — governs worker dispatch, model selection, and review practices |
| §5 | Dispatch Gate | Supervised dispatch planning | [docs/charter/05-dispatch-gate.md](docs/charter/05-dispatch-gate.md) — governs the supervised dispatch process and gate enforcement |
| §6 | Succession | Session continuity or master change | [docs/charter/06-succession.md](docs/charter/06-succession.md) — governs master succession and recovery procedures |
| §7 | Records | Document ownership or memory questions | [docs/charter/07-records.md](docs/charter/07-records.md) — governs document ownership and record separation |
| §8 | Boot, Hooks, and Observability | Configuration or measurement | [docs/charter/08-boot-hooks-observability.md](docs/charter/08-boot-hooks-observability.md) — governs boot configuration, hook wiring, and observability practices |
| §9 | Incident-Derived Rules | Understanding a safety measure | [docs/charter/09-incident-derived-rules.md](docs/charter/09-incident-derived-rules.md) — records rules from production incidents with measurement criteria |
| §10 | Closed Principles Pointer | Architecture or scope questions | [docs/charter/10-closed-principles-pointer.md](docs/charter/10-closed-principles-pointer.md) — references closed decisions and where to find them |
