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
  *"gh api graphql"*|*"orca terminal list"*|*"orca terminal read"*|*"git log"*|*"git diff"*|*"git show"*|*"pytest"*|*"cat "*) ;;
  *) exit 0;;
esac
is_bounded_stage() {
  local stage="$1" command_name
  stage="${stage#"${stage%%[![:space:]]*}"}"
  command_name="${stage%%[[:space:]]*}"
  case "$command_name" in
    head|tail|wc) return 0;;
    gh)
      [[ "$stage" == *"--jq"* ]] && return 0
      ;;
    grep)
      [[ "$stage" =~ (^|[[:space:]])grep[[:space:]]+(-[[:alnum:]]*[cq][[:alnum:]]*|--count|--quiet)([[:space:]]|$) ]] && return 0
      ;;
    rg)
      [[ "$stage" =~ (^|[[:space:]])rg([[:space:]]+.*)?[[:space:]](-c|--count|-q|--quiet|-l)([[:space:]]|$) ]] && return 0
      [[ "$stage" =~ (^|[[:space:]])rg([[:space:]]+.*)?[[:space:]](-m[[:space:]]*[0-9]+|--max-count(=|[[:space:]]+)[0-9]+)([[:space:]]|$) ]] && return 0
      ;;
  esac
  return 1
}

# Return the first simple command and the remainder split at ;, &&, or ||.
# A single | stays in the command so the final pipeline stage can be checked.
split_compound() {
  local text="$1" char next i
  for ((i = 0; i < ${#text}; i++)); do
    char="${text:i:1}"
    next="${text:i+1:1}"
    if [[ "$char" == ";" ]]; then
      SPLIT_SEGMENT="${text:0:i}"
      SPLIT_REMAINDER="${text:i+1}"
      return 0
    fi
    if [[ "$char" == "&" && "$next" == "&" ]] || [[ "$char" == "|" && "$next" == "|" ]]; then
      SPLIT_SEGMENT="${text:0:i}"
      SPLIT_REMAINDER="${text:i+2}"
      return 0
    fi
  done
  return 1
}

has_unbounded_large_segment() {
  local remaining="$1" segment final_stage
  while :; do
    if split_compound "$remaining"; then
      segment="$SPLIT_SEGMENT"
      remaining="$SPLIT_REMAINDER"
    else
      segment="$remaining"
      remaining=""
    fi
    case "$segment" in
      *"gh api graphql"*|*"orca terminal list"*|*"orca terminal read"*|*"git log"*|*"git diff"*|*"git show"*|*"pytest"*|*"cat "*)
        final_stage="${segment##*|}"
        is_bounded_stage "$final_stage" || return 0
        ;;
    esac
    [[ -z "$remaining" ]] && break
  done
  return 1
}

if has_unbounded_large_segment "$CMD"; then
  VERDICT="warn"
  echo "[trim-warn] 대용량 출력 가능 명령에 필터가 없다. rg -m N/--max-count N, rg -c/--count, rg -q/--quiet, rg -l, head/tail/--jq/wc/grep -c/grep -q로 필요한 줄만 받아라 (L0 토큰 규칙)"
fi
exit 0
