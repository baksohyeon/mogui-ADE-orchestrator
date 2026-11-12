#!/bin/bash
# UserPromptSubmit: surface today's dispatches that lack a tracker card.

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
  printf '{"ts":%d,"hook":"bd-gap-warn","event":"UserPromptSubmit","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

LEDGER="${DISPATCH_GATE_LEDGER:-}"
if [ -z "$LEDGER" ] && [ -n "${MOGUI_STATE_DIR:-}" ]; then
  LEDGER="$MOGUI_STATE_DIR/dispatch-ledger.jsonl"
fi
if [ -z "$LEDGER" ]; then
  LEDGER="${HOME:-$(cd ~ && pwd)}/.mogui/dispatch-ledger.jsonl"
fi

if [ ! -f "$LEDGER" ] || ! command -v python3 >/dev/null 2>&1; then
  VERDICT="skip"
  exit 0
fi

RESULT=$(LEDGER="$LEDGER" python3 - <<'PY'
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ledger = Path(os.environ["LEDGER"])
kst = timezone(timedelta(hours=9))
today_start = datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
today_start_ts = today_start.timestamp()
missing = 0

def reverse_lines(path, block_size=8192):
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""
        while position > 0:
            size = min(block_size, position)
            position -= size
            handle.seek(position)
            buffer = handle.read(size) + buffer
            parts = buffer.split(b"\n")
            buffer = parts[0]
            for part in reversed(parts[1:]):
                yield part.decode("utf-8", errors="replace")
        if buffer:
            yield buffer.decode("utf-8", errors="replace")

try:
    rows = reverse_lines(ledger)
    for line in rows:
        try:
            row = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict):
            continue
        stamp = row.get("ts")
        try:
            stamp_value = float(stamp)
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp_value < today_start_ts:
            break
        if row.get("decision") != "ALLOW" or not row.get("job_id"):
            continue
        if not str(row.get("card") or "").strip():
            missing += 1
except OSError:
    raise SystemExit(0)

active = 0
if missing and __import__("shutil").which("bd"):
    try:
        result = subprocess.run(
            ["bd", "list", "--status=in_progress", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            payload = json.loads(result.stdout)
            if isinstance(payload, list):
                active = len(payload)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        pass

if missing:
    print(f"[bd-gap] today: {missing} dispatches without a card · {active} in_progress")
    print("warn")
PY
)
MESSAGE=$(printf '%s\n' "$RESULT" | sed -n '1p')
if [ -n "$MESSAGE" ]; then
  VERDICT="warn"
  printf '%s\n' "$MESSAGE"
else
  VERDICT="pass"
fi
exit 0
