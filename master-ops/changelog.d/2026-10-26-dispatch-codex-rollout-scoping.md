`master-ops/scripts/dispatch` scopes a codex worker's model probe to its own rollout instead of the
newest rollout across every account and date: a marker file timestamps this dispatch's own start,
and `select_scoped_codex_rollout` only considers rollouts no older than that marker, falling back to
`PROBE_STATE=unavailable` instead of guessing when none match. The codex rollout glob now resolves
its accounts directory through `codex_accounts_dir` (the `CODEX_ACCOUNTS_DIR` override, then an
OS-specific default) instead of a hardcoded macOS path, so it also reaches the rollout tree on Linux.

`scripts/model-probe-rollout` tolerates whitespace around the `"model"` field's colon and takes the
first `"model"` field on a line with `grep -o`'s left-to-right match order instead of a greedy regex
that landed on the last one; an unreadable rollout file now takes the same exit-1 path as a missing
one.

`master-ops/scripts/test-dispatch-runtime.sh` extracts the `jqf()` helper with the same brace-matching
`awk` already used for `tier_for_model()`, since `jqf()` is no longer a single physical line.
