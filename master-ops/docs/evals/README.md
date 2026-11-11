# Evaluation evidence and preregistration

This directory is where charter [§11 Earn Its Place](../charter/11-earn-its-place.md) keeps its
ledger and its preregistration shape. It follows the pattern of
[gstack ETHOS §9 "Earn Its Place"](https://github.com/garrytan/gstack-evals), applied to this
template: every harness part either ships with evidence that it helps, or with a stated reason,
an owner, and a measure-by date. This template ships no runner. A plan here is a document; the
trials are run by whoever owns the plan, with whatever harness they have.

## `evidence.json`

One JSON object: `{"measured_at": "<date>", "parts": [...]}`. `measured_at` is the date the ledger
itself was last reviewed as a whole, not the date of any one part's trial.

Each entry in `parts` is one harness part:

| Field | Meaning |
|---|---|
| `key` | The part's path relative to the template root, or a declared name for a hook's stdout (a hook's own script is sized from disk by its path; its stdout at a given event is not a file, so it gets a name instead, carried with `measured_tokens`) |
| `kind` | `card`, `skill`, `hook`, `memory`, `dispatch`, or `shared` |
| `loads` | `every session`, `every prompt`, `every use`, or `every dispatch` |
| `status` | `helps`, `no-effect`, `hurts`, `untested`, or `safety` |

What else a row carries depends on `status`:

- `helps` / `no-effect` / `hurts`: `sources` (a list of strings naming the trial or trials) and,
  optionally, `caveats`.
- `untested`: `plan`, a string. `"none (grandfathered)"` means the part predates this ledger and
  has not yet been queued for a trial. Any other plan string also needs `owner` and `measure_by`
  (`YYYY-MM-DD`).
- `safety`: `reason`, a one-line string. A safety guard stays on its stated reason per §11; it is
  never asked to clear a fair-test bar, because it exists to stop the rare bad run that an
  averaged outcome score cannot see.

A row may also carry `measured_tokens` with `measured_on`, for a part a script cannot size from
disk. `scripts/harness-inventory` prints that number verbatim, marked `*`, instead of estimating
it. One such part is out of this ledger's scope entirely: the SessionStart tracker-priming stdout
an installed tracker hook writes into context is not a template script (it comes from the
install's own tracker wiring, the way the gstack and ponytail session banners are not template
parts either), so it carries no row here. An install that wants to track it adds its own row under
a declared name, using the same `measured_tokens` / `measured_on` fields.

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
