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
out=$(bd where 2>&1)
case "$out" in
  *mogui-master-ops/.beads*) echo "[tracker] bd resolves to mogui-master-ops/.beads (OK)" ;;
  *) echo "[tracker] WARNING: bd where did not resolve to the ops repository from the workspace root. First line: $(printf '%s' "$out" | head -1)" ;;
esac
if [ -n "$BEADS_DIR" ] && [ "$BEADS_DIR" != "{{OPS_REPO}}/.beads" ]; then
  echo "[tracker] WARNING: BEADS_DIR points outside the workspace ops repo: $BEADS_DIR"
fi

# Boot briefing: active protections, one line (owner feedback 2026-08-03 — quiet
# guards have zero presence; say what is standing watch).
supp=$(wc -l < ~/.mogui/guard-suppressions.jsonl 2>/dev/null | tr -d ' ')
decisions=$(grep -c 'mogui-master-ops/model-tier-policy.json' ~/.mogui/dispatch-ledger.jsonl 2>/dev/null || true)
decisions=${decisions:-0}
echo "[protections] active: role-state inject (every turn) | product-path hard block (overrides logged: ${supp:-0}) | bash trim-warn | dispatch gate+ledger (ops-policy decisions: ${decisions:-0}) | PreCompact memory reinject"
