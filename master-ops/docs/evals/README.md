# Evaluation evidence and preregistration

This directory is where charter [§11 Earn Its Place](../charter/11-earn-its-place.md) keeps its
ledger and its preregistration shape. It follows the pattern of
[gstack ETHOS §9 "Earn Its Place"](https://github.com/garrytan/gstack-evals), applied to this
template: every harness part either ships with evidence that it helps, or with a stated reason,
an owner, and a measure-by date. This template ships no runner. A plan here is a document; the
trials are run by whoever owns the plan, with whatever harness they have.

## `evidence.json` and `evidence.instance.json`

The template ledger is one JSON object: `{"measured_at": "<date>", "parts": [...]}`.
`measured_at` is the date the ledger itself was last reviewed as a whole, not the date of any
one part's trial. An install that wants to track its own parts adds rows to the optional
`evidence.instance.json`, which is instance-owned in `MANIFEST.json` and survives template
upgrades. `harness-inventory` merges both ledgers; the local file uses the same object and row
schema, and its absence means that the install has no local rows.

Each entry in `parts` is one harness part:

| Field | Meaning |
|---|---|
| `key` | The part's path relative to the template root, or a declared name for a hook's stdout. A card, skill, memory, or shared part is sized from disk by its path; a hook or dispatch part is `exec` instead (see below), and a hook's stdout at a given event is not a file at all, so it gets a declared name, carried with `measured_tokens` |
| `kind` | `card`, `skill`, `hook`, `memory`, `dispatch`, or `shared` |
| `loads` | `every session`, `every prompt`, `every use`, or `every dispatch` |
| `status` | `helps`, `no-effect`, `hurts`, `untested`, or `safety` |

What else a row carries depends on `status`:

- `helps` / `no-effect` / `hurts`: `sources` (a list of strings naming the trial or trials) and,
  optionally, `caveats`.
- `untested`: `plan`, a string, and it is always one of two shapes: `"none (grandfathered)"`, or a
  pointer or promise to a prereg page (the shape in the next section). `"none (grandfathered)"`
  means the part predates this ledger and has not yet been queued for a trial; it carries no
  `owner` or `measure_by` of its own; a grandfathered part gets both the day the master reaches it
  in rank order, because `scripts/harness-inventory`'s table is that queue. Any other plan string
  also needs `owner` and `measure_by` (`YYYY-MM-DD`), and a plan string that only names a review
  style ("first-use review") without yet pointing at a prereg page is a placeholder, not a plan:
  write the prereg page, or say when it is due, by `measure_by`.
- `safety`: `reason`, a one-line string. A safety guard stays on its stated reason per §11; it is
  never asked to clear a fair-test bar, because it exists to stop the rare bad run that an
  averaged outcome score cannot see.

### Card rows that do not actually load every session

`loads` has no bucket for "opened on demand, one at a time," and a charter section is exactly
that: `docs/MASTER-OPERATIONS.md` loads one linked `docs/charter/*.md` section per need, not the
whole charter at session start. Those rows, and the two `AGENTS.md` twins, are still seeded as
`loads: "every session"` for lack of a closer bucket; read it as "this card's *ceiling* is every
session," not as a claim that it fires on every boot. A future `loads` value for on-demand parts
would make this precise instead of approximate.

### Hook and dispatch rows are `exec`, not sized from disk

A hook script and a dispatch artifact such as `scripts/dispatch` are executed, not read into a
model's context: their own file size is not a load, the way a program's source size is not the
cost of running it. `scripts/harness-inventory` prints `exec` for every `kind: "hook"` or
`kind: "dispatch"` row that carries no `measured_tokens`, and ranks those rows after every sized
row rather than by their script's byte count. A hook that does put real content into context, such
as a SessionStart hook's own stdout, is sized through `measured_tokens` instead (see below), which
still ranks numerically like any other sized row.

A row may also carry `measured_tokens` with `measured_on`, for a part a script cannot size from
disk. `scripts/harness-inventory` prints that number verbatim, marked `*`, instead of estimating
it. One such part is out of this ledger's scope entirely: the SessionStart tracker-priming stdout
an installed tracker hook writes into context is not a template script (it comes from the
install's own tracker wiring, the way the gstack and ponytail session banners are not template
parts either), so it carries no row here. An install that wants to track it adds its own row to
`evidence.instance.json` under a declared name, using the same `measured_tokens` / `measured_on`
fields.

## Status values and the disqualifier words

A fair test (§11) runs the real session prompt of the host, on the models the install dispatches
to, against a no-harness arm that cannot read the part under test, on tasks the plain model fails
sometimes but not always. A result that misses one of those conditions is a lead, not a verdict,
and is recorded with the reason it falls short:

| Word | What it means |
|---|---|
| `stub` | Ran against a synthetic or simplified harness, not the real session prompt |
| `small-tier` | Ran on a smaller model than the install actually dispatches to |
| `unmasked` | The no-harness arm could still see the part, or the two arms were not actually blind to which is which |
| `ceiling` | Both arms scored near the top of the scale; the test could not have detected an effect either way |
| `no-exposure` | The model never visibly used the part during the trial, so the comparison measured nothing |
| `variant-only` | Compared one version of the part against another, not against no part at all |
| `no-true-none-arm` | There was no arm that actually lacked the part |

## Preregistration template

A plan merges before any paid trial. One page per plan, with these headings and one line each:

- **Question** — what decision this trial will settle.
- **Arms (named and masked)** — what each arm sees, and how the no-harness arm is kept from
  reading the part under test.
- **Inputs (frozen)** — the task set, fixed before any arm runs.
- **Metrics and bars** — a number and a threshold, not a vibe.
- **Exposure gate** — the share of trials in which the part must visibly run before its effect
  counts at all.
- **Trials and budget** — how many runs, and what they cost.
- **Stop rule** — when the trial ends, win or lose.
- **Outcome rule** — what each result maps to: keep, fix-method, or cut-candidate.
- **Owner and measure-by date** — who runs it and by when.
