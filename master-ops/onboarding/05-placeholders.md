# 05 — Replace Template Placeholders (Step 4)

Load rule: read this file only when Step 4 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `06-tracker.md`.

**Position and action:** Step 4 begins with the skeleton in place: replace every placeholder with confirmed or measured local facts.

**Why/caution:** Keep product-specific rules in product repositories and keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user accepts host-specific divergence.

## Owner script (3–6 sentences, adapt to the owner's language)

Where we are: the ops repository skeleton exists. What we decide next: the few remaining blanks that only the owner can confirm. Ask for each unresolved value and any coordination exclusions, one short turn at a time.

## Run

Fill `{{RUNTIME_ROOT}}` from the current repository root and `{{TEMPLATE_VERSION}}` from its single-line `master-ops/TEMPLATE-VERSION`; do not ask for either. Pass `{{OPS_REPO}}/docs/MASTER-OPERATIONS.md` as `master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`. Add no placeholders.

## Verify

```console
$ ! rg '\{\{[^}]+\}\}' "{{OPS_REPO}}"
$ cmp "{{OPS_REPO}}/CLAUDE.md" "{{OPS_REPO}}/AGENTS.md"
```

Also verify no source workspace's private names were copied accidentally.
