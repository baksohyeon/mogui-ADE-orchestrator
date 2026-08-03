# Reverify — Health Check For An Already-Founded Workspace

Load rule: read this file only when the router's mode question answered **Reverify**. Router: [`../ONBOARDING.md`](../ONBOARDING.md). This mode uses no other step file.

**Position and action:** the workspace already has an ops repository and a master. Check health, report, and stop. Running the full founding steps against a founded workspace is time waste at best and a duplicate master at worst.

**Standing block: do not spawn.** No new master terminal, no `master-succeed spawn`, no founding kickoff. If a check fails badly enough that a new master seems needed, that is a succession decision for the owner and the living master — not a reverify outcome.

## Owner script (3–6 sentences, adapt to the owner's language)

Where we are: this workspace was already set up, so nothing will be installed or changed. What happens next: a handful of read-only checks — where the master sits, whether the tracker answers, and whether the governance records are current — and then a short pass/fail report. You do not need to type anything unless a check needs your decision.

## Checklist (all read-only)

1. **Seat**: the durable placement selector recorded in the ops repository still resolves on the host (`ORCA terminal list --worktree <selector> --json`), and exactly one live master terminal sits in it.
2. **Tracker**: from `{{WORKSPACE_ROOT}}`, `bd where` (or the equivalent) resolves to the ops repository, and no tracker database shadows it from above.
3. **Role state**: `docs/runbooks/role-state.md` names one active role with Role Lock state, and its Generation matches the last entry in `docs/lineage/MASTER-LINEAGE.md`.
4. **Lineage**: the last lineage entry's session evidence (session id, measured model) is present, and the measured model matches the configured one or the mismatch is explained.
5. **Operating card**: the owner still has the operating card from installation; if it is lost, reprint it from `10-card-and-retire.md` with current values — that is the one write this mode allows.
6. **Placeholders**: `rg '\{\{[^}]+\}\}' "{{OPS_REPO}}"` finds nothing, or every hit is an intentionally deferred value the owner can name.

## Report

State each check as pass or fail with its evidence, in the owner's language, short. A failed check gets one sentence of consequence and one recommended next action (usually: bring it to the living master as a task). Then stop; reverify has no further steps.
