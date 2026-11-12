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

# worker-wait resolves `lib/orca_json.py` and `mogui_log.py` relative to its
# own file location (docs/runbooks/orca-json.md); every sed-mutated copy of
# the script below is written directly into $work, so stage both siblings
# there once, up front, instead of per mutant.
cp "$ROOT/scripts/mogui_log.py" "$work/mogui_log.py"
mkdir -p "$work/lib"
cp "$ROOT/scripts/lib/orca_json.py" "$work/lib/orca_json.py"

# --- fixtures: one DEAD dispatch (pid recorded, not alive) -------------------
cat > "$work/worker_list.json" <<'JSON'
{"ok":true,"result":{"workers":[{"dispatchId":"ctx_dead0001","dispatchStatus":"dispatched","agentTerminalHandle":"term_dead-pane"}],"page":{"hasMore":false}}}
JSON
cat > "$work/terminal_list.json" <<'JSON'
{"ok":true,"result":{"terminals":[{"handle":"term_dead-pane","lastOutputAt":1}]}}
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
# Requires the exact probe (-p 9999, the recorded pid) rather than exiting 1
# unconditionally: a regression that probed the wrong pid, dropped -p, or
# skipped the probe entirely would still read DEAD from a fixture that never
# checked what was actually asked.
cat > "$work/ps" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "-p" ] && [ "$2" = "9999" ] && exit 1 || exit 0
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
  "orchestration worker-list") echo '{"ok":true,"result":{"workers":[],"page":{"hasMore":false}}}' ;;
  "terminal list")
    if printf '%s\n' "$@" | grep -q -- '--json'; then echo '{"ok":true,"result":{"terminals":[]}}'; fi ;;
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
sed 's/if not existing or _pid_alive(existing) is not False:/if False:/' "$SCRIPT" > "$mutant_lock"
chmod +x "$mutant_lock"
if cmp -s "$SCRIPT" "$mutant_lock"; then
  fail "failability: lock-alive-check sed pattern did not match the script"
fi
# No timeout wrapper needed: the empty-worker-list fixture above makes the
# loop's own initial accounting pass exit before any check --wait call, on
# both the real script and this mutant, so a hang here would itself be a
# regression worth seeing rather than a case to guard against. Assert the
# exact bypassed-lock exit (0, from the empty accounting), not merely "not 2":
# a crash (1), a missing command (127), or a hypothetical timeout kill (124)
# would all satisfy "not 2" without proving the lock check was ever reached.
mutant_lock_rc=$(PATH="$work/alivebin:$PATH" HOME="$work/home" "$mutant_lock" --run run_lock_test >/dev/null 2>&1; echo $?)
if [ "$mutant_lock_rc" -eq 0 ]; then
  ok "failability: dropping the lock-alive check no longer exits 2 (lock bypassed)"
else
  fail "failability: lock mutant did not change the exit code (got $mutant_lock_rc, want 0)"
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

# --- Case 3: 1.4.246+ worker-list shape (outcome/terminal/nextCursor) -------
# reads the same DEAD verdict as Case 1's old-shape fixture, routed through
# lib/orca_json.py instead of a shape-specific reader here.
cat > "$work/worker_list_new.json" <<'JSON'
{"ok":true,"result":{"workers":[{"dispatchId":"ctx_dead0002","taskId":"task_dead0002","outcome":"in_progress","terminal":"term_dead-pane-2"}],"nextCursor":""}}
JSON
cat > "$work/terminal_list_new.json" <<'JSON'
{"ok":true,"result":{"terminals":[{"handle":"term_dead-pane-2","lastOutputAt":1}]}}
JSON
cat > "$work/orca-new-shape" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
  "orchestration worker-list") cat "$work/worker_list_new.json" ;;
  "terminal list")
    if printf '%s\n' "\$@" | grep -q -- '--json'; then cat "$work/terminal_list_new.json"
    else echo "term_dead-pane-2 pane"; fi
    ;;
  "terminal read") echo "" ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/orca-new-shape"
cat > "$work/ledger_new.jsonl" <<'EOF'
{"job_id": "ctx_dead0002", "worker_pid": "9999", "pane": "term_dead-pane-2"}
EOF

