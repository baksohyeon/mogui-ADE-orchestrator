# 03 — Choose And Create The Ops Repository (Steps 2–3)

Load rule: read this file only when Step 2 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `04-seat.md`.

## Step 2. Choose the ops repository

**Position and action:** Step 2 begins with a confirmed workspace inventory: recommend and obtain approval for the ops repository.

**Why/caution:** Governance needs a visible ownership boundary that cannot be confused with product code.

### Owner script (kind ELI5, adapt to the owner's language)

Where we are: the workspace facts are confirmed, and the Herald now needs a book for the Master to read from. What we decide next: where this workspace's governance records will live — a small repository that is clearly separate from product code. Explain like ELI5: product repositories hold the thing being built; the ops repository holds how the Master should coordinate that work. Ask whether to create a new repository or reuse an existing operations repository, and whether local Git initialization is allowed for a new ops repository; this choice applies only to `{{OPS_REPO}}`, never to `{{WORKSPACE_ROOT}}`.

Inspect the confirmed names; propose two or three candidates with pros and cons; recommend `<workspace>-ops`; evaluate governance clarity, separation from product scope, and shell-title ambiguity; use a structured choice when available.

### Verify (Step 2)

- `{{OPS_REPO}}` is an approved absolute path or repository name
- the selection was evaluated against the confirmed inventory
- no product repository name was reused

## Step 3. Create the ops repository

**Position and action:** Step 3 begins with an approved name: create or deliberately reuse the ops repository before registering it in Orca.

**Why/caution:** Read and merge existing files; never overwrite operations records or initialize Git without approval.

Ask for confirmation to create or reuse `{{OPS_REPO}}` and separate confirmation before local Git initialization of that ops repository.

If new or empty, copy the Stage 1 skeleton from `{{RUNTIME_ROOT}}/master-ops/`, excluding `TEMPLATE-VERSION`, `CHANGELOG.md`, `ONBOARDING.md`, and the `onboarding/` directory; if existing, merge deliberately after reading it. Do not push unless explicitly asked. The skeleton includes `workspace-card/` (canonical workspace-root session card); that directory copies with the rest of the skeleton and is not excluded.

### Verify (Step 3)

- the ops repository exists with its own agent instruction files `CLAUDE.md` and `AGENTS.md` (the ops-repo pair, kept byte-identical later — **not** the workspace session card), plus `docs/MASTER-OPERATIONS.md`, byte-identical `workspace-card/CLAUDE.md` and `workspace-card/AGENTS.md` (canonical session-card pair for later root deploy), and the rest of the Stage 1 skeleton
- only the allowed remaining placeholders are present
- `TEMPLATE-VERSION`, `CHANGELOG.md`, `ONBOARDING.md`, and the `onboarding/` directory are absent from the generated repository
