#!/bin/bash
# PreToolUse(Bash) 경고형 훅: 대용량 출력 명령이 필터 없이 실행되면 한 줄 경고.
# 차단하지 않는다. 토큰 절약 규칙(L0, Dorito 2026-08-03)의 리마인더다.

log_fire() {
  mkdir -p ~/.mogui
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"bash-output-trim-warn","event":"PreToolUse(Bash)","cwd":"%s","runtime_hint":"%s","session_kind":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" >> ~/.mogui/hook-fire-log.jsonl 2>/dev/null || true
}

log_fire

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
case "$CMD" in
  *"| head"*|*"| tail"*|*"| grep"*|*"--jq"*|*"| python3"*|*"| wc"*|*"-m json.tool"*|*"| cut"*) exit 0;;
esac
case "$CMD" in
  *"gh api graphql"*|*"orca terminal list"*|*"orca terminal read"*|*"git log"*|*"git diff"*|*"git show"*|*"pytest"*|*"cat "*)
    echo "[trim-warn] 대용량 출력 가능 명령에 필터가 없다. --jq/tail/grep로 필요한 줄만 받아라 (L0 토큰 규칙)" ;;
esac
exit 0
