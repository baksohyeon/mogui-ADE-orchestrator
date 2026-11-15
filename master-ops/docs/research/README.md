# Research

Reusable research records for this workspace. The layout generalizes the research harness originated in the QFUDS repository and keeps evidence records separate from owner decisions.

Within `{{WORKSPACE_ROOT}}`, this directory uses the following layout:

```text
docs/research/
  literature/            verified external source records and index.csv
  investigations/<chain>/
    plans/               questions, scope, and execution plans
    coverage/            search breadth, skipped paths, and unverified hits
    conclusions/         closeouts: what changed and what stays open
```

The operational rules live in [Research workflow](../runbooks/research-workflow.md).

## Rules

- Keep plans, coverage, and conclusions in an investigation chain.
- A plan-only task needs no conclusion. An executed search, judgment, extraction, or failure needs a closeout.
- A closeout records created and modified paths, method, what changed, what did not change, and what stays open for the owner.
- Every literature row carries its URL, read date, and `read_how` value of `fetched` or `search summary only`.
- Unverified sources stay in `coverage/` until their claims are checked.
- "No" is a valid evidence result and remains part of the closeout.

The stage 1 layout keeps the literature index header-only until a verified source is recorded. A commented example shows the row shape without becoming a source record:

```csv
# example-source,"Example source",https://example.org/source,2026-11-15,fetched,example-topic,"Verified claim supported by the source"
```

Stage 1 adds the workflow and layout. It adds no commit guard, hook, or execution script. A later owner-approved stage can evaluate those additions after both seats have used this layout.
