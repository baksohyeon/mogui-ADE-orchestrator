#!/bin/bash
# PreToolUse(Bash) hook: warn when command starts with bare `cd`.
# This hook is warning-only and never blocks execution.

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
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || return 0
  local session_kind
  session_kind="$(derive_session_kind)"
  printf '{"ts":%d,"hook":"bash-bare-cd-warn","event":"PreToolUse(Bash)","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

INPUT=$(cat)
WARN=$(
  printf '%s' "$INPUT" | python3 -c '
import json
import shlex
import sys

try:
    payload = json.load(sys.stdin)
    raw = payload.get("tool_input", {}).get("command", "")
except (ValueError, AttributeError, TypeError):
    # ValueError includes JSONDecodeError; all malformed/shape inputs should stay silent.
    print("skip")
    raise SystemExit(0)

# Some runtimes may encode command as a list of lines.
if isinstance(raw, list):
    command = "\n".join(str(part) for part in raw)
elif isinstance(raw, str):
    command = raw
else:
    command = str(raw or "")

if not command.strip():
    print("pass")
    raise SystemExit(0)

try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    tokens = list(lexer)
except Exception:
    # Parsing failures should never block or warn.
    print("skip")
    raise SystemExit(0)

first = ""
for token in tokens:
    if token:
        first = token
        break

# Subshell-wrapped calls begin with "("; only bare first-token cd should warn.
print("warn" if first == "cd" else "pass")
'
)

if [ "$WARN" = "warn" ]; then
  VERDICT="warn"
  echo "[bash-bare-cd-warn] first token is bare cd; shell state persists between Bash calls, use git -C/gh --repo/absolute paths." >&2
elif [ "$WARN" = "skip" ]; then
  VERDICT="skip"
fi

exit 0
