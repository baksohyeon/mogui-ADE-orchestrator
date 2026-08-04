# Workspace session card

`CLAUDE.md` in this directory is the **canonical** master session card — the file the agent host reads at the workspace root to learn who the master is, what its execution rule is, and how requests route to skills. The copy at the workspace root is a **deployment** of it, placed there because that is where the agent host reads it from.

This is not the ops repository's own agent instruction file pair (`CLAUDE.md` / `AGENTS.md` at the ops repository root). Those files describe how an agent works *inside* the ops repository. This card is the workspace-root session card. It is also not the owner-facing operating card printed in onboarding step 10.

Owner decision, 2026-08-05: the card lives here (in the ops repository after install; in the Stage 1 skeleton as `master-ops/workspace-card/`) and onboarding deploys a copy to the workspace root. The workspace root is a container for the product checkouts and is not itself a git repository, so a card kept only at the root is versioned nowhere, backed up nowhere, and shipped to a fresh install nowhere. That was the measured state until this directory existed.

## Editing

Edit the file here (or in the ops repository's `workspace-card/CLAUDE.md` after install), then redeploy to the workspace root. Never edit the root copy alone: it is the copy, and the next deployment overwrites it.

From the workspace root, after the card's installation values are filled (onboarding step 05 does this):

```bash
cp <ops-repo>/workspace-card/CLAUDE.md <workspace-root>/CLAUDE.md
```

Angle-bracket slots are filled by hand at redeploy time; this README carries no double-brace template placeholders, because step 03 copies it into the ops repository and step 05 asserts that no such placeholder remains there.

Onboarding step 05 deploys the filled card. Reverify check 7 compares the two and **reports drift only** — it does not silently redeploy. There is no harness self-check script for this pair in the template; the reverify entry is the check.

## The link base is the deployment location, not this one

**Decision (deliberate exception to the working-directory clause):** every path inside the card resolves from the **workspace root**, because that is where the card is read — not from `workspace-card/`, where it is stored. A link written relative to this storage directory would break the moment the file is deployed. This is the single place in the repository where a document's links are relative to somewhere other than its own directory, and it contradicts the working-directory clause in [contract conventions](../docs/runbooks/contract-conventions.md) on its face. That contradiction is intentional. Do not "fix" the card's links to resolve from this directory; that would break the deployed copy the master actually reads.

When editing, verify each link by resolving it from the workspace root (with the card's installation values already filled), not from this directory.

## What is not here

Instance-specific values that already have a home stay in their home. The seat path and workspace id belong to [role state](../docs/runbooks/role-state.md); operating rules belong to [Master Operations](../docs/MASTER-OPERATIONS.md). The card points at those files instead of restating them, so each fact has one place to be corrected. Product-repository test commands are measured from each product repository's own CI, not baked into this template card.
