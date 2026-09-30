#!/usr/bin/env bash
# Promoted shape: `--once --json` against a scratch ledger and a fake orca on PATH
# prints the accounting table and exits 0; a held lock makes a second waiter
# exit 2. Each case below also runs against a sed-mutated copy of the real
# script to prove the case can fail, then against an unmutated copy to prove
# it passes again — mutating a temp copy, never the committed file.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/worker-wait"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# --- fixtures: one DEAD dispatch (pid recorded, not alive) -------------------
cat > "$work/worker_list.json" <<'JSON'
{"result":{"workers":[{"dispatchId":"ctx_dead0001","dispatchStatus":"dispatched","agentTerminalHandle":"term_dead-pane"}],"page":{"hasMore":false}}}
JSON
cat > "$work/terminal_list.json" <<'JSON'
{"result":{"terminals":[{"handle":"term_dead-pane","lastOutputAt":1}]}}
JSON
cat > "$work/orca" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
  "orchestration worker-list") cat "$work/worker_list.json" ;;
  "terminal list")
    if printf '%s\n' "\$@" | grep -q -- '--json'; then cat "$work/terminal_list.json"
    else echo "term_dead-pane pane"; fi
    ;;
  "terminal read") echo "" ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/orca"
cat > "$work/ps" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$work/ps"
cat > "$work/ledger.jsonl" <<'EOF'
{"job_id": "ctx_dead0001", "worker_pid": "9999", "pane": "term_dead-pane"}
EOF

run_once() {
  PATH="$work:$PATH" HOME="$work/home" "$1" --once --json --run run_x --ledger "$work/ledger.jsonl" 2>&1
}

# --- Case 1: --once --json prints the table and exits 0, DEAD verdict shown -
out=$(run_once "$SCRIPT"); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q '"DEAD"'; then
  ok "once/json: exit 0, DEAD verdict for a recorded pid that is not alive"
else
  fail "once/json: expected exit 0 with a DEAD row, got exit $rc: $out"
fi

mutant="$work/worker-wait-mutant-dead"
sed 's/return "DEAD"/return "working"/' "$SCRIPT" > "$mutant"
chmod +x "$mutant"
mutant_out=$(run_once "$mutant"); mutant_rc=$?
if [ "$mutant_rc" -eq 0 ] && ! printf '%s' "$mutant_out" | grep -q '"DEAD"'; then
  ok "failability: dropping the DEAD return makes this case fail"
else
  fail "failability: DEAD mutant did not change the observed verdict"
fi
restored_out=$(run_once "$SCRIPT"); restored_rc=$?
if [ "$restored_rc" -eq 0 ] && printf '%s' "$restored_out" | grep -q '"DEAD"'; then
  ok "restored: unmutated script reports DEAD again"
else
  fail "restored: unmutated script should still report DEAD"
fi

# --- Case 2: a held lock refuses a second waiter with exit 2 ----------------
mkdir -p "$work/home/.mogui/worker-wait" "$work/alivebin"
echo "4242" > "$work/home/.mogui/worker-wait/run_lock_test.lock"
cat > "$work/alivebin/ps" <<'EOF'
#!/usr/bin/env bash
[ "$2" = 4242 ] && exit 0 || exit 1
EOF
chmod +x "$work/alivebin/ps"
# Empty accounting so a bypassed lock exits the loop after one pass instead of
# spinning: the point of this fixture is the lock's exit code, not the table.
cat > "$work/alivebin/orca" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") echo '{"result":{"workers":[],"page":{"hasMore":false}}}' ;;
  "terminal list")
    if printf '%s\n' "$@" | grep -q -- '--json'; then echo '{"result":{"terminals":[]}}'; fi ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/alivebin/orca"

lock_out=$(PATH="$work/alivebin:$PATH" HOME="$work/home" "$SCRIPT" --run run_lock_test 2>&1)
lock_rc=$?
if [ "$lock_rc" -eq 2 ] && [ -n "$lock_out" ]; then
  ok "lock held by a live pid: second waiter exits 2 with a one-line message"
else
  fail "lock held by a live pid: expected exit 2, got exit $lock_rc: $lock_out"
fi

mutant_lock="$work/worker-wait-mutant-lock"
sed 's/if existing and _pid_alive(existing):/if False:/' "$SCRIPT" > "$mutant_lock"
chmod +x "$mutant_lock"
mutant_lock_rc=$(PATH="$work/alivebin:$PATH" HOME="$work/home" timeout 5 "$mutant_lock" --run run_lock_test >/dev/null 2>&1; echo $?)
if [ "$mutant_lock_rc" -ne 2 ]; then
  ok "failability: dropping the lock-alive check no longer exits 2 (lock bypassed)"
else
  fail "failability: lock mutant did not change the exit code"
fi
# The bypassing mutant run above acquired the lock for real, overwriting the
# file with its own (since-exited) pid; re-seed it before checking restore.
echo "4242" > "$work/home/.mogui/worker-wait/run_lock_test.lock"
restored_lock_rc=$(PATH="$work/alivebin:$PATH" HOME="$work/home" "$SCRIPT" --run run_lock_test >/dev/null 2>&1; echo $?)
if [ "$restored_lock_rc" -eq 2 ]; then
  ok "restored: unmutated script still refuses the held lock with exit 2"
else
  fail "restored: unmutated script should still exit 2 on a held lock"
fi
rm -f "$work/home/.mogui/worker-wait/run_lock_test.lock"

[ "$FAILED" -eq 0 ] && { echo "worker-wait: all checks passed"; exit 0; }
echo "worker-wait: FAILED"
exit 1
