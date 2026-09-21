#!/usr/bin/env bash
# PostToolUse(Bash): measure what actually came back, warn once when it is large.
#
# bash-output-trim-warn.sh looks at the command string before it runs and goes quiet the moment
# any filter token appears, so it never fired while one session spent 24% of its context on Bash
# results (measured on a seat). This hook reads the tool result after the fact and speaks only about size.
# It never blocks (exit 0 always) and prints one line, because the line itself costs context.
#
#   MOGUI_BASH_OUTPUT_WARN_CHARS   threshold in characters, default 6000 (about 1.5k tokens)
#
# The result JSON is read into a variable first: a heredoc program on `python3 -` would take
# python's stdin for itself and the piped result would never reach json.load. Measured 2026-09-14
# when the first version passed its own small-result test for exactly that reason.
set -u
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
  local session_kind
  session_kind="$(derive_session_kind)"
  printf '{"ts":%d,"hook":"bash-output-size-warn","event":"PostToolUse","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT
THRESH="${MOGUI_BASH_OUTPUT_WARN_CHARS:-6000}"
if ! [[ "$THRESH" =~ ^[0-9]+$ ]]; then
  VERDICT="skip"
  exit 0
fi
INPUT=$(cat)
if ! out=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(2)
if not isinstance(d, dict):
    sys.exit(2)
r = d.get("tool_response")
if isinstance(r, dict):
    text = "".join(str(r.get(k, "")) for k in ("stdout", "stderr", "output", "content")) or json.dumps(r, ensure_ascii=False)
else:
    text = "" if r is None else str(r)
n = len(text)
thresh = int(sys.argv[1])
if n > thresh:
    print(f"[output-size] this Bash result was {n} chars (~{n//4} tokens), over the {thresh}-char line. Next call: ask one question, filter every sub-command, grep instead of cat.")
' "$THRESH"); then
  VERDICT="skip"
  exit 0
fi
[ -n "$out" ] && VERDICT="warn"
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
