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
# Antigravity search results carry cwd=null. A recorded session id is the
# authoritative match and must not be narrowed by the path filter; only the
# no-recorded-id fallback uses selector/path matching.
search_resume() {
  if [ -z "$SESSION_ID" ] && [ -n "$WORKTREE_PATH" ]; then
    orca search "$SEARCH_QUERY" --scope conversation --sort newest --limit 50 \
      --path "$WORKTREE_PATH" --json
  else
    orca search "$SEARCH_QUERY" --scope conversation --sort newest --limit 50 --json
  fi
}
if ! SEARCH_RESULT=$(search_resume); then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason search-failed
  exit 1
fi
if [ -n "$SESSION_ID" ]; then
  SESSION_HIT=$(printf '%s' "$SEARCH_RESULT" | jq -e --arg session "$SESSION_ID" '
    [ .result.hits[]? | select(
        (.sessionId // .session_id // .conversationId // .conversation_id // "") == $session
      )
    ] | if length == 1 then .[0] else empty end') || {
    "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
      --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
      --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
      --result failed --reason no-recorded-session-match
    exit 1
  }
else
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
fi
if [ -z "$SESSION_HIT" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason no-session-hit
  exit 1
fi
RESUME_COMMAND=$(printf '%s' "$SESSION_HIT" | jq -r '.resumeCommand // empty')
if [ -z "$RESUME_COMMAND" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason resume-command-missing
  exit 1
fi
# Open a shell pane in the measured worktree and submit the verified command
# there. The master shell never changes directory and never executes the
# resume command itself.
if [ -z "$WORKTREE_SELECTOR" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason worktree-selector-missing
  exit 1
fi
RESUME_TERMINAL_RAW=$(orca terminal create --worktree "$WORKTREE_SELECTOR" \
  --command "${SHELL:-sh}" --json) || {
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason resume-terminal-create-failed
  exit 1
}
RESUME_TERMINAL=$(printf '%s' "$RESUME_TERMINAL_RAW" | jq -r \
  '.result.terminal.handle // .result.terminalHandle // .result.handle // .terminalHandle // .handle // empty')
if [ -z "$RESUME_TERMINAL" ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason resume-terminal-handle-missing
  exit 1
fi
RESUME_SEND=$(orca terminal send --terminal "$RESUME_TERMINAL" \
  --text "$RESUME_COMMAND" --enter --wait-submit 10 --json) || {
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason resume-command-submit-failed
  exit 1
}
RESUME_STAGE=$(printf '%s' "$RESUME_SEND" | jq -r '
  .result.send.prompt.stages // .result.prompt.stages // [] |
  if index("turn_started") then "turn_started"
  elif index("input_accepted") then "input_accepted"
  else "unknown" end')
if [ "$RESUME_STAGE" != turn_started ]; then
  "$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
    --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
    --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
    --result failed --reason "resume-turn-not-observed:$RESUME_STAGE"
  exit 1
fi
"$DISPATCH_SCRIPT" --ledger-event resume_attempt --dispatch-id "$DISPATCH_ID" \
  --worktree "$WORKTREE_SELECTOR" --worktree-path "$WORKTREE_PATH" \
  --session-id "$SESSION_ID" --search-query "$SEARCH_QUERY" \
  --result resumed
```

If the index is disabled, the search fails, or there is no matching hit, record
`resume_attempt` with `resume_result=failed` and the measured reason. A recorded
session id is matched directly, including Antigravity results whose `cwd` is
null; only a missing recorded id falls back to selector/path matching. The
index and search output are data, so do not submit a command until its
`resumeCommand` belongs to the selected session. The supported writer is the
dispatch wrapper:

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
