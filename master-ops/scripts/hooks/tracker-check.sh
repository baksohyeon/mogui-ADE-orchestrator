#!/bin/bash
# SessionStart: warn when the tracker does not resolve to the ops repository from the
# workspace root (MASTER-OPERATIONS §7 — this failure is otherwise silent).

log_fire() {
  mkdir -p ~/.mogui
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"tracker-check","event":"SessionStart","cwd":"%s","runtime_hint":"%s","session_kind":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" >> ~/.mogui/hook-fire-log.jsonl 2>/dev/null || true
}

log_fire

# WORKSPACE_ROOT lets a test point the hook at a scratch tree; the install path is the default.
ROOT_DEFAULT='{{WORKSPACE_ROOT}}'
cd "${WORKSPACE_ROOT:-$ROOT_DEFAULT}" || exit 0
OPS_BASENAME="$(basename "{{OPS_REPO}}")"
out=$(bd where 2>&1)
case "$out" in
  *"$OPS_BASENAME"/.beads*) echo "[tracker] bd resolves to $OPS_BASENAME/.beads (OK)" ;;
  *) echo "[tracker] WARNING: bd where did not resolve to the ops repository from the workspace root. First line: $(printf '%s' "$out" | head -1)" ;;
esac
if [ -n "$BEADS_DIR" ] && [ "$BEADS_DIR" != "{{OPS_REPO}}/.beads" ]; then
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
  case "$wired_blob" in *"$n"*) active="$active ${n%.sh}";; *) unwired="$unwired ${n%.sh}";; esac
done
echo "[protections] wired:${active:- none} (overrides logged: ${supp:-0}, ops-policy decisions: ${decisions:-0})${unwired:+ | NOT WIRED:$unwired}"
