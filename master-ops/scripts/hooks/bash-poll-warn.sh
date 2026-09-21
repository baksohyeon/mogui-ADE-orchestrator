#!/bin/bash
# PreToolUse(Bash) hook: detect hand-rolled poll loops and warn
# Detects while+sleep, chained sleep patterns, and loop state checks.

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
log_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || return 0
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
    session_kind="master"
  fi
  printf '{"ts":%d,"hook":"bash-poll-warn","event":"PreToolUse(Bash)","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" "$VERDICT" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

INPUT=$(cat)
if ! CMD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null); then
  VERDICT="skip"
  exit 0
fi

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
  VERDICT="warn"
  echo "[bash-poll-warn] hand-rolled poll loop detected - event waits use scripts/orca-wait (charter section 4)"
fi

exit 0
