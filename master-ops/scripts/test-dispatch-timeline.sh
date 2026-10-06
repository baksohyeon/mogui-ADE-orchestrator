#!/usr/bin/env bash
# Promoted shape: `scripts/dispatch-timeline --json` against a scratch ledger,
# event log, and a fake orca on PATH joins all three sources in time order and
# exits 0. An id whose sources are all empty still exits 0 and names every
# missing source rather than printing an empty table silently.
#
# The runtime root resolves from MOGUI_RUNTIME_ROOT first, then the two-up
# layout. A test that cannot see the module under test has nothing to
# measure, so with neither resolved this file prints a SKIP line and exits 0.
set -u

resolve_runtime_root() {
  # $1 = MOGUI_RUNTIME_ROOT (may be empty), $2 = two-up candidate.
  # Prints the resolved root on success (exit 0), or the SKIP line (exit 1).
  if [ -n "$1" ] && [ -e "$1/scripts/dispatch-timeline" ]; then
    printf '%s\n' "$1"
  elif [ -e "$2/scripts/dispatch-timeline" ]; then
    printf '%s\n' "$2"
  else
    echo "SKIP: runtime root not found (set MOGUI_RUNTIME_ROOT)"
    return 1
  fi
}

two_up="$(cd "$(dirname "$0")/../.." && pwd)"
if ! ROOT="$(resolve_runtime_root "${MOGUI_RUNTIME_ROOT:-}" "$two_up")"; then
  echo "$ROOT"
  exit 0
fi
SCRIPT="$ROOT/scripts/dispatch-timeline"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# --- Case 0: root resolution picks MOGUI_RUNTIME_ROOT, then two-up, then SKIPs
root_fixture="$work/root-fixture"
mkdir -p "$root_fixture/scripts" "$root_fixture/src/master_runtime/core"
: > "$root_fixture/scripts/dispatch-timeline"
: > "$root_fixture/src/master_runtime/core/dispatch_timeline.py"

override_out=$(resolve_runtime_root "$root_fixture" "$ROOT"); override_rc=$?
if [ "$override_rc" -eq 0 ] && [ "$override_out" = "$root_fixture" ]; then
  ok "root: MOGUI_RUNTIME_ROOT wins over a valid two-up layout (exit $override_rc)"
else
  fail "root: expected $root_fixture, got exit $override_rc: $override_out"
fi

empty_root="$work/empty-root"
mkdir -p "$empty_root"
skip_out=$(resolve_runtime_root "" "$empty_root"); skip_rc=$?
if [ "$skip_rc" -eq 1 ] && [ "$skip_out" = "SKIP: runtime root not found (set MOGUI_RUNTIME_ROOT)" ]; then
  ok "root: no override and no two-up layout prints SKIP and signals not-found (exit $skip_rc)"
else
  fail "root: expected the SKIP line and exit 1, got exit $skip_rc: $skip_out"
fi

# A stale or mistyped MOGUI_RUNTIME_ROOT (an existing directory without the
# runtime) must not win over a valid two-up layout.
stale_root="$work/stale-root"
mkdir -p "$stale_root"
stale_out=$(resolve_runtime_root "$stale_root" "$root_fixture"); stale_rc=$?
if [ "$stale_rc" -eq 0 ] && [ "$stale_out" = "$root_fixture" ]; then
  ok "root: a stale MOGUI_RUNTIME_ROOT without the marker falls back to the valid two-up layout"
else
  fail "root: expected the stale override to fall back to $root_fixture, got exit $stale_rc: $stale_out"
fi

# Mutant: re-run the deleted `ROOT="$(cd "$(dirname "$0")/../.." && pwd)"`
# expression itself, which always took the two-up path with no existence
# check and no MOGUI_RUNTIME_ROOT override, and confirm it cannot land on
# root_fixture the way the fixed resolver does.
mutant_out="$(cd "$(dirname "$0")/../.." && pwd)"; mutant_rc=$?
if [ "$mutant_rc" -eq 0 ] && [ "$mutant_out" = "$root_fixture" ]; then
  fail "failability: the old ROOT line should not have honored MOGUI_RUNTIME_ROOT"
else
  ok "failability: the old ROOT line ignores MOGUI_RUNTIME_ROOT (exit $mutant_rc, got $mutant_out instead of $root_fixture)"
fi

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
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
    python3 "$SCRIPT" task_demo --ledger "$work/ledger.jsonl" --event-log "$work/event-log.jsonl" --json
}

# --- Case 1: three sources join in time order, none missing -----------------
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] \
  && printf '%s' "$out" | grep -q '"rows":\[{"timestamp":50.0,"source":"event-log","event":"dispatch_launched"' \
  && printf '%s' "$out" | grep -q '"source":"dispatch-show"' \
  && printf '%s' "$out" | grep -q '"missing_sources":\[\]'; then
  ok "json: exit 0, all three sources joined in time order, none missing"
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
empty_out=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$empty_orca:$PATH" python3 "$SCRIPT" task_nothing \
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

