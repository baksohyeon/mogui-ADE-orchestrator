#!/bin/bash
# PreToolUse(Bash) 경고형 훅: 대용량 출력 명령이 필터 없이 실행되면 한 줄 경고.
# 차단하지 않는다. 토큰 절약 규칙(L0, Dorito 2026-08-03)의 리마인더다.

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
  printf '{"ts":%d,"hook":"bash-output-trim-warn","event":"PreToolUse(Bash)","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

INPUT=$(cat)
if ! CMD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null); then
  VERDICT="skip"
  exit 0
fi
case "$CMD" in
  *"| head"*|*"| tail"*|*"| grep"*|*"--jq"*|*"| python3"*|*"| wc"*|*"-m json.tool"*|*"| cut"*) exit 0;;
esac
case "$CMD" in
  *"gh api graphql"*|*"orca terminal list"*|*"orca terminal read"*|*"git log"*|*"git diff"*|*"git show"*|*"pytest"*|*"cat "*)
    VERDICT="warn"
    echo "[trim-warn] 대용량 출력 가능 명령에 필터가 없다. --jq/tail/grep로 필요한 줄만 받아라 (L0 토큰 규칙)" ;;
esac
exit 0
