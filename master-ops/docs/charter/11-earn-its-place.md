# §11. Earn Its Place

Governs how a card section, skill, hook, memory file, or dispatch artifact justifies its ongoing cost. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Every card section, skill, hook, memory file, and dispatch artifact costs tokens and attention on every run
that loads it. Each one earns its place: it ships with evidence that it helps, or with a stated reason, an
owner, and a date by which a fair test will measure it. Safety guards are the exception: they stay on their
stated reason, because they stop the rare bad run that an average score cannot see.

A fair test runs the real session prompt of the host (not a stub), on the models the install dispatches to,
against a no-harness arm that cannot read the part under test, on tasks the plain model fails sometimes but not
always. A result that misses one of these is a lead, not a verdict, and is listed with its reason: `stub`,
`small-tier`, `unmasked`, `ceiling`, `no-exposure`, `variant-only`, `no-true-none-arm`.

A test records exposure (did the model actually use the part) before it records effect. A null result gets one
"why null" pass: used? task fit? enough power and room below the ceiling? does today's model do it without the
part? Then keep, fix the method, or cut, and say which in `docs/evals/evidence.json`.

Measure the biggest parts first: `scripts/harness-inventory` ranks every part by load per run.
Preregister before spending: `docs/evals/README.md` holds the plan shape. A plan merges before any paid trial.
