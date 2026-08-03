# §1. Document Map

Maps current state and document ownership. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Orca is REQUIRED infrastructure. Supervised dispatch = orca orchestration only. (charter rule since template v5)

The workspace master-operations SSOT is the charter index [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md); this file is its Document Map section.

- Template version: `{{TEMPLATE_VERSION}}` (source: `{{RUNTIME_ROOT}}/master-ops/CHANGELOG.md`)
- Operations repository: `{{OPS_REPO}}`
- Workspace root: `{{WORKSPACE_ROOT}}`
- Workspace repositories: `{{REPO_LIST}}`
- Append-only evidence: `docs/decisions/closed-decisions-and-facts.md`, `docs/lineage/MASTER-LINEAGE.md`
- Field cards: `docs/runbooks/succession-boot-card.md`
- Role state SSOT: `docs/runbooks/role-state.md`
- Observability suite: `docs/observability/README.md` — attribution legend, integrity rules, and the blame / retro / travelog genres
- Execution state SSOT: the issue tracker selected during onboarding, reachable from `{{WORKSPACE_ROOT}}`
- Long-term planning and design SSOT: Git documents

Issue-tracker memory should contain only load-bearing rules and pointers. Keep it curated; do not turn it into a second copy of this document.