run_once_new_shape() {
  PATH="$work/new-shape-bin:$PATH" HOME="$work/home" "$1" --once --json --run run_x --ledger "$work/ledger_new.jsonl" 2>&1
}
mkdir -p "$work/new-shape-bin"
cp "$work/orca-new-shape" "$work/new-shape-bin/orca"
cp "$work/ps" "$work/new-shape-bin/ps"

out=$(run_once_new_shape "$SCRIPT"); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'ctx_dead0002' && printf '%s' "$out" | grep -q '"DEAD"'; then
  ok "new-shape worker-list (outcome/terminal/nextCursor): DEAD verdict read through lib/orca_json.py"
else
  fail "new-shape worker-list: expected a DEAD row for ctx_dead0002, got exit $rc: $out"
fi

# Failability: a worker-wait + lib/orca_json.py pair that reads only the old
# path must not see this dispatch at all (no `outcome` reader -> never
# "in_progress" -> never added to the dispatched rows -> no row, no DEAD).
mutant_dir="$work/mutant-old-path-only"
mkdir -p "$mutant_dir/lib"
cp "$ROOT/scripts/mogui_log.py" "$mutant_dir/mogui_log.py"
sed 's/raw_status = worker.get("outcome")/raw_status = None  # mutated: old path only/' \
  "$ROOT/scripts/lib/orca_json.py" > "$mutant_dir/lib/orca_json.py"
cp "$SCRIPT" "$mutant_dir/worker-wait"
chmod +x "$mutant_dir/worker-wait"
if cmp -s "$ROOT/scripts/lib/orca_json.py" "$mutant_dir/lib/orca_json.py"; then
  fail "failability: new-shape worker-list sed pattern did not match lib/orca_json.py"
fi
mutant_out=$(run_once_new_shape "$mutant_dir/worker-wait"); mutant_rc=$?
if [ "$mutant_rc" -eq 0 ] && ! printf '%s' "$mutant_out" | grep -q 'ctx_dead0002'; then
  ok "failability: old-path-only lib/orca_json.py drops the new-shape dispatch entirely"
else
  fail "failability: old-path-only mutant should have dropped ctx_dead0002, got exit $mutant_rc: $mutant_out"
fi

# --- Case 4: worker-list pagination reaches a target on page two ------------
# Both response shapes must carry page-one workers forward while requesting the
# cursor returned by that page. The fake orca rejects a missing or wrong cursor,
# so a loop that stops after page one cannot satisfy the assertions.
pagination_case() {
  local shape="$1" page1 page2 terminal_json orca_bin bin ledger calls out rc cursor
  page1="$work/worker_list_${shape}_page1.json"
  page2="$work/worker_list_${shape}_page2.json"
  terminal_json="$work/terminal_list_${shape}.json"
  orca_bin="$work/orca-${shape}"
  bin="$work/pagination-${shape}-bin"
  ledger="$work/ledger-${shape}.jsonl"
  calls="$work/pagination-${shape}.calls"

  if [ "$shape" = old ]; then
    printf '%s\n' '{"ok":true,"result":{"workers":[{"dispatchId":"ctx_page_old_1","dispatchStatus":"dispatched","agentTerminalHandle":"term_page_old_1"}],"page":{"hasMore":true,"nextCursor":"cursor-old-page-2"}}}' > "$page1"
    printf '%s\n' '{"ok":true,"result":{"workers":[{"dispatchId":"ctx_page_old_2","dispatchStatus":"dispatched","agentTerminalHandle":"term_page_old_2"}],"page":{"hasMore":false,"nextCursor":""}}}' > "$page2"
    cursor="cursor-old-page-2"
  else
    printf '%s\n' '{"ok":true,"result":{"workers":[{"dispatchId":"ctx_page_new_1","outcome":"in_progress","terminal":"term_page_new_1"}],"nextCursor":"cursor-new-page-2"}}' > "$page1"
    printf '%s\n' '{"ok":true,"result":{"workers":[{"dispatchId":"ctx_page_new_2","outcome":"in_progress","terminal":"term_page_new_2"}],"nextCursor":""}}' > "$page2"
    cursor="cursor-new-page-2"
  fi
  printf '%s\n' "{\"ok\":true,\"result\":{\"terminals\":[{\"handle\":\"term_page_${shape}_1\",\"lastOutputAt\":1},{\"handle\":\"term_page_${shape}_2\",\"lastOutputAt\":1}]}}" > "$terminal_json"
  printf '%s\n' \
    "{\"job_id\": \"ctx_page_${shape}_1\", \"worker_pid\": \"9999\", \"pane\": \"term_page_${shape}_1\"}" \
    "{\"job_id\": \"ctx_page_${shape}_2\", \"worker_pid\": \"9999\", \"pane\": \"term_page_${shape}_2\"}" > "$ledger"
  : > "$calls"
  cat > "$orca_bin" <<EOF
#!/usr/bin/env bash
printf '%s\\n' "\$*" >> "$calls"
cursor=""
previous=""
for arg in "\$@"; do
  if [ "\$previous" = "--cursor" ]; then cursor="\$arg"; fi
  previous="\$arg"
done
case "\$1 \$2" in
  "orchestration worker-list")
    case "\$cursor" in
      "") cat "$page1" ;;
      "$cursor") cat "$page2" ;;
      *) exit 1 ;;
    esac
    ;;
  "terminal list") cat "$terminal_json" ;;
  "terminal read") echo "" ;;
  *) echo "{}" ;;
