# orca-wait runbook

## What it does

**`scripts/orca-wait`** - event-driven wait wrapper that encapsulates the correct orca orchestration check protocol. Drains the unread backlog via deliveryId ack-chaining, then blocks on orchestration check until a message arrives or timeout expires.

**`scripts/hooks/bash-poll-warn.sh`** - PreToolUse(Bash) warn hook that detects hand-rolled poll loops (while+sleep, chained sleep patterns) and reminds to use `orca-wait` instead.

## Why this matters

Agents reflexively reach for `while true; do sleep; done` loops instead of orca's event-driven `check --wait` protocol. This creates tight polling, burns tokens on redundant state checks, and misses the orca semantics that make agent coordination reliable. The wrapper removes friction (long command flags); the hook provides measured feedback at the moment of temptation.

## orca-wait protocol (charter section 4)

The correct orca wait flow:
1. **Drain unread backlog** - Loop with `--wait 100ms --timeout-ms 100` (return-immediately) and ack each batch via deliveryId. This clears old messages so the subsequent wait genuinely blocks on new messages.
2. **Block on deliveryId ack-chain** - `orca orchestration check --ack <deliveryId> --unread --wait --timeout-ms <N> --json`, chaining the previous batch's deliveryId so orca never replays the same message twice.
3. **Parse and filter** - Print one line per non-heartbeat message: `type|id|from|subject`.
4. **Honest failure** - If orca is missing or errors, print one clear error to stderr and exit nonzero.

## orca-wait usage

```bash
# Wait once and return after first batch
./scripts/orca-wait --once

# Keep waiting and print every non-heartbeat batch
./scripts/orca-wait

# Custom timeout (milliseconds)
./scripts/orca-wait --once --timeout-ms 10000

# Filter by message types
./scripts/orca-wait --once --timeout-ms 10000 --types worker_done,escalation
```

Output:
```
worker_done|msg_def456|term_xyz|complete
```

## bash-poll-warn hook

Detects these patterns and emits one-line warning:
- `while true` combined with `sleep`
- `sleep <n>` chained (`;`, `&&`, `||`, `|`) with state-check commands (orca check, git, gh, curl)
- `while` loop containing both sleep and a state check

Exit code always 0 (fail-open); warning goes to stdout.

## Host Settings JSON for wiring bash-poll-warn

Wire the hook in the host settings file used by the active runtime. For Claude,
the settings file is usually `.claude/settings.json` in the project or
`~/.claude/settings.json` globally:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "$CLAUDE_PROJECT_DIR/scripts/hooks/bash-poll-warn.sh",
        "description": "Warn when bash commands contain hand-rolled poll loops"
      }
    ]
  }
}
```

**Important:** Settings hooks are inert until session restart. Changing settings does not take effect mid-conversation; restart the host session for the hook to fire.

## Measurement value

Each bash-poll-warn firing is logged to the configured hook fire-log path, defaulting to `$HOME/.mogui/hook-fire-log.jsonl`, with session kind (master/worker/unknown) and CWD. This provides evidence for the enforcement-vs-discipline question: Are agents adopting orca-wait, or still reaching for hand-rolled loops under pressure?

Fire log fields:
- `ts`: Unix timestamp
- `hook`: "bash-poll-warn"
- `event`: "PreToolUse(Bash)"
- `cwd`: Working directory
- `runtime_hint`: Optional hint from `$MOGUI_RUNTIME_HINT`
- `session_kind`: "master", "worker", or "unknown"

## Related docs

- `docs/orca-docs-grounding.md` - Orca foundational knowledge charter and documentation sources
- `docs/MASTER-OPERATIONS.md` - Workspace orchestration model
- `docs/runbooks/contract-conventions.md` - Charter conventions including section 4 waits reference
