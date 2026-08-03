# 03 — Choose And Create The Ops Repository (Steps 2–3)

Load rule: read this file only when Step 2 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `04-seat.md`.

## Step 2. Choose the ops repository

**Position and action:** Step 2 begins with a confirmed workspace inventory: recommend and obtain approval for the ops repository.

**Why/caution:** Governance needs a visible ownership boundary that cannot be confused with product code.

### Owner script (3–6 sentences, adapt to the owner's language)

Where we are: the workspace facts are confirmed. What we decide next: where this workspace's governance records will live — a small repository that is clearly separate from product code. Ask whether to create a new repository or reuse an existing operations repository, and whether local Git initialization is allowed for a new ops repository; this choice applies only to `{{OPS_REPO}}`, never to `{{WORKSPACE_ROOT}}`.

Inspect the confirmed names; propose two or three candidates with pros and cons; recommend `<workspace>-ops`; evaluate governance clarity, separation from product scope, and shell-title ambiguity; use a structured choice when available.

### Verify (Step 2)

- `{{OPS_REPO}}` is an approved absolute path or repository name
- the selection was evaluated against the confirmed inventory
- no product repository name was reused

## Step 3. Create the ops repository

**Position and action:** Step 3 begins with an approved name: create or deliberately reuse the ops repository before registering it in Orca.

**Why/caution:** Read and merge existing files; never overwrite operations records or initialize Git without approval.

Ask for confirmation to create or reuse `{{OPS_REPO}}` and separate confirmation before local Git initialization of that ops repository.

If new or empty, copy the Stage 1 skeleton from `{{RUNTIME_ROOT}}/master-ops/`, excluding `TEMPLATE-VERSION`, `CHANGELOG.md`, `ONBOARDING.md`, and the `onboarding/` directory; if existing, merge deliberately after reading it. Do not push unless explicitly asked.

### Verify (Step 3)

- the ops repository exists with `CLAUDE.md`, `AGENTS.md`, `docs/MASTER-OPERATIONS.md`, and the Stage 1 skeleton
- only the allowed remaining placeholders are present
- `TEMPLATE-VERSION`, `CHANGELOG.md`, `ONBOARDING.md`, and the `onboarding/` directory are absent from the generated repository
