#!/bin/bash
# UserPromptSubmit/SessionStart: inject role state + execution rule.
# Exists to counter host-injected autonomy defaults (MASTER-OPERATIONS §7/§8, owner-approved 2026-08-03).

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
json_str() {
  local value="${1-}"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=$(printf '%s' "$value" | tr -d '\000-\037\177')
  printf '%s' "$value"
}
derive_session_kind() {
  if [ -n "${ORCA_TASK_ID:-}" ] || [ -n "${ORCA_DISPATCH_ID:-}" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    printf 'worker'
  elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
    printf 'master'
  else
    printf 'unknown'
  fi
}
log_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
  local event="$1"
  local session_kind
  session_kind="$(derive_session_kind)"
  printf '{"ts":%d,"hook":"role-state-inject","event":"%s","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$event")" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}

# Detect hook event from stdin or environment
hook_event="UserPromptSubmit"
if [ -z "$1" ] && [[ "$0" == *"SessionStart"* ]]; then
  hook_event="SessionStart"
fi

trap 'log_fire "$hook_event"' EXIT

RS={{OPS_REPO}}/docs/runbooks/role-state.md
if [ -r "$RS" ]; then
  role=$(grep -m1 '^Current Role:' "$RS")
  lock=$(grep -m1 '^Role Lock:' "$RS")
  role_value="${role#Current Role:}"
  lock_value="${lock#Role Lock:}"
  if [ -n "$role" ] && [ -n "$lock" ] && [ -n "$(printf '%s' "$role_value" | tr -d '[:space:]')" ] && [ -n "$(printf '%s' "$lock_value" | tr -d '[:space:]')" ]; then
    echo "[role-state] ${role} | ${lock} | Execution rule: Proposal -> Approval -> Execution. Product-repo implementation goes to dispatched workers, never inline."
  else
    VERDICT="warn"
    echo "[role-state] WARNING: role-state markers missing in $RS — declare Current Role and Role Lock before proceeding."
  fi
else
  VERDICT="warn"
  echo "[role-state] WARNING: role-state.md unreadable at $RS — declare Role State before proceeding."
fi
