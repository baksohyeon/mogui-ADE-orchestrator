# refactor: route remaining Orca JSON callers through the shared reader

## Summary

The spawn-test and dispatch-smoke harnesses now read both supported Orca JSON
shapes through `scripts/lib/orca_json.py`, and worker-wait has an end-to-end
regression fixture for a target dispatch on the second worker-list page.

## Changes

- `scripts/spawn-test` uses `run_id()` for coordinator Run detection and tests
  both response shapes.
- `scripts/dispatch-smoke` uses `dispatch_status()` for both dispatch-show
  reads and tests both response shapes.
- `scripts/test-worker-wait.sh` covers old and new two-page worker-list
  responses and proves a page-one-only mutant drops the page-two dispatch.

## References

- Issue: #218