esac
EOF
  chmod +x "$orca_bin"
  mkdir -p "$bin"
  cp "$orca_bin" "$bin/orca"
  cp "$work/ps" "$bin/ps"

  out=$(PATH="$bin:$PATH" HOME="$work/home" "$SCRIPT" --once --json --run run_x --ledger "$ledger" 2>&1)
  rc=$?
  if [ "$rc" -eq 0 ] \
    && printf '%s' "$out" | grep -q "ctx_page_${shape}_1" \
    && printf '%s' "$out" | grep -q "ctx_page_${shape}_2" \
    && grep -q -- "--cursor $cursor" "$calls"; then
    ok "pagination $shape shape: page one and page two are accounted for"
  else
    fail "pagination $shape shape: expected both pages and --cursor $cursor, got exit $rc: $out"
  fi
}

pagination_case old
pagination_case new

pagination_mutant="$work/worker-wait-mutant-page-one"
mkdir -p "$work/page-mutant/lib"
sed 's/if not cursor:/if True:  # mutated: stop after page one/' "$SCRIPT" > "$pagination_mutant"
cp "$ROOT/scripts/mogui_log.py" "$work/page-mutant/mogui_log.py"
cp "$ROOT/scripts/lib/orca_json.py" "$work/page-mutant/lib/orca_json.py"
chmod +x "$pagination_mutant"
if cmp -s "$SCRIPT" "$pagination_mutant"; then
  fail "failability: page-one pagination sed pattern did not match the script"
fi
mutant_out=$(PATH="$work/pagination-old-bin:$PATH" HOME="$work/home" \
  "$pagination_mutant" --once --json --run run_x --ledger "$work/ledger-old.jsonl" 2>&1)
mutant_rc=$?
if [ "$mutant_rc" -eq 0 ] && ! printf '%s' "$mutant_out" | grep -q 'ctx_page_old_2'; then
  ok "failability: page-one mutant drops the page-two dispatch (mutant run: $mutant_out)"
else
  fail "failability: page-one mutant unexpectedly accounted for page two, got exit $mutant_rc: $mutant_out"
fi

# --- Case 4: `check --wait` with no deliveryId (1.4.246+ dropped it; a -------
# consuming check marks the batch handled server-side and `--ack` is a
# no-op) must not print the old "no deliveryId to ack" warning, and must
# still carry the prior ack forward unchanged (an old-shape ack still
# pending behind this heartbeat must not be silenced).
check_no_delivery_id() {
  # $1: path to a worker-wait to test (real script or a mutant copy).
  python3 - "$1" <<'PYEOF'
import importlib.machinery
import importlib.util
import io
import sys
from contextlib import redirect_stderr
from unittest import mock

script_path = sys.argv[1]
loader = importlib.machinery.SourceFileLoader("worker_wait_under_test", script_path)
spec = importlib.util.spec_from_loader("worker_wait_under_test", loader)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


heartbeat_no_delivery = '{"ok":true,"result":{"messages":[{"type":"heartbeat"}]}}'
with mock.patch.object(mod.subprocess, "run", return_value=FakeProc(heartbeat_no_delivery)):
    buf = io.StringIO()
    with redirect_stderr(buf):
        batch, ack = mod._wait_for_message("run_x", "stale_ack")
stderr_out = buf.getvalue()
passed = batch is None and ack == "stale_ack" and "no deliveryId to ack" not in stderr_out
print("PASS" if passed else f"FAIL batch={batch!r} ack={ack!r} stderr={stderr_out!r}")
PYEOF
}

