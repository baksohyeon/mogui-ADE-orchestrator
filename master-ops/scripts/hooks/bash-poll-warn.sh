#!/bin/bash
# PreToolUse(Bash) hook: detect hand-rolled poll loops and warn
# Detects while+sleep, chained sleep patterns, and loop state checks.

log_fire() {
  local fire_log="${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}"
  mkdir -p "$(dirname "$fire_log")" 2>/dev/null || return 0
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
    session_kind="master"
  fi
  python3 - "bash-poll-warn" "PreToolUse(Bash)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" <<'PY' >> "$fire_log" 2>/dev/null || true
import json
import sys
import time

_, hook, event, cwd, runtime_hint, session_kind = sys.argv
print(json.dumps({
    "ts": int(time.time()),
    "hook": hook,
    "event": event,
    "cwd": cwd,
    "runtime_hint": runtime_hint,
    "session_kind": session_kind,
}, separators=(",", ":")))
PY
}

log_fire

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

# Detect hand-rolled poll patterns:
# 1. while true combined with sleep
# 2. sleep chained with state-check commands (orca check, git rev-parse, gh pr view, curl)

POLL_DETECTED=0

# Pattern 1: while true with sleep
if [[ "$CMD" =~ while[[:space:]]+true ]] && [[ "$CMD" =~ sleep ]]; then
  POLL_DETECTED=1
fi

# Pattern 2a: sleep chained with state check via &&, ;, or pipe
if [[ "$CMD" =~ sleep[[:space:]]+[0-9] ]] && \
   [[ "$CMD" =~ (&&|;|[|])[[:space:]]*(orca[[:space:]]+orchestration[[:space:]]+check|git[[:space:]]+rev-parse|gh[[:space:]]+pr[[:space:]]+view|curl) ]]; then
  POLL_DETECTED=1
fi

# Pattern 2b: while loop with sleep and curl/check
if [[ "$CMD" =~ while ]]; then
  if [[ "$CMD" =~ sleep ]] && [[ "$CMD" =~ (curl|orca[[:space:]]+orchestration[[:space:]]+check|git[[:space:]]+rev-parse|gh[[:space:]]+pr) ]]; then
    POLL_DETECTED=1
  fi
fi

if [[ $POLL_DETECTED -eq 1 ]]; then
  echo "[bash-poll-warn] hand-rolled poll loop detected - event waits use scripts/orca-wait (charter section 4)"
fi

exit 0
