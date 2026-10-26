---
status: active
---

# Postmortem ledger

Purpose: observability into how a technical incident was diagnosed, written so that a
junior engineer can follow the reasoning. Git and the issue tracker hold *what was done*;
this ledger holds the layer they cannot: what was observed, which hypotheses were held,
how each was tested, why the fix was chosen, and what stayed unverified. It also carries
the judgment layer the earlier retro ledger held, since reasoning and misjudgment are the
same record read twice.

This directory replaced the former retro directory on 2026-09-14 by owner decision. The generator is
`skills/postmortem`, invoked as `/postmortem`, and the directory carries the same name so a
reader who runs the skill finds where its output lands.

Agent fault is not softened here. When the incident includes an agent's own judgment error,
this record names it in the body per skill §3, and the structured self-observation goes to
`docs/blame/` through `blame-agent` per skill §11. The two genres are not interchangeable.

Shared attribution legend and integrity rules: `docs/observability/README.md`.

## When to write

- After a debugging incident, once the evidence is in hand
- After an incident or a near miss involving the master's own judgment
- At succession or session close
- On request from the workspace owner

## Format

File name `YYYY-MM-DD-<slug>.md`, no serial number. Body follows `skills/postmortem/SKILL.md`
sections 2 to 5 for technical incidents and section 6 for coordination incidents. Every
record carries, in some form:

1. **Fact pointers**: execution records live in the tracker and in Git. One-line pointers
   only; do not restate them as narrative here.
2. **Hypotheses and how each was tested**: state, cost, result, and what was left
   unverified. Sequence as it happened; a better order discovered afterwards is a lesson,
   not a rewrite.
3. **Judgment and misjudgment**: at each fork, why that branch, and what was unknown then.
   Whether the master caught its own error or the owner did stays distinct; they mean
   different things about the harness.
4. **Near misses**: actions not taken, and what stopped them. Often the only record of a
   failure mode that left no trace.
5. **Conditional lessons**: no absolute rules. State the observed condition. Look for a
   counterexample in the same day's evidence before generalizing.
6. **Attribution**: when the owner's instruction or insight was the trigger, name it.

## Discipline

- Tag `[FORCED]` / `[SHAPED]` / `[JUDGED]` / `[RECONSTRUCTED]` on judgment claims; a
  `[JUDGED]` line carries its unchosen alternative.
- A verification claim carries its evidence. Output that was absent is recorded as absent,
  and an exit code that was not captured is not written down.
- No minimizing, no burying. Unflattering facts are the reason this ledger exists.
- A list of things that went well has no observation value. Sections 2 to 5 carry the
  weight.
