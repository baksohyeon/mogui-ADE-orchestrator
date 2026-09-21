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

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
log_fire() {
mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
session_kind="${MOGUI_SESSION_KIND:-master}"
printf '{"ts":%s,"hook":"worker-block-warn","event":"%s","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
  "$(date +%s)" "${1:-UserPromptSubmit}" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" "$VERDICT" \
  >> "$FIRE_LOG" 2>/dev/null || true
}
hook_event="${1:-UserPromptSubmit}"
trap 'log_fire "$hook_event"' EXIT

listing=$(orca terminal list 2>/dev/null) || { VERDICT="skip"; exit 0; }
[ -z "$listing" ] && { VERDICT="skip"; exit 0; }

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

# Approval markers live in one file that this hook and worker-pane-sweep both read; see the
# header there for why. A missing file is reported, never silently treated as "no prompts".
markers_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/approval-prompt-markers.txt"
approval_re=$(grep -vE '^[[:space:]]*(#|$)' "$markers_file" 2>/dev/null | paste -sd'|' -)
if [ -z "$approval_re" ]; then
  VERDICT="skip"
  echo "[worker-block] approval marker file unreadable or empty: $markers_file; approval prompts are not being detected"
  blocked=0
else
  blocked=$(printf '%s' "$listing" | grep -icE "$approval_re" || true)
fi
limit=$(printf '%s'  "$listing" | grep -icE "quota reached|resets in [0-9]|rate limit|usage limit|upgrade your subscription" || true)
update=$(printf '%s' "$listing" | grep -icE "please restart|update ran successfully|was successfully upgraded" || true)
gate=$(printf '%s'   "$listing" | grep -icE "new worktree.*resume session|resume session.*changelog" || true)

total=$(( blocked + limit + update + gate ))
[ "$total" -eq 0 ] && exit 0

VERDICT="warn"
parts=""
[ "$blocked" -gt 0 ] && parts="$parts approval=$blocked"
[ "$limit" -gt 0 ]   && parts="$parts limit=$limit"
[ "$update" -gt 0 ]  && parts="$parts update=$update"
[ "$gate" -gt 0 ]    && parts="$parts start-screen=$gate"
echo "[worker-block]$parts | a pane is waiting, not working. Classify it before acting: scripts/worker-pane-sweep"
exit 0
