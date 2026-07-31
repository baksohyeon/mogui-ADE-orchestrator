---
status: active
---

# Agent journey — index

Turn-level harness dissection. Different genre from the generation travelog and the retro
ledger: this one attributes each behaviour down to the harness component that produced it,
so the reader learns *which layer to fix*.

**On demand only.** No automatic trigger. This capture is token-intensive; produce it at a
natural seam — an acceptance verdict, a session close, a flow worth explaining — not every
turn.

Shared attribution legend and integrity rules: `docs/observability/README.md`. This index
is the SSOT for the per-document matrix below; individual captures use the tags without
restating the legend.

## Output layout

- `docs/agent-journey/YYYY-MM-DD-<slug>/JOURNEY.md`; follow-ups in the same folder as
  `JOURNEY-N-<focus-slug>.md`. Folder date is fixed at first capture.
- Sub-agent transcripts are not committed.
- Folder selection uses observable signals only: (1) an active planning workstream
  directory that exists on disk, (2) an explicit instruction from the workspace owner.
  Otherwise a new folder. "It feels like the same thread" is not a signal, and neither is
  the Git branch — short-lived branches do not map one-to-one onto work threads.

## Fixed sections

`0` and `7` are optional; the rest are required. Section 5 is always present, "none" if
nothing happened.

| Section | Contents |
|---|---|
| 0. Why capture this | Optional, one or two lines |
| 1. Procedure | What the harness **forced**. Table: signal source / type / component class / what was injected or compelled / what the master actually did |
| 2. Reasoning | Interpretation and decisions, with attribution tags; `[JUDGED]` lines carry the unchosen alternative |
| 3. Execution | Tool calls in order, parallel or serial marked |
| 4. Output | What shaped the output's form — hooks, rules, tracker memory |
| 5. Owner intervention points (required) | Interrupts, redirections, corrections in time order, and how each changed the path |
| 6. What did not fire (required) | Skills, sub-agents, gates left off, and why. Evidence that restraint worked |
| 7. Weight class | Optional, one line. The comparison matrix lives in this index |
| 8. Lessons | Where it landed, and what was learned about the system |

Before writing, collect evidence: session-start and per-prompt hook output that actually
fired, the real tool-call sequence, tracker state for the track, and Git state if relevant.
Then check the freshness gate — if the record is gone, say so and downgrade the claims.

Cross-link, do not co-locate: if an incident occurred in the same work, link the incident
report; if a judgment record exists, link the retro entry.

## Capture matrix

| Date | Document | Weight class | One line |
|---|---|---|---|
