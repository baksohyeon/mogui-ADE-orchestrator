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

cd {{WORKSPACE_ROOT}} || exit 0
OPS_BASENAME="$(basename "{{OPS_REPO}}")"
out=$(bd where 2>&1)
case "$out" in
  *"$OPS_BASENAME"/.beads*) echo "[tracker] bd resolves to $OPS_BASENAME/.beads (OK)" ;;
  *) echo "[tracker] WARNING: bd where did not resolve to the ops repository from the workspace root. First line: $(printf '%s' "$out" | head -1)" ;;
esac
if [ -n "$BEADS_DIR" ] && [ "$BEADS_DIR" != "{{OPS_REPO}}/.beads" ]; then
  echo "[tracker] WARNING: BEADS_DIR points outside the workspace ops repo: $BEADS_DIR"
fi

# Boot briefing: active protections, one line (owner feedback 2026-08-03 — quiet
# guards have zero presence; say what is standing watch).
supp=$(wc -l < ~/.mogui/guard-suppressions.jsonl 2>/dev/null | tr -d ' ')
# Count only ledger rows that name this install's policy path when possible;
# fall back to the basename so a shared per-user ledger still yields a number.
decisions=$(grep -cF -- "$OPS_BASENAME/model-tier-policy.json" ~/.mogui/dispatch-ledger.jsonl 2>/dev/null || true)
if [ "${decisions:-0}" = "0" ]; then
  decisions=$(grep -cF -- 'model-tier-policy.json' ~/.mogui/dispatch-ledger.jsonl 2>/dev/null || true)
fi
decisions=${decisions:-0}
echo "[protections] active: role-state inject (every turn) | product-path hard block (overrides logged: ${supp:-0}) | bash trim-warn | dispatch gate+ledger (ops-policy decisions: ${decisions:-0}) | PreCompact memory reinject"
