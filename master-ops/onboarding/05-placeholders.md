# 05 — Replace Template Placeholders (Step 4)

Load rule: read this file only when Step 4 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `06-tracker.md`.

**Position and action:** Step 4 begins with the skeleton in place: replace every placeholder with confirmed or measured local facts, then deploy the filled workspace session card to the workspace root.

**Why/caution:** Keep product-specific rules in product repositories and keep the ops repository's own agent instruction pair (`CLAUDE.md` and `AGENTS.md` at the ops repository root) byte-identical unless the user accepts host-specific divergence. That pair is a different file from `workspace-card/CLAUDE.md` (canonical session card) and from the deployed root `CLAUDE.md` (deployment of that card). The master reads the root card at boot, so deployment happens in this step — after placeholders are gone, and well before the spawn step (`09-spawn.md`).

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the ops repository skeleton exists, and the earlier steps recorded the owner's confirmed names and choices. What we do next: fill the remaining placeholders from those facts and local measurements, verify the generated files, and place the master's session card at the workspace root so the host can read it when the master boots. Pause to ask only if a required value was never decided.

## Run

Fill `{{RUNTIME_ROOT}}` from the current repository root and `{{TEMPLATE_VERSION}}` from its single-line `master-ops/TEMPLATE-VERSION`; do not ask for either. Pass `{{OPS_REPO}}/docs/MASTER-OPERATIONS.md` as `master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`. Include every file under the ops repository that still carries `{{...}}`, including `workspace-card/CLAUDE.md`. Add no placeholders.

**Placeholder constraint (chosen path):** fill the session card's placeholders in this step with the rest of the ops repository, then run the no-placeholder assertion. Do not leave `{{...}}` in `workspace-card/` and do not special-case the assertion to ignore the card — the card is ordinary filled content.

After the no-placeholder and ops-pair checks pass, deploy the filled session card to the workspace root (overwrite the root copy; the ops repository file remains the canonical):

```console
$ cp "{{OPS_REPO}}/workspace-card/CLAUDE.md" "{{WORKSPACE_ROOT}}/CLAUDE.md"
```

The root file is outside every git repository. Links inside the card resolve from `{{WORKSPACE_ROOT}}`, not from `workspace-card/` — see [workspace-card README](../workspace-card/README.md).

## Verify

```console
$ ! rg --hidden -g '!.git/**' -g '!.beads/**' '\{\{[^}]+\}\}' "{{OPS_REPO}}"
$ cmp "{{OPS_REPO}}/CLAUDE.md" "{{OPS_REPO}}/AGENTS.md"
$ cmp "{{WORKSPACE_ROOT}}/CLAUDE.md" "{{OPS_REPO}}/workspace-card/CLAUDE.md"
```

- The first `cmp` is the **ops repository agent instruction pair** only (root `CLAUDE.md` vs `AGENTS.md` inside `{{OPS_REPO}}`).
- The second `cmp` is the **workspace session card** (deployed root copy vs canonical `workspace-card/CLAUDE.md`). Never cross-compare those two pairs.

Also verify no source workspace's private names were copied accidentally.

## If fail

- `rg` still finds `{{...}}` tokens: fill each from the confirmed facts, or record the owner's explicit deferral for that value; never delete a placeholder to silence the check.
- ops-pair `cmp` shows `CLAUDE.md` and `AGENTS.md` differ: if the divergence is byte-only formatting, re-unify to one common block in both files; if a substantive line exists in only one file, stop and ask whether host-specific divergence is intended.
- session-card `cmp` fails or the root file is missing: redeploy with the `cp` above from the filled canonical file; do not invent root-only edits.
