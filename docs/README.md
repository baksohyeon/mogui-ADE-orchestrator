# Document index

Three sets of documents live in this repository, and they are separate because they have different readers and different lifetimes.

| Set | Reader | Lifetime |
| --- | --- | --- |
| [`docs/public/`](./public/) | someone reading about this system | stays in this repository |
| [`master-ops/`](../master-ops/) | someone installing the system, and the master agent that runs afterwards | copied out and substituted into a new operations repository |
| [`docs/internal/`](./internal/) | contributors to this repository | stays in this repository, ages fast |

Files under `master-ops/` are **templates**: `{{PLACEHOLDER}}` tokens are live, and onboarding Stage 1 replaces them. Do not read them as a description of this repository, and do not fill in placeholders here.

## docs/public, the explanation

Read in this order:

1. [`overview.md`](./public/overview.md), what problem this solves, when it is worth it, related work
2. [`getting-started.md`](./public/getting-started.md), shortest path into the repository
3. [`concepts.md`](./public/concepts.md), the vocabulary: runtime units, evidence labels, the four capability areas
4. [`master-lifecycle.md`](./public/master-lifecycle.md), boot, role state, compaction, succession
5. [`delegation-and-review.md`](./public/delegation-and-review.md), worker contracts, the dispatch gate, acceptance
6. [`reference.md`](./public/reference.md), script entry points, generated from local `--help` output

These pages describe the control model. Host-specific hook wiring, workspace path policy, and sensitive-lane implementation sit outside this public surface.

## master-ops, the template

[`master-ops/ONBOARDING.md`](../master-ops/ONBOARDING.md) is the entry point: an agent-executed, two-stage flow that scaffolds an operations repository for a new workspace and ends with a founding master session. `master-ops/docs/` holds the operations documents that get copied into that new repository, charter, role state, succession card, lineage ledger, and the observability suite (retro, travelog, field notes, agent journey).

Orca ADE is a hard prerequisite for the onboarding flow.

## docs/internal, contributor material

| Path | What it is |
| --- | --- |
| [`internal/specs/`](./internal/specs/) | narrow specs for wiring gaps and for behaviour not yet built |
| [`internal/tooling/`](./internal/tooling/) | [`redaction-scan.md`](./internal/tooling/redaction-scan.md), run this before publishing anything |

These describe how something works or is meant to work. Nobody keeps them current against the code, so when a document and the code disagree, trust the code and its tests.

Planning documents and worker reports are not kept here. They record what a decision looked like on one day, they go stale immediately, and git history holds them.

## Language

Everything a reader or installer touches, `README.md`, `docs/public/`, `docs/README.md`, `master-ops/`, is English. A Korean mirror of `docs/public/` is maintained outside this repository, in the operations repository of the workspace that authors it, so a translation cannot drift against its English original inside the same tree without a check catching it.
