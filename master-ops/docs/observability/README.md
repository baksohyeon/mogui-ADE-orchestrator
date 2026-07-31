---
status: active
---

# Observability Suite (index and shared legend)

Git history and the issue tracker record *what happened*. They cannot record what shaped
the master's behaviour, what it almost did, or what it decided not to do. Without that
layer, the only observation channel a workspace owner has is a post-incident report — which
arrives only after something already broke.

This suite adds three voluntary, standing record genres plus one optional deep-capture
genre. Each one captures a different layer; none replaces another, and none replaces the
incident report.

| Genre | Directory | Captures | Cadence |
|---|---|---|---|
| Retro | `docs/retro/` | Judgment, misjudgment, near misses, temptations resisted | Track milestones, incidents, succession, on request |
| Travelog | `docs/travelog/` | Where the master went, what it actually ran, what came back | Append per generation, as events happen |
| Field notes | `docs/field-notes/` | Plain-language digest for the workspace owner: narrative, quoted exchanges, commands used, concepts, traps | On explicit request, or on master proposal + approval |
| Agent journey | `docs/agent-journey/` | Turn-level harness dissection with component attribution | On demand only |

Adopt the genres a workspace actually needs. Retro and travelog are the load-bearing pair;
field notes and agent journey are optional and cost real tokens to produce.

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
