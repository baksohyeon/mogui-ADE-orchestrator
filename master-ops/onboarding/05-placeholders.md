# 05 — Replace Template Placeholders (Step 4)

Load rule: read this file only when Step 4 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `06-tracker.md`.

**Position and action:** Step 4 begins with the skeleton in place: replace every placeholder with confirmed or measured local facts.

**Why/caution:** Keep product-specific rules in product repositories and keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user accepts host-specific divergence.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the ops repository skeleton exists, and the earlier steps recorded the owner's confirmed names and choices. What we do next: fill the remaining placeholders from those facts and local measurements, then verify the generated files. Pause to ask only if a required value was never decided.

## Run

Fill `{{RUNTIME_ROOT}}` from the current repository root and `{{TEMPLATE_VERSION}}` from its single-line `master-ops/TEMPLATE-VERSION`; do not ask for either. Pass `{{OPS_REPO}}/docs/MASTER-OPERATIONS.md` as `master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`. Add no placeholders.

## Verify

```console
$ ! rg --hidden -g '!.git/**' -g '!.beads/**' '\{\{[^}]+\}\}' "{{OPS_REPO}}"
$ cmp "{{OPS_REPO}}/CLAUDE.md" "{{OPS_REPO}}/AGENTS.md"
```

Also verify no source workspace's private names were copied accidentally.

## If fail

- `rg` still finds `{{...}}` tokens: fill each from the confirmed facts, or record the owner's explicit deferral for that value; never delete a placeholder to silence the check.
- `cmp` shows `CLAUDE.md` and `AGENTS.md` differ: if the divergence is byte-only formatting, re-unify to one common block in both files; if a substantive line exists in only one file, stop and ask whether host-specific divergence is intended.
