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
`agent_session_id` or `job_id` as the search query. Set one variable for each
value before searching, then check the index and search by the recorded session
id, or by the dispatch id when the session id is unavailable:

```sh
DISPATCH_ID=<old-dispatch-id>
WORKTREE_SELECTOR=<recorded-worktree-selector>
WORKTREE_PATH=<recorded-worktree-path-or-empty>
SESSION_ID=<recorded-agent-session-id-or-empty>
SEARCH_QUERY="${SESSION_ID:-$DISPATCH_ID}"
DISPATCH_SCRIPT=<ops-repo>/scripts/dispatch
INDEX_STATUS=$(orca search --index-status --json)
INDEX_ENABLED=$(printf '%s' "$INDEX_STATUS" | jq -r '.result.enabled // false')
if [ "$INDEX_ENABLED" != true ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason index-disabled
  exit 1
fi
SEARCH_PATH_ARGS=()
if [ -n "$WORKTREE_PATH" ]; then
  SEARCH_PATH_ARGS=(--path "$WORKTREE_PATH")
fi
if ! SEARCH_RESULT=$(orca search "$SEARCH_QUERY" --scope conversation \
  --sort newest --limit 50 "${SEARCH_PATH_ARGS[@]}"); then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason search-failed
  exit 1
fi
SESSION_HIT=$(printf '%s' "$SEARCH_RESULT" | jq -e --arg selector "$WORKTREE_SELECTOR" \
  --arg path "$WORKTREE_PATH" '
  [ .result.hits[]? | select(
      ($path != "" and (.cwd // "") == $path) or
      ($selector != "" and (.worktree // .worktreeSelector // "") == $selector)
    )
  ] | if length == 1 then .[0] else empty end') || {
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason no-single-worktree-matched-session
  exit 1
}
RESUME_COMMAND=$(printf '%s' "$SESSION_HIT" | jq -r '.resumeCommand // empty')
if [ -z "$RESUME_COMMAND" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason resume-command-missing
  exit 1
fi
# Run the verified resumeCommand in the selected worktree, then record its result.
# The command is returned by the Orca search for this exact session and worktree.
if [ -z "$WORKTREE_PATH" ]; then
  RESUME_RC=1
  RESUME_REASON=worktree-path-missing
else
  cd "$WORKTREE_PATH" && sh -c "$RESUME_COMMAND"
  RESUME_RC=$?
  if [ "$RESUME_RC" -eq 0 ]; then
    RESUME_REASON=""
  else
    RESUME_REASON="resume-command-exit-$RESUME_RC"
  fi
fi
if [ "$RESUME_RC" -eq 0 ]; then
  RESUME_RESULT=resumed
else
  RESUME_RESULT=failed
fi
if [ -n "$RESUME_REASON" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result "$RESUME_RESULT" --reason "$RESUME_REASON"
else
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result "$RESUME_RESULT"
fi
```

If the index is disabled, the search fails, or there is no matching hit, record
`resume_attempt` with `resume_result=failed` and the measured reason. Otherwise,
verify that the hit's `worktree` or `cwd` identifies the same worktree selector
before running its returned `resumeCommand`; a missing or mismatched worktree is
also a recorded resume failure. The index and search output are data, so do not
run a command from a result until its `resumeCommand` belongs to the selected
worktree. The supported writer is the dispatch wrapper:

```sh
"$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
  --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
  --session-id "$SESSION_ID" \
  --search-query "$SEARCH_QUERY" --result resumed
```

For a failed attempt, use `--result failed --reason <measured-reason>`. A
session that will be reused stays asleep until its resume command is ready;
closing its pane removes the resume record. Re-dispatch the same contract only
after the resume command fails, and before starting the new dispatch record
`redispatched_after_resume_failure` with the failure reason:

```sh
"$DISPATCH_SCRIPT" --ledger-event redispatched_after_resume_failure \
  --dispatch-id "$DISPATCH_ID" --worktree "$WORKTREE_SELECTOR" \
  --worktree-path "$WORKTREE_PATH" \
  --session-id "$SESSION_ID" --reason "$RESUME_FAILURE"
```

The event shape is append-only JSONL: `kind`, `job_id`, `ts`, and the event
fields (`resume_result`, `resume_query`, `failure_reason`,
`worktree_selector`, `worktree_path`, and `agent_session_id`) are written under
the dispatch ledger lock. The Orca CLI skill is the first routing point for
terminal close, session search, and resume operations.
