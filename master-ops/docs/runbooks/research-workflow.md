# Research workflow

This workflow governs reusable research records in `docs/research/`. It generalizes the routing workflow that originated in the QFUDS repository for use in this template.

## Scope

Use this workflow when a research task searches external sources, records a plan or coverage boundary, produces an evidence-based result, or needs a durable closeout for the owner. Keep research records separate from operating decisions. The owner decides what an evidence record means for the workspace.

## Folder roles

Use these destinations:

| Destination | Use for | Do not use for |
| --- | --- | --- |
| `docs/research/literature/` | Reusable records for verified external sources, with one row in `literature/index.csv` per source | Search plans, coverage gaps, execution history, or owner decisions |
| `docs/research/investigations/<chain>/plans/` | Search questions, scope, prompts, and execution plans | Result claims or conclusions |
| `docs/research/investigations/<chain>/coverage/` | What was searched, what was found, what was skipped, and which sources remain unverified | Literature records or result claims |
| `docs/research/investigations/<chain>/conclusions/` | Result closeouts, evidence summaries, and open owner questions | Raw sources, plans, or unverified search hits |

`<chain>` is a stable, descriptive investigation name. Keep all records for one line of inquiry in the same chain so a reader can follow the plan, coverage, and conclusion together.

## Source and literature records

Every literature index row carries:

- a stable key and title;
- the source URL;
- the date the source was read, in `YYYY-MM-DD` form;
- `read_how`, recorded as `fetched` or `search summary only`;
- topics and a concise claim supported by the source.

Record a source in `literature/index.csv` only when the claim is verified to the level stated in the row. A source seen only in a search summary remains in the investigation's `coverage/` record until it is checked. Do not turn an unverified hit into a literature claim.

## Investigation flow

1. Write a plan in `plans/` before an execution when the questions, scope, or method need to be preserved.
2. Record search breadth, skipped paths, inaccessible sources, and search-summary-only hits in `coverage/`.
3. Add verified sources to `literature/index.csv` with the URL, read date, and read method. Keep the claim narrow enough for the recorded evidence.
4. Write a conclusion closeout after an execution, extraction, judgment, or failure changes what the investigation can say.
5. Update the relevant index or read-order record when adding a plan or conclusion. Keep unrelated indexes unchanged.

## When a conclusion closeout is required

Create or update a closeout when a search has been executed, an evidence result or judgment has been produced, an extraction or structured record has been created, or an execution has failed. A plan-only task needs no closeout.

## Required closeout content

Every closeout states:

- created paths;
- modified index or manifest paths;
- method used;
- what changed;
- what did not change;
- what stays open for the owner;
- evidence limits or unresolved coverage.

"No" is a valid answer. State it directly when the evidence does not support a requested result, and preserve the search or method that established that boundary.

## Index updates

Update `docs/research/literature/index.csv` for each verified literature record. Update a chain's local README or read-order record when the chain has one and a plan or conclusion is added. Put unverified sources and coverage expansion in `coverage/`. Do not update an unrelated index for appearance or completeness.

## Stage boundary

Stage 1 supplies this workflow, the `docs/research/` layout, and the literature index rule. It does not add a commit guard, hook, or execution script. Those changes require a later owner-approved stage after both seats have used the workflow.
