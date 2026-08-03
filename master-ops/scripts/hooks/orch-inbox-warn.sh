#!/bin/bash
# UserPromptSubmit: warn once when unacked orchestration messages exist.
# Keep this resolution order in sync with onboarding-preflight.sh and dispatch-gate.
if [ -n "${ORCA_CLI_COMMAND:-}" ]; then
  orca_command="$ORCA_CLI_COMMAND"
elif [ -n "${ORCA_DEV_REPO_ROOT:-}" ]; then
  orca_command="orca-dev"
else
  orca_command="orca"
fi
command -v "$orca_command" >/dev/null 2>&1 || exit 0
out=$("$orca_command" orchestration check --peek --json 2>/dev/null) || exit 0
line=$(printf '%s' "$out" | python3 -c 'import json,sys
try:
  r=(json.load(sys.stdin).get("result") or {})
  c=int(r.get("count") or 0)
  if c < 1: raise SystemExit
  s=[" ".join(str((m or {}).get("subject","")).split())[:48] for m in (r.get("messages") or [])[:3]]
  s=[x for x in s if x]
  print(f"[orch-inbox] unacked={c}" + ((" | " + " ; ".join(s)) if s else ""))
except Exception:
  pass' 2>/dev/null)
[ -n "$line" ] && echo "$line"
exit 0
