---
status: active
---

# Observability Suite (index and shared legend)

Git history and the issue tracker record *what happened*. They cannot record what shaped
the master's behaviour, what it almost did, or what it decided not to do. Without that
layer, the only observation channel a workspace owner has is a post-incident report — which
arrives only after something already broke.

This suite adds three standing record genres. They capture different layers,
neither replaces the others, and each answers a different observability question.

| Genre | Directory | Captures | Cadence |
|---|---|---|---|
| Blame | `docs/blame/` | Structured incident observation record: what was observed, what was not observed, and where observation was promoted to cause too early | Only when an incident trigger is met |
| Retro | `docs/retro/` | Judgment, misjudgment, near misses, temptations resisted | Track milestones, incidents, succession, on request |
| Travelog | `docs/travelog/` | Where the master went, what it actually ran, what came back | Append per generation, as events happen |

Blame has a narrow job that neither retro nor travelog can do: it recovers the
evidence layer a raw session can blur during self-report, including what was not
checked and where a causal claim outran observation. Its strict format is there for
measurement quality, not for punishment. Use the filename format
`BLAME-YYYY-MM-DD-<slug>.md`.

**PROPOSED (owner decision pending)**

Proposed incident triggers grounded in 2026-08-03 measurements:
- A claim is stated stronger than its evidence supports and then propagated into a worker tool or contract.
- A completed-tense progress report is made without a matching execution event (the action did not run).
- A reading surface is treated as the thing itself (wrong mailbox, wrong field, piped exit code) and used as ground truth.

Rejected candidates (not adopted as triggers):
- Product repository `main` reach outside dispatch path: rejected because the 2026-08-03 evidence set for this track did not confirm a direct main-path breach event.
- "Wrote a guard and broke it the same day" as standalone trigger: rejected because it is too broad and mostly a duplicate symptom of the stronger evidence-quality triggers above.

Retro is the one that earns its cost. It answers why a decision took the shape it
did, which nothing else records. Travelog answers what happened, and a workspace
that keeps a verbatim session transcript will find it redundant.

The workspace that authors this template also ran two further genres, a
plain-language digest and a turn-level harness dissection. Both are dropped
here. They were useful while working out what the suite should be and neither
justified its token cost afterwards. Add your own if a question keeps going
unanswered by these two; do not start from a genre and look for a use.

## Attribution tags (shared legend — this file is the SSOT)

Any claim about *why* the master did something carries a tag. Confidence descends down the
table.

| Tag | Meaning | Confidence |
|---|---|---|
| `[FORCED]` | A hook or system rule compelled it; no choice existed | High (record-backed) |
| `[SHAPED]` | Injected context (operations doc, tracker memory, hook output) shaped it; it would have gone differently without that context | High (record-backed) |
| `[JUDGED]` | The master's own judgment — must be accompanied by *what was chosen / what was not chosen / why* | Medium (confabulation risk) |
| `[RECONSTRUCTED]` | The behavioural record is gone (compaction, succession, clear); inferred backwards from artifacts | Lowest |

Component classes for attribution: `system-prompt`, `tool-desc`, `tool-impl`,
`middleware`, `skill`, `sub-agent`, `memory`.

## Integrity rules (apply to every genre)

- **Record the instruction not to record.** When someone asks for something to
  be left out, the request goes in the record: what was asked, when, and by
  whom. Naming what was withheld is what makes the gap visible.
  One exception, and it is narrow. When the request carries a credential, token,
  or key, record it as metadata only — the class of secret, where it came from,
  the time, the requester, and a marker at the gap. Never the value, and never
  a verbatim quote of a request that contains one. Recording the instruction
  must not become the way a secret enters the record.
  A verbatim transcript layer enforces the rest structurally, because a parser
  cannot be persuaded; an interpretive genre cannot, which is why this is
  written down.
- **`[JUDGED]` must be falsifiable.** State the alternative that was not chosen. A smooth
  after-the-fact narrative with no alternative exposed is indistinguishable from a
  rationalization.
- **Freshness honesty.** Use `[FORCED]`/`[SHAPED]` only while the behavioural record is
  still in context. After compaction or succession, downgrade affected claims to
  `[RECONSTRUCTED]` and say so in the preamble. Never present a reconstruction as a record.
- **Cross-check against primary artifacts.** Back record-based claims with verbatim hook
  output, tool output, commit stats, or tracker comments. When narrative and artifact
  disagree, the artifact wins.
- **List what did not fire.** Skills, sub-agents, gates, and workflows that stayed off —
  and why — are the only evidence that restraint worked as designed. Omitting them turns
  every record into an over-claim.
- **No credit erasure.** When the trigger for progress was the workspace owner's
  instruction or insight, say so explicitly. Do not drop the subject and present it as the
  master's own realization.
- **Measured, not imagined.** Quotes, commands, and numbers are real records or they are
  not included.

## What this suite cannot do

These are behavioural traces — well-structured application logs, not introspection. They
record which hooks fired, which tools ran in what order, and where the owner intervened.
They cannot record what actually happened inside the model or what its "real motive" was.
No document genre can. Blurring that line is the failure mode this legend exists to
prevent.
