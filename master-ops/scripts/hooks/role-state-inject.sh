#!/bin/bash
# UserPromptSubmit/SessionStart: inject role state + execution rule.
# Exists to counter host-injected autonomy defaults (MASTER-OPERATIONS §7/§8, owner-approved 2026-08-03).

log_fire() {
  mkdir -p ~/.mogui
  local event="$1"
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"role-state-inject","event":"%s","cwd":"%s","runtime_hint":"%s","session_kind":"%s"}\n' \
    "$(date +%s)" "$event" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" >> ~/.mogui/hook-fire-log.jsonl 2>/dev/null || true
}

# Detect hook event from stdin or environment
hook_event="UserPromptSubmit"
if [ -z "$1" ] && [[ "$0" == *"SessionStart"* ]]; then
  hook_event="SessionStart"
fi

log_fire "$hook_event"

RS={{OPS_REPO}}/docs/runbooks/role-state.md
if [ -r "$RS" ]; then
  role=$(grep -m1 '^Current Role:' "$RS")
  lock=$(grep -m1 '^Role Lock:' "$RS")
  echo "[role-state] ${role:-Current Role: UNKNOWN} | ${lock:-Role Lock: UNKNOWN} | Execution rule: Proposal -> Approval -> Execution. Product-repo implementation goes to dispatched workers, never inline."
else
  echo "[role-state] WARNING: role-state.md unreadable at $RS — declare Role State before proceeding."
fi
