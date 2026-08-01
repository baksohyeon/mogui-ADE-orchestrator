# Verbatim Transcript Ledger Spec

Date: 2026-08-01

## Scope

This document specifies a first-class record layer that this repository does not
ship yet: a verbatim ledger of what the human and the master actually said,
split by workstream, with causal labels placed at the decision points.

The template set under `master-ops/docs/` currently exports four interpretive
genres (`retro`, `travelog`, `field-notes`, `agent-journey`). All four select and
compress. Nothing exports the primary record they are interpretations of.

The reference implementation exists outside this repository and has produced 24
workstream files across two master generations. This spec covers what changes
when it is generalized and brought in.

## Why A Primary Layer

Interpretation layers read thin over time because the writer chose what mattered
before knowing what would matter. A verbatim ledger fixes the ordering: record
first, interpret later, and when the two disagree the record wins.

The ledger is also the only artifact that can answer "did that actually happen,
or did a later summary invent it." Two extraction bugs in the reference
implementation were found precisely because a known utterance could be named and
then searched for.

## Layer Position

| Layer | Directory | Character |
| --- | --- | --- |
| Primary | `master-ops/docs/transcripts/` | Utterances as spoken. No selection. |
| Interpretive | `retro`, `travelog` | What happened, why it was judged that way |
| Interpretive | `field-notes`, `agent-journey` | Learning and path narrative |

## Edit Budget

The ledger is verbatim with exactly two mechanical edits, and both leave a
visible mark where they acted.

1. Injected blocks are removed. Hook output, system reminders, skill bodies,
   attachments, tool results, and subagent returns are not something a person
   said.
2. Tool calls are collapsed to a labeled line carrying the command. The session
   record remains the source of truth for full output.

Utterance text is never altered. Typos stay.

## Causal Labels

Labels mark why a decision took the shape it did. Three are load-bearing:

- `FORCED`: a constraint the master did not choose
- `SHAPED`: an influence that narrowed the options
- `JUDGED`: the master's own call

These match the tag names in `master-ops/docs/observability/README.md`, which is
the shared legend for the observation genres.

Labels are placed inline, adjacent to the utterance they describe, not collected
in a header summary. A header summary answers "what happened in this workstream"
and that is an interpretive question the second layer already owns.

Inline placement must not become editing. The renderer inserts labels as marked
annotation lines beside the utterance and never modifies the utterance itself.
A `--raw` mode emits the ledger with annotations omitted, and the test suite
asserts that `--raw` output is byte-identical to the unannotated render. That
makes "verbatim" a measured property rather than a claim.

Labels are authored by the master after the ledger is built, in a separate
annotation file keyed by utterance index. Generation is not attempted. The label
answers why a judgment was made, and a machine guessing at that produces
plausible wrong answers that then look like evidence. The tool instead counts
decision points that carry no label and reports the count, because the observed
failure mode is not bad labels but absent ones.

## Result Truncation

Tool results collapse to one line by default. They are not truncated when the
call exited nonzero or otherwise failed. Results matter most where they
contradicted the expectation, and those are the ones a one-line collapse loses.

## Host Support

Measured on Claude Code records. Nothing else has been measured.

The parser reads a host's session record directly and that record is
host-shaped. Another host is likely to work once its record shape is checked
and the extraction is pointed at it. Until someone does that, Claude Code is
what the support claim covers.

The parser reads a host's session record directly and that record is
host-shaped. The reference implementation distinguishes human utterances by a
`promptSource` field and recovers mid-turn messages from an enqueue record,
neither of which is portable. Rather than build a host abstraction before a
second host is actually needed, the supported set is declared and the parser
stays direct.

This matches how the repository already declares its platform support: macOS
only, other platforms planned.

## Injected-Prefix Configuration

The reference implementation hardcodes the prefixes of its own workspace's hook
output. Those are specific to one installation. In this repository the list is a
configuration file and the shipped default is empty.

A prefix list is a string filter and string filters were the wrong tool once
already: skill bodies and agent returns kept passing as human speech until the
split moved to a structural field. The prefix list stays as a secondary filter
behind the structural one, never as the primary.

## Operator Language

Ledger content follows the source. A Korean conversation produces a Korean
ledger, because the ledger quotes it.

Tool output, help text, warnings, and errors are English here, matching the rest
of the repository. Downstream installations may localize their own copy.

## Verification

- `--raw` output is byte-identical to the render with annotations omitted
- an utterance that falls into no workstream fails the build, preserving the
  existing guarantee that partitioning cannot silently drop speech
- with an empty prefix list, injected blocks are still not classified as human
  speech, proving the structural split leads
- unlabeled decision points are counted and reported
- regenerating an existing ledger produces unchanged output
