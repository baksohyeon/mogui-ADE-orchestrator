#!/bin/bash
# UserPromptSubmit: warn once when unacked orchestration messages exist.

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
log_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"orch-inbox-warn","event":"UserPromptSubmit","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" "$VERDICT" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

command -v orca >/dev/null 2>&1 || { VERDICT="skip"; exit 0; }
# heartbeat is a liveness signal, not work: it is counted, never listed, and never wakes the master alone.
out=$(orca orchestration check --peek --json 2>/dev/null) || { VERDICT="skip"; exit 0; }
line=$(printf '%s' "$out" | python3 -c 'import json,sys
try:
  payload=json.load(sys.stdin)
  if not isinstance(payload, dict) or "result" not in payload or not isinstance(payload.get("result"), dict):
    print("__SKIP__")
    raise SystemExit
  r=payload.get("result")
  ms=[m for m in (r.get("messages") or []) if isinstance(m, dict)]
  act=[m for m in ms if m.get("type") != "heartbeat"]
  hb=len(ms)-len(act)
  if not act:
    print("__PASS__")
    raise SystemExit
  s=[" ".join(str(m.get("subject","")).split())[:48] for m in act[:3]]
  s=[x for x in s if x]
  print(f"[orch-inbox] unacked={len(act)}" + ((" | " + " ; ".join(s)) if s else "") + (f" | heartbeats={hb}" if hb else ""))
except Exception:
  print("__SKIP__")' 2>/dev/null)
case "$line" in
  "__PASS__") ;;
  "__SKIP__"|"") VERDICT="skip" ;;
  *) VERDICT="warn"; echo "$line" ;;
esac
exit 0
