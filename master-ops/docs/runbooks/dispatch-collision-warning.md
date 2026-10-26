# Dispatch Collision Warning

`scripts/dispatch` calls `scripts/dispatch-collision-check` right after gate
allow and before the live three-line dispatch log. The helper compares the
contract's declared scope against open pull request files and unfinished ledger
dispatch scopes, then prints `WARNING:` lines for overlaps and exits `0`.
Set `MOGUI_PRODUCT_REPO` environment variable (defaults to `baksohyeon/mogui-ADE-orchestrator`) to specify the repository for PR lookups.

## What to do when warned

- Dispatch now and plan merge order when the work is urgent.
- Wait for the current owner when overlap is broad and conflict risk is high.
- Keep the warning lines in run notes so collision trends stay measurable.

## Limit

This check is fail-open and scope-declaration based. If a contract has no
usable scope paths, or a worker edits files outside declared scope, the helper
cannot warn for that hidden overlap.