result=$(check_no_delivery_id "$SCRIPT")
if [ "$result" = "PASS" ]; then
  ok "check --wait with no deliveryId: treated as handled, no stale-ack warning"
else
  fail "check --wait with no deliveryId: $result"
fi

mutant_ack="$work/worker-wait-mutant-ack-warn"
python3 - "$SCRIPT" "$mutant_ack" <<'PYEOF'
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = open(src_path, encoding="utf-8").read()
anchor = (
    "            # heartbeat must not be silenced.\n"
    "            return None, ack\n"
)
replacement = (
    "            # heartbeat must not be silenced.\n"
    '            print("worker-wait: heartbeat batch had no deliveryId to ack; '
    'treating as quiet", file=sys.stderr)\n'
    "            return None, ack\n"
)
if anchor not in src:
    print("mutation anchor not found", file=sys.stderr)
    sys.exit(1)
with open(dst_path, "w", encoding="utf-8") as f:
    f.write(src.replace(anchor, replacement, 1))
PYEOF
if [ ! -s "$mutant_ack" ] || cmp -s "$SCRIPT" "$mutant_ack"; then
  fail "failability: ack-warning mutation anchor did not match the script"
fi
chmod +x "$mutant_ack"
mutant_result=$(check_no_delivery_id "$mutant_ack")
if [ "$mutant_result" != "PASS" ]; then
  ok "failability: reintroducing the old stale-ack warning fails this case ($mutant_result)"
else
  fail "failability: ack-warning mutant did not change the observed behavior"
fi

# --- Case 5: a worker-list result with no `workers` key is a malformed-list
# error, not a quiet "nothing left" (issue #219: `{"result":{}}` must not be
# read as an empty run).
cat > "$work/orca-no-workers-key" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") echo '{"ok":true,"result":{}}' ;;
  "terminal list")
    if printf '%s\n' "$@" | grep -q -- '--json'; then echo '{"ok":true,"result":{"terminals":[]}}'; fi ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/orca-no-workers-key"
mkdir -p "$work/no-workers-key-bin"
cp "$work/orca-no-workers-key" "$work/no-workers-key-bin/orca"
cp "$work/ps" "$work/no-workers-key-bin/ps"
printf '{"job_id": "ctx_none", "worker_pid": "9999", "pane": "term_none"}\n' > "$work/ledger_no_workers_key.jsonl"

no_workers_out=$(PATH="$work/no-workers-key-bin:$PATH" HOME="$work/home" "$SCRIPT" --once --json --run run_x --ledger "$work/ledger_no_workers_key.jsonl" 2>&1)
no_workers_rc=$?
if [ "$no_workers_rc" -ne 0 ] && printf '%s' "$no_workers_out" | grep -q "no 'workers' key"; then
  ok "malformed worker-list result ({\"result\":{}}): exits non-zero naming the missing workers key"
else
  fail "malformed worker-list result: expected a non-zero exit naming the missing workers key, got exit $no_workers_rc: $no_workers_out"
fi
if printf '%s' "$no_workers_out" | grep -qi "nothing left"; then
  fail "malformed worker-list result: must not be reported as nothing left to do"
fi

mutant_list="$work/worker-wait-mutant-empty-list"
sed "s/if not isinstance(result, dict) or not isinstance(result.get(\"workers\"), list):/if False:/" "$SCRIPT" > "$mutant_list"
if cmp -s "$SCRIPT" "$mutant_list"; then
  fail "failability: malformed-list sed pattern did not match the script"
