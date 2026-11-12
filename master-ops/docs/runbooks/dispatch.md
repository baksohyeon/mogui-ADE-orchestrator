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
runs `bd create "<title>" -t task -p 2`, and claims the returned id with
`bd update <id> --claim`. If `bd` or its tracker is unavailable, it prints a
warning, records `card_reason: tracker unavailable`, and puts `Tracker card:
none` in the prepared prompt. `--check-only` never creates or claims a card.

The prepared prompt includes `Tracker card: <id>` (or `none`) after the
contract and standing-rule material, so a worker can retain the association
through context compaction. The register milestone names the same card; the
ledger is the source of truth for later reconciliation.
