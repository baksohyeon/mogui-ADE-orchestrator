---
status: active
---

# Retro ledger

Purpose: observability into master judgment. Git and the issue tracker hold *what was
done*; this ledger holds the layer they cannot — reasoning, misjudgment and self-correction,
near misses, and rationalizations resisted. Unlike an incident report, which is compelled
after a failure, this is a standing voluntary record.

Shared attribution legend and integrity rules: `docs/observability/README.md`.

## When to write

- Track milestones — right after a substantive judgment such as a dispatch, acceptance, or
  rejection
- After an incident or a near miss
- At succession or session close
- On request from the workspace owner

## Format

File name `YYYY-MM-DD-<slug>.md`. Fixed sections:

1. **Fact pointers** — execution records live in the tracker and in Git. One-line pointers
   only; do not restate them as narrative here.
2. **Judgment and rationale** — at each fork, why that branch. Include what was unknown at
   the time.
3. **Misjudgment and self-correction** — what was wrong, and whether the master caught it
   or the owner did. Keep those two distinct; they mean different things about the harness.
4. **Near misses** — actions not taken, and what stopped them. Often the most valuable
   section: it is the only record of a failure mode that left no trace.
5. **Conditional lessons** — no absolute rules. State the observed condition: "under X,
   Y is dangerous." Look for a counterexample in the same day's evidence before
   generalizing.
6. **Attribution** — when the owner's instruction or insight was the trigger, name it.

## Discipline

- Tag `[FORCED]` / `[SHAPED]` / `[JUDGED]` / `[RECONSTRUCTED]` on judgment claims; a
  `[JUDGED]` line carries its unchosen alternative.
- No minimizing, no burying. Unflattering facts are the reason this ledger exists.
- A list of things that went well has no observation value. Sections 3, 4, and 5 carry the
  weight.
