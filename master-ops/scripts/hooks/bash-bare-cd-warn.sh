#!/bin/bash
# PreToolUse(Bash) hook: warn when command starts with bare `cd`.
# This hook is warning-only and never blocks execution.

log_fire() {
  local fire_log="${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}"
  mkdir -p "$(dirname "$fire_log")" 2>/dev/null || return 0
  local session_kind="unknown"
  if [ -n "${ORCA_TASK_ID:-}" ] || [ -n "${ORCA_DISPATCH_ID:-}" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
    session_kind="master"
  fi
  python3 - "bash-bare-cd-warn" "PreToolUse(Bash)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" <<'PY' >> "$fire_log" 2>/dev/null || true
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
WARN=$(
  printf '%s' "$INPUT" | python3 -c '
import json
import shlex
import sys

payload = json.load(sys.stdin)
raw = payload.get("tool_input", {}).get("command", "")

# Some runtimes may encode command as a list of lines.
if isinstance(raw, list):
    command = "\n".join(str(part) for part in raw)
elif isinstance(raw, str):
    command = raw
else:
    command = str(raw or "")

if not command.strip():
    print("0")
    raise SystemExit(0)

try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    tokens = list(lexer)
except Exception:
    # Parsing failures should never block or warn.
    print("0")
    raise SystemExit(0)

first = ""
for token in tokens:
    if token:
        first = token
        break

# Subshell-wrapped calls begin with "("; only bare first-token cd should warn.
print("1" if first == "cd" else "0")
'
)

if [ "$WARN" = "1" ]; then
  echo "[bash-bare-cd-warn] first token is bare cd; shell state persists between Bash calls, use git -C/gh --repo/absolute paths." >&2
fi

exit 0
