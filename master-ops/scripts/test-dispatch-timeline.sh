#!/usr/bin/env bash
# Promoted shape: `scripts/dispatch-timeline --json` against a scratch ledger,
# event log, and a fake orca on PATH joins all three sources in time order and
# exits 0. An id whose sources are all empty still exits 0 and names every
# missing source rather than printing an empty table silently.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/dispatch-timeline"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "$work/ledger.jsonl" <<'EOF'
{"ts": 100, "job_id": "ctx_demo", "orchestration_task": "task_demo", "decision": "ALLOW"}
EOF
cat > "$work/event-log.jsonl" <<'EOF'
{"ts": 50, "dispatch_id": "ctx_demo", "task_id": "task_demo", "event": "dispatch_launched", "outcome": "pass"}
{"ts": 150, "dispatch_id": "ctx_demo", "task_id": "task_demo", "event": "reaped", "outcome": "pass"}
EOF
cat > "$work/orca" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "orchestration dispatch-show")
    echo '{"result":{"dispatch":{"status":"COMPLETED","last_heartbeat_at":"1970-01-01T00:03:20+00:00"}}}'
    ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/orca"

run() {
  PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
    python3 "$SCRIPT" task_demo --ledger "$work/ledger.jsonl" --event-log "$work/event-log.jsonl" --json
}

# --- Case 1: three sources join in time order, none missing -----------------
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] \
  && printf '%s' "$out" | grep -q '"source":"event-log".*"event":"dispatch_launched"' \
  && printf '%s' "$out" | grep -q '"missing_sources":\[\]'; then
  ok "json: exit 0, all three sources joined, none missing"
else
  fail "json: expected a joined timeline with no missing sources, got exit $rc: $out"
fi

# The sort lives in the core module, not this thin CLI wrapper, and the
# wrapper resolves its own src/ root from its own __file__ (`parent.parent /
# "src"`), which wins over any PYTHONPATH override. So the mutant is a whole
# mirrored repo (scripts/ + src/, mutating only the copied core module) —
# never the committed files — with __pycache__ stripped so a stale .pyc
# copied alongside the mutated .py cannot shadow the edit.
core_module="$ROOT/src/master_runtime/core/dispatch_timeline.py"
mutant_repo="$work/mutant-repo"
mkdir -p "$mutant_repo/scripts"
cp "$SCRIPT" "$mutant_repo/scripts/dispatch-timeline"
cp -r "$ROOT/src" "$mutant_repo/src"
find "$mutant_repo/src" -name '__pycache__' -exec rm -rf {} + 2>/dev/null
mutant_core="$mutant_repo/src/master_runtime/core/dispatch_timeline.py"
sed 's/rows.sort(key=lambda row: row.timestamp)/pass  # sort removed/' "$core_module" > "$mutant_core"
if cmp -s "$core_module" "$mutant_core"; then
  fail "failability: sort-removal sed pattern did not match the script"
fi
mutant_out=$(PYTHONDONTWRITEBYTECODE=1 PATH="$work:$PATH" python3 "$mutant_repo/scripts/dispatch-timeline" task_demo \
  --ledger "$work/ledger.jsonl" --event-log "$work/event-log.jsonl" --json 2>&1)
# Unsorted insertion order is ledger (ts=100) then event-log (ts=50, ts=150):
# the first row's source flips from event-log to ledger once sorting is gone.
if printf '%s' "$mutant_out" | grep -q '"rows":\[{"timestamp":100.0,"source":"ledger"'; then
  ok "failability: removing the sort puts the ledger row first instead of the earlier event-log row"
else
  fail "failability: sort-removal mutant did not change row order"
fi
restored_out=$(run 2>&1)
if printf '%s' "$restored_out" | grep -q '"source":"event-log".*"event":"dispatch_launched"'; then
  ok "restored: unmutated core module sorts the event-log row first again"
else
  fail "restored: unmutated core module should still sort the event-log row first"
fi

# --- Case 2: an id with nothing in any source names all three as missing ----
empty_ledger="$work/empty-ledger.jsonl"
empty_log="$work/empty-event-log.jsonl"
: > "$empty_ledger"
: > "$empty_log"
empty_orca="$work/empty-orca-bin"
mkdir -p "$empty_orca"
cat > "$empty_orca/orca" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$empty_orca/orca"
empty_out=$(PYTHONPATH="$ROOT/src" PATH="$empty_orca:$PATH" python3 "$SCRIPT" task_nothing \
  --ledger "$empty_ledger" --event-log "$empty_log" --json 2>&1)
empty_rc=$?
if [ "$empty_rc" -eq 0 ] \
  && printf '%s' "$empty_out" | grep -q '"rows":\[\]' \
  && printf '%s' "$empty_out" | grep -q '"ledger"' \
  && printf '%s' "$empty_out" | grep -q '"event-log"' \
  && printf '%s' "$empty_out" | grep -q '"dispatch-show"'; then
  ok "json: an id with nothing anywhere names all three sources as missing"
else
  fail "json: expected empty rows with all three sources named missing, got exit $empty_rc: $empty_out"
fi

[ "$FAILED" -eq 0 ] && { echo "dispatch-timeline: all checks passed"; exit 0; }
echo "dispatch-timeline: FAILED"
exit 1
