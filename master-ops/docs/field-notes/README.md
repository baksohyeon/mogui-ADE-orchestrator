---
status: active
---

# Field notes

A plain-language session digest written for the workspace owner rather than for operations.
The other three genres serve observation; this one serves learning and recall — what
happened, in the owner's terms, with the commands and concepts that mattered.

Optional genre. Adopt it when the owner wants a teaching or recall artifact; skip it
otherwise.

Shared attribution legend and integrity rules: `docs/observability/README.md`.

## Generation rule

No automatic hook. Either (1) the owner asks, or (2) the master *proposes* at a session seam
and waits for approval. Never produced unprompted — an unrequested digest is token spend the
owner did not authorize.

Output: `docs/field-notes/YYYY-MM-DD-<slug>.md`, normally one per session seam.

## Fixed sections

1. **What happened today** — the session as a narrative, explained as if to a smart
   ten-year-old. Analogies welcome; accuracy is not negotiable.
2. **Key exchanges** — two or three pivotal owner-prompt / master-response pairs, **quoted
   verbatim**. Not summarized. Verify against the session record where the workspace has a
   transcript index; if the record is gone, mark `[RECONSTRUCTED]`.
3. **Commands used** — only commands actually run. Command, one line on what it does, and
   when to reach for it. Do not invent instructive commands that were never run.
4. **Concept notes** — two to four concepts that appeared today, in plain language. Select
   by one criterion: it actually decided something today.
5. **Trap cards** — mines stepped on or narrowly avoided. Symptom, cause, avoidance, one
   line each.

## Integrity

- Plain-language treatment applies to sections 1 and 4 only. Quotes and commands keep
  verbatim accuracy.
- Sensitive material — credentials, tokens, keys — is excluded regardless of audience. For
  any audience beyond the owner, apply the workspace's publication rules as well.
- Do not omit failures to make the read pleasant. Failures are the best teaching material
  in the document.
