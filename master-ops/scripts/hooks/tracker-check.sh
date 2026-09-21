#!/bin/bash
# SessionStart: warn when the tracker does not resolve to the ops repository from the
# workspace root (MASTER-OPERATIONS §7 — this failure is otherwise silent).

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
HOOK_CWD="$PWD"
if [[ "$FIRE_LOG" != /* ]]; then
  FIRE_LOG="$HOOK_CWD/$FIRE_LOG"
fi
json_str() {
  local value="${1-}"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=$(printf '%s' "$value" | tr -d '\000-\037\177')
  printf '%s' "$value"
}
derive_session_kind() {
  if [ -n "${ORCA_TASK_ID:-}" ] || [ -n "${ORCA_DISPATCH_ID:-}" ] || [[ "$HOOK_CWD" == *".orca/worktrees"* ]]; then
    printf 'worker'
  elif [ -f "$HOOK_CWD/docs/MASTER-OPERATIONS.md" ]; then
    printf 'master'
  else
    printf 'unknown'
  fi
}
HOOK_SESSION_KIND="$(derive_session_kind)"
log_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
  printf '{"ts":%d,"hook":"tracker-check","event":"SessionStart","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "$HOOK_CWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$HOOK_SESSION_KIND")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap log_fire EXIT

# WORKSPACE_ROOT lets a test point the hook at a scratch tree; the install path is the default.
ROOT_DEFAULT='{{WORKSPACE_ROOT}}'
cd "${WORKSPACE_ROOT:-$ROOT_DEFAULT}" || { VERDICT="skip"; exit 0; }
OPS_BASENAME="$(basename "{{OPS_REPO}}")"
out=$(bd where 2>&1)
case "$out" in
  *"$OPS_BASENAME"/.beads*) echo "[tracker] bd resolves to $OPS_BASENAME/.beads (OK)" ;;
  *) VERDICT="warn"; echo "[tracker] WARNING: bd where did not resolve to the ops repository from the workspace root. First line: $(printf '%s' "$out" | head -1)" ;;
esac
if [ -n "$BEADS_DIR" ] && [ "$BEADS_DIR" != "{{OPS_REPO}}/.beads" ]; then
  VERDICT="warn"
  echo "[tracker] WARNING: BEADS_DIR points outside the workspace ops repo: $BEADS_DIR"
fi

# Boot briefing: one line naming which shipped protections are actually wired. Measured
# 2026-09-14: the previous fixed string called two unwired guards "active" on a peer
# seat while the same boot's self-check listed them as UNWIRED. Wiring is read from the
# settings file; a shipped hook that no command references prints as NOT WIRED. Warn only.
supp=$(wc -l < ~/.mogui/guard-suppressions.jsonl 2>/dev/null | tr -d ' ')
# Count only ledger rows that name this install's policy path (basename-scoped).
# No bare filename fallback — a shared ledger must not import other installs.
decisions=$(grep -cF -- "$OPS_BASENAME/model-tier-policy.json" ~/.mogui/dispatch-ledger.jsonl 2>/dev/null || true)
decisions=${decisions:-0}
HOOKS_DIR="${MOGUI_HOOKS_DIR:-$(cd "$(dirname "$0")" && pwd)}"
# scripts/hooks -> scripts -> ops repo -> workspace root; seat settings live under root.
SEAT_ROOT="${WORKSPACE_ROOT:-$(cd "$HOOKS_DIR/../../.." 2>/dev/null && pwd)}"
SETTINGS="${MOGUI_SETTINGS_FILE:-$SEAT_ROOT/.claude/settings.json}"
wired_blob=$(python3 -c '
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
print("\n".join(h.get("command","") for arr in (d.get("hooks") or {}).values() for m in arr for h in (m.get("hooks") or [])))' "$SETTINGS" 2>/dev/null)
active=""; unwired=""
for f in "$HOOKS_DIR"/*.sh; do
  n=$(basename "$f"); [ "$n" = "tracker-check.sh" ] && continue
  # A hook counts as wired only when a command names it as a path token: /<name> followed by a quote, a space, or the end.
  if printf '%s\n' "$wired_blob" | grep -qE "/$(printf '%s' "$n" | sed 's/\./\\./g')([\"' ]|\$)"; then active="$active ${n%.sh}"; else unwired="$unwired ${n%.sh}"; fi
done
[ -n "$unwired" ] && VERDICT="warn"
echo "[protections] wired:${active:- none} (overrides logged: ${supp:-0}, ops-policy decisions: ${decisions:-0})${unwired:+ | NOT WIRED:$unwired}"
