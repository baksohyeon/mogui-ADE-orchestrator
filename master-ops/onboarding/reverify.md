# Reverify — Health Check For An Already-Founded Workspace

Load rule: read this file only when the router's mode question answered **Reverify**. Router: [`../ONBOARDING.md`](../ONBOARDING.md). This mode uses no other step file, with one exception: `10-card-and-retire.md` may be opened read-only to reprint a lost operating card (check 5).

**Position and action:** the workspace already has an ops repository and a master. Check health, report, and stop. Running the full founding steps against a founded workspace is time waste at best and a duplicate master at worst.

**Standing block: do not spawn.** No new master terminal, no `master-succeed spawn`, no founding kickoff. If a check fails badly enough that a new master seems needed, that is a succession decision for the owner and the living master — not a reverify outcome.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: this workspace was already set up, so nothing will be installed or changed at runtime. If the operating card is lost, reprinting it is the one allowed write. What happens next: a handful of checks — where the master sits, whether the tracker answers, and whether the governance records are current — and then a short pass/fail report. Provide the workspace root and ops repository path, or the operating card, before the checks when those facts are not already available.

## Checklist (read-only, except operating-card reprint)

0. **Bootstrap the facts first**: this mode never loads the steps that establish the workspace facts, so ask the owner for the workspace root and ops repository path (or the operating card, which carries both), then read the durable placement result from that ops repository. Do not scan the disk for candidate workspaces, and do not substitute this orchestrator clone's paths. Every `{{...}}` value below means the measured value from that ops repository, not a literal. Keep checks read-only unless check 5 must reprint a lost operating card.
1. **Seat**: the durable placement selector recorded in the ops repository still resolves on the host (`orca terminal list --worktree <selector> --json`), and exactly one live master terminal sits in it.
2. **Tracker**: from `{{WORKSPACE_ROOT}}`, `bd where` (or the equivalent) resolves to the ops repository, and no tracker database shadows it from above.
3. **Role state**: `docs/runbooks/role-state.md` names one active role with Role Lock state, and its Generation matches the last entry in `docs/lineage/MASTER-LINEAGE.md`.
4. **Lineage**: the last lineage entry's session evidence (session id, measured model) is present, and the measured model matches the configured one or the mismatch is explained.
5. **Operating card**: the owner still has the operating card from installation; if it is lost, reprint it from `10-card-and-retire.md` with current values — that is the one write this mode allows.
6. **Placeholders**: `rg '\{\{[^}]+\}\}' "{{OPS_REPO}}"` finds nothing, or every hit matches an owner-recorded deferral (same rule as the placeholders step (`05-placeholders.md`)); anything else is an installation error — fail reverify and have the owner bring it to the living master as a rescue task.
7. **Workspace session card**: the deployed root card matches the ops canonical — `cmp "{{WORKSPACE_ROOT}}/CLAUDE.md" "{{OPS_REPO}}/workspace-card/CLAUDE.md"` is silent (byte match). This is the workspace-root session card the agent host reads, **not** the ops repository's own agent instruction pair (`{{OPS_REPO}}/CLAUDE.md` / `AGENTS.md`) and **not** the owner-facing operating card from step 10. If the root file is missing or differs, **report drift only** — do not redeploy, do not overwrite either side. Bring the drift to the living master as a rescue task.

## Report

State each check as pass or fail with its evidence, in the owner's language, short. A failed check gets one sentence of consequence and one recommended next action (usually: bring it to the living master as a task). Then stop; reverify has no further steps.