fi
chmod +x "$mutant_list"
mutant_list_out=$(PATH="$work/no-workers-key-bin:$PATH" HOME="$work/home" "$mutant_list" --once --json --run run_x --ledger "$work/ledger_no_workers_key.jsonl" 2>&1)
mutant_list_rc=$?
if [ "$mutant_list_rc" -eq 0 ]; then
  ok "failability: dropping the malformed-list check reports exit 0 (false empty run) again"
else
  fail "failability: malformed-list mutant did not change the exit code (got $mutant_list_rc, want 0)"
fi
restored_list_out=$(PATH="$work/no-workers-key-bin:$PATH" HOME="$work/home" "$SCRIPT" --once --json --run run_x --ledger "$work/ledger_no_workers_key.jsonl" 2>&1)
restored_list_rc=$?
if [ "$restored_list_rc" -ne 0 ] && printf '%s' "$restored_list_out" | grep -q "no 'workers' key"; then
  ok "restored: unmutated script still raises on a missing workers key"
else
  fail "restored: unmutated script should still exit non-zero naming the missing workers key"
fi

# --- Case 6: a `workers` key present but null (not a list) is the same
# malformed-list error, not an empty run (cubic review on PR #239).
cat > "$work/orca-null-workers" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") echo '{"ok":true,"result":{"workers":null}}' ;;
  "terminal list")
    if printf '%s\n' "$@" | grep -q -- '--json'; then echo '{"ok":true,"result":{"terminals":[]}}'; fi ;;
  *) echo "{}" ;;
esac
EOF
chmod +x "$work/orca-null-workers"
mkdir -p "$work/null-workers-bin"
cp "$work/orca-null-workers" "$work/null-workers-bin/orca"
cp "$work/ps" "$work/null-workers-bin/ps"
printf '{"job_id": "ctx_none2", "worker_pid": "9999", "pane": "term_none2"}\n' > "$work/ledger_null_workers.jsonl"

null_workers_out=$(PATH="$work/null-workers-bin:$PATH" HOME="$work/home" "$SCRIPT" --once --json --run run_x --ledger "$work/ledger_null_workers.jsonl" 2>&1)
null_workers_rc=$?
if [ "$null_workers_rc" -ne 0 ] && printf '%s' "$null_workers_out" | grep -q "no 'workers' key"; then
  ok "malformed worker-list result ({\"workers\":null}): exits non-zero naming the malformed workers value"
else
  fail "malformed worker-list result ({\"workers\":null}): expected a non-zero exit naming the malformed workers value, got exit $null_workers_rc: $null_workers_out"
fi
if printf '%s' "$null_workers_out" | grep -qi "nothing left"; then
  fail "malformed worker-list result ({\"workers\":null}): must not be reported as nothing left to do"
fi

mutant_null="$work/worker-wait-mutant-null-list"
sed "s/if not isinstance(result, dict) or not isinstance(result.get(\"workers\"), list):/if not isinstance(result, dict) or \"workers\" not in result:/" "$SCRIPT" > "$mutant_null"
if cmp -s "$SCRIPT" "$mutant_null"; then
  fail "failability: null-workers sed pattern did not match the script"
fi
chmod +x "$mutant_null"
mutant_null_out=$(PATH="$work/null-workers-bin:$PATH" HOME="$work/home" "$mutant_null" --once --json --run run_x --ledger "$work/ledger_null_workers.jsonl" 2>&1)
mutant_null_rc=$?
if [ "$mutant_null_rc" -eq 0 ]; then
  ok "failability: dropping the list-type check reports exit 0 again on {\"workers\":null}"
else
  fail "failability: null-workers mutant did not change the exit code (got $mutant_null_rc, want 0)"
fi
restored_null_out=$(PATH="$work/null-workers-bin:$PATH" HOME="$work/home" "$SCRIPT" --once --json --run run_x --ledger "$work/ledger_null_workers.jsonl" 2>&1)
restored_null_rc=$?
if [ "$restored_null_rc" -ne 0 ] && printf '%s' "$restored_null_out" | grep -q "no 'workers' key"; then
  ok "restored: unmutated script still raises on {\"workers\":null}"
else
  fail "restored: unmutated script should still exit non-zero on {\"workers\":null}"
fi

[ "$FAILED" -eq 0 ] && { echo "worker-wait: all checks passed"; exit 0; }
echo "worker-wait: FAILED"
exit 1