# --- Case 3: --since combined with a positional id is a usage error --------
since_and_id_out=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
  python3 "$SCRIPT" task_demo --since 1 --ledger "$work/ledger.jsonl" \
  --event-log "$work/event-log.jsonl" --json 2>&1)
since_and_id_rc=$?
if [ "$since_and_id_rc" -eq 2 ]; then
  ok "usage: --since with a positional id exits 2"
else
  fail "usage: expected exit 2 for --since with an id, got exit $since_and_id_rc: $since_and_id_out"
fi

# --- Case 4: --since rejects non-finite and negative hours at parse time ----
for bad_since in nan inf -1; do
  bad_since_out=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
    python3 "$SCRIPT" --since "$bad_since" --ledger "$work/ledger.jsonl" \
    --event-log "$work/event-log.jsonl" --json 2>&1)
  bad_since_rc=$?
  if [ "$bad_since_rc" -eq 2 ]; then
    ok "usage: --since $bad_since exits 2"
  else
    fail "usage: expected exit 2 for --since $bad_since, got exit $bad_since_rc: $bad_since_out"
  fi
done

# --- Case 5b: a positive --since lists the existing fixtures' dispatch id --
# --since is hours-ago; the fixtures carry 1970 epoch timestamps, so the
# window must reach before the epoch. Derive enough hours from the current
# time rather than picking an arbitrary magic number.
since_hours=$(( $(date +%s) / 3600 + 1 ))
since_out=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
  python3 "$SCRIPT" --since "$since_hours" --ledger "$work/ledger.jsonl" \
  --event-log "$work/event-log.jsonl" --json 2>&1)
since_rc=$?
if [ "$since_rc" -eq 0 ] \
  && printf '%s' "$since_out" | grep -q '"dispatch_id":"ctx_demo"' \
  && printf '%s' "$since_out" | grep -q '"task_id":"task_demo"'; then
  ok "since: a positive window lists ctx_demo/task_demo from the existing fixtures"
else
  fail "since: expected ctx_demo/task_demo listed for a positive window, got exit $since_rc: $since_out"
fi

# Same mirrored-repo mutant technique as Case 1: mutate only the copy, never
# the committed core module, with __pycache__ stripped.
since_mutant_repo="$work/mutant-repo-since"
mkdir -p "$since_mutant_repo/scripts"
cp "$SCRIPT" "$since_mutant_repo/scripts/dispatch-timeline"
cp -r "$ROOT/src" "$since_mutant_repo/src"
find "$since_mutant_repo/src" -name '__pycache__' -exec rm -rf {} + 2>/dev/null
since_mutant_core="$since_mutant_repo/src/master_runtime/core/dispatch_timeline.py"
sed 's/return sorted(last_seen.values(), key=lambda row: row\["last_ts"\], reverse=True)/return []/' \
  "$core_module" > "$since_mutant_core"
if cmp -s "$core_module" "$since_mutant_core"; then
  fail "failability: list_since-emptying sed pattern did not match the script"
fi
since_mutant_out=$(PYTHONDONTWRITEBYTECODE=1 PATH="$work:$PATH" python3 "$since_mutant_repo/scripts/dispatch-timeline" \
  --since "$since_hours" --ledger "$work/ledger.jsonl" --event-log "$work/event-log.jsonl" --json 2>&1)
if printf '%s' "$since_mutant_out" | grep -q '"dispatch_id":"ctx_demo"'; then
  fail "failability: list_since-emptying mutant should not list ctx_demo"
else
  ok "failability: emptying list_since drops the previously-listed dispatch id"
fi

# --- Case 5: human-readable mode survives an out-of-range timestamp --------
huge_ledger="$work/huge-ts-ledger.jsonl"
cat > "$huge_ledger" <<'EOF'
{"ts": 999999999999999, "job_id": "ctx_huge", "orchestration_task": "task_huge", "decision": "ALLOW"}
EOF
huge_event_log="$work/huge-event-log.jsonl"
: > "$huge_event_log"
huge_out=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" PATH="$work:$PATH" \
  python3 "$SCRIPT" task_huge --ledger "$huge_ledger" --event-log "$huge_event_log" 2>&1)
huge_rc=$?
if [ "$huge_rc" -eq 0 ] && printf '%s' "$huge_out" | grep -q 'unparseable'; then
  ok "human-readable: an out-of-range timestamp prints 'unparseable' instead of crashing"
else
  fail "human-readable: expected exit 0 with 'unparseable', got exit $huge_rc: $huge_out"
fi

[ "$FAILED" -eq 0 ] && { echo "dispatch-timeline: all checks passed"; exit 0; }
echo "dispatch-timeline: FAILED"
exit 1
