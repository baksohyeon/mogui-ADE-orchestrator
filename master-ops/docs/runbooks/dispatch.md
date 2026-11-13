# Supervised dispatch wrapper

`scripts/dispatch` runs the checked and registered worker path. Every live
dispatch carries a tracker card id in its register row when the tracker is
available; an explicit reason records a deliberate or measured gap.

The card flags are:

```text
--card <id>             use an existing tracker card and claim no new card
--no-card <reason>      dispatch with no card, recording why
```

When neither flag is supplied, the wrapper reads the contract's H1 title,
runs `bd create "<title>" -t task -p 2 --json`, parses its JSON `id`, and
claims that id with `bd update <id> --claim`. If the claim fails, the created id
is retained with `card_reason: claim failed`; if `bd` or its tracker is
unavailable, it prints a warning and records `card_reason: tracker unavailable`.
If card creation fails, it records `card_reason: tracker create failed`; if the
command succeeds without returning a usable id, it records
`card_reason: tracker create returned no id`. In either case it puts
`Tracker card: none` in the prepared prompt. If a later task, gate, or delivery
step fails after a claim, the wrapper returns the card to open status and says
whether that release succeeded. `--check-only` never creates or claims a card.

The prepared prompt includes `Tracker card: <id>` (or `none`) after the
contract and standing-rule material, so a worker can retain the association
through context compaction. The register milestone names the same card; the
ledger is the source of truth for later reconciliation.

## Resume before re-dispatch

When a worker exits abnormally, inspect the dispatch ledger row for its
`worktree_selector` and `agent_session_id`. Find the recorded session with
`orca search`, or search by agent when the session id is unavailable, and run
the returned `resumeCommand` in the same worktree. A session that will be
reused stays asleep until its resume command is ready; closing its pane removes
the resume record.

Record the resume attempt and its result in the dispatch ledger. Re-dispatch
the same contract only after the resume command fails, and record
`redispatched_after_resume_failure` with the failure reason before starting the
new dispatch. The Orca CLI skill is the first routing point for terminal close,
session search, and resume operations.
