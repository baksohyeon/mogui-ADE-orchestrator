# §1. Document Map

Maps current state and document ownership. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Orca is REQUIRED infrastructure. Supervised dispatch = orca orchestration only. (charter rule since template v5)

The workspace master-operations SSOT is the charter index [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md); this file is its Document Map section.

Document roles stay narrow: a charter section may state a rule and its reason, a runbook may describe one recurring procedure and its worker Brief, a skill may state when to fire and point to a runbook while carrying its own method only when no runbook covers the operation, a workflow script may execute orchestration without serving as the prose procedure, and memory may hold a dated unstable owner preference with no procedure content until it becomes a runbook default; each surface keeps the other surfaces' content out.

- Template version: `{{TEMPLATE_VERSION}}` (source: installed `MANIFEST.json`, filled at onboarding from the template version stamp)
- Operations repository: `{{OPS_REPO}}`
- Workspace root: `{{WORKSPACE_ROOT}}`
- Workspace repositories: `{{REPO_LIST}}`
- Append-only evidence: `docs/decisions/closed-decisions-and-facts.md`, `docs/lineage/MASTER-LINEAGE.md`
- Field cards: `docs/runbooks/succession-boot-card.md`
- Role state SSOT: `docs/runbooks/role-state.md`
- Review voice (public-surface prose): [Review voice](../runbooks/review-voice.md)
- Observability suite: `docs/observability/README.md` — attribution legend, integrity rules, and the blame / postmortem / travelog genres
- Execution state SSOT: the issue tracker selected during onboarding, reachable from `{{WORKSPACE_ROOT}}`
- Long-term planning and design SSOT: Git documents

Issue-tracker memory should contain only load-bearing rules and pointers. Keep it curated; do not turn it into a second copy of this document.
