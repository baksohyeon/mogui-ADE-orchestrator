---
status: active
---

# Travelog

A per-generation journey log. Where the retro ledger holds judgment and misjudgment, the
travelog holds the itinerary — where the master went, what it actually ran, and what came
back. When a master says it "verified" something, this is where the reader learns what it
actually executed.

Shared attribution legend and integrity rules: `docs/observability/README.md`.

## Format

- File `gen-<N>.md`, append-only. Do not delete a generation's log when that generation
  ends; the point is that a later generation can read it.
- Entry shape: `## HH:MM <title>` followed by short prose. For verification work, record
  **the command run, what was observed, and the conclusion** — not just the conclusion.
- The tracker is the execution-state SSOT and Git is the code-fact SSOT. Identifiers and
  hashes appear here as pointers, not as duplicated state.
- Tag *why* claims per the shared legend. For substantive entries, add one line on what did
  not fire.

## What makes a log worth reading later

Dead ends, wrong guesses, and things that turned out differently than expected. A log that
records only successful steps is a changelog with extra words — the reader already has the
changelog.
