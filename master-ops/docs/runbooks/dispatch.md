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
unavailable, it prints a warning, records `card_reason: tracker unavailable`,
and puts `Tracker card: none` in the prepared prompt. If a later task, gate, or
delivery step fails after a claim, the wrapper returns the card to open status
and says whether that release succeeded. `--check-only` never creates or claims
a card.

The prepared prompt includes `Tracker card: <id>` (or `none`) after the
contract and standing-rule material, so a worker can retain the association
through context compaction. The register milestone names the same card; the
ledger is the source of truth for later reconciliation.
