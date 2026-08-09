#!/usr/bin/env bash
# Tell the coordinator, every turn, when a worker pane needs a decision.
#
# Why a hook and not a script. On 2026-08-06 a claude worker stopped on a destructive-op prompt
# that --dangerously-skip-permissions does not cover, and the owner cleared it because the
# coordinator never looked. Clearing an in-scope prompt is dispatch authority (charter 04), so
# that was the coordinator's job. Its monitoring polled the orchestration inbox and pull-request
# state, and a blocked worker changes neither: no message arrives, no commit lands, and silence
# reads as progress. See the measured blocked-worker prompt incident.
#
# One RPC on purpose. `orca terminal list` already returns a preview per pane, so this classifies
# from that instead of reading every pane, which would be ~20 calls per turn. The tradeoff is a
# shorter frame: this hook decides only whether to LOOK, never what to do. Read the pane before
# acting — firing text at a start screen exits it.
#
# fail-open by contract: logging or RPC trouble must never block a turn.
set -uo pipefail

if [ -n "${MOGUI_HOOK_FIRE_LOG:-}" ]; then FIRE_LOG="$MOGUI_HOOK_FIRE_LOG"; else FIRE_LOG="$HOME/.mogui/hook-fire-log.jsonl"; fi
session_kind="${MOGUI_SESSION_KIND:-master}"
python3 - "$FIRE_LOG" "${1:-UserPromptSubmit}" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" <<'PY' >/dev/null 2>&1 || true
import json
import os
import sys
import time

path, event, cwd, runtime_hint, session_kind = sys.argv[1:]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps({
        "ts": int(time.time()),
        "hook": "worker-block-warn",
        "event": event,
        "cwd": cwd,
        "runtime_hint": runtime_hint,
        "session_kind": session_kind,
    }, ensure_ascii=False) + "\n")
PY

listing=$(orca terminal list 2>/dev/null) || exit 0
[ -z "$listing" ] && exit 0

# Drop this session's own pane and its preview before matching. The coordinator writes about
# prompts, quotas, and restarts as ordinary work, so its own frame matches these markers.
# Measured 2026-08-06 on the companion sweep, which reported the coordinator as blocked on
# approval while it was writing about approvals. Same family as `grep -v grep` deleting the
# master from its own process scan.
if [ -n "${ORCA_TERMINAL_HANDLE:-}" ]; then
  listing=$(printf '%s' "$listing" | awk -v self="$ORCA_TERMINAL_HANDLE" '
    /^term_/ { skip = ($1 == self) } !skip')
fi
# Strip runtime status lines: "always-approve" and "bypass permissions" announce that approvals
# are automatic, which is the opposite of a prompt.
listing=$(printf '%s' "$listing" | sed 's/always-approve//g; s/bypass permissions//g')

# A prompt is prompt-shaped: numbered choices, or an explicit proceed question. Matching the bare
# word "approve" anywhere caught code listings on the first run, so the markers are narrower here.
blocked=$(printf '%s' "$listing" | grep -icE "do you want to proceed|1\. yes|2\. yes, and|\[y/n\]|\(y/n\)|press enter to continue|trust this (folder|workspace)" || true)
limit=$(printf '%s'  "$listing" | grep -icE "quota reached|resets in [0-9]|rate limit|usage limit|upgrade your subscription" || true)
update=$(printf '%s' "$listing" | grep -icE "please restart|update ran successfully|was successfully upgraded" || true)
gate=$(printf '%s'   "$listing" | grep -icE "new worktree.*resume session|resume session.*changelog" || true)

total=$(( blocked + limit + update + gate ))
[ "$total" -eq 0 ] && exit 0

parts=""
[ "$blocked" -gt 0 ] && parts="$parts approval=$blocked"
[ "$limit" -gt 0 ]   && parts="$parts limit=$limit"
[ "$update" -gt 0 ]  && parts="$parts update=$update"
[ "$gate" -gt 0 ]    && parts="$parts start-screen=$gate"
echo "[worker-block]$parts | a pane is waiting, not working. Classify it before acting: scripts/worker-pane-sweep"
exit 0
