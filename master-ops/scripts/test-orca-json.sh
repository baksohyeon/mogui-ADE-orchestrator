#!/usr/bin/env bash
# Regression test for scripts/lib/orca_json.py: one fixture per
# shape (old and 1.4.246+) per function, plus parse_envelope's trailing-human-
# line and multi-document cases. Each new-shape case also runs against a
# mutant copy of the module that reads only the old path, to prove the case
# can fail (never mutating the committed file, a temp copy only).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODULE="$ROOT/scripts/lib/orca_json.py"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

run_checks() {
  # $1: path to an orca_json.py to test (real module or a mutant copy).
  # Prints one "<name>:<shape>:PASS" or "<name>:<shape>:FAIL ..." line per
  # check; never raises on its own, so a mutant that breaks an import still
  # yields readable FAIL lines instead of an empty run.
  ORCA_JSON_MODULE="$1" python3 - <<'PYEOF'
import importlib.util
import os

module_path = os.environ["ORCA_JSON_MODULE"]
spec = importlib.util.spec_from_file_location("orca_json_under_test", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def check(name, shape, got, want):
    status = "PASS" if got == want else f"FAIL got={got!r} want={want!r}"
    print(f"{name}:{shape}:{status}")


check("task_id", "old", m.task_id({"task": {"id": "task_old1"}}), "task_old1")
check("task_id", "new", m.task_id({"taskId": "task_new1", "status": "ready"}), "task_new1")
check("task_id", "absent", m.task_id({}), None)

check("run_id", "old", m.run_id({"run": {"id": "run_old1"}}), "run_old1")
check("run_id", "new", m.run_id({"runId": "run_new1"}), "run_new1")
check("run_id", "new-null", m.run_id({"runId": None}), None)

check("terminal_handle", "old", m.terminal_handle({"terminal": {"handle": "term_old1"}}), "term_old1")
check(
    "terminal_handle",
    "new-terminalHandle",
    m.terminal_handle({"terminalHandle": "term_new1"}),
    "term_new1",
)
check("terminal_handle", "new-handle", m.terminal_handle({"handle": "term_new2"}), "term_new2")

check("dispatch_id", "old", m.dispatch_id({"dispatch": {"id": "ctx_old1"}}), "ctx_old1")
check("dispatch_id", "new", m.dispatch_id({"dispatchId": "ctx_new1"}), "ctx_new1")

check("dispatch_status", "old", m.dispatch_status({"dispatch": {"status": "running"}}), "running")
check("dispatch_status", "new", m.dispatch_status({"status": "running"}), "running")

check("delivery_id", "old", m.delivery_id({"deliveryId": "dlv1"}), "dlv1")
check("delivery_id", "new-absent", m.delivery_id({"messages": []}), None)

check("messages", "present", m.messages({"messages": [{"type": "heartbeat"}]}), [{"type": "heartbeat"}])
check("messages", "absent", m.messages({}), [])

old_workers = m.workers(
    {
        "workers": [
            {
                "dispatchId": "ctx_a",
                "taskId": "task_a",
                "dispatchStatus": "dispatched",
                "agentTerminalHandle": "term_a",
            },
            {
                "dispatchId": "ctx_b",
                "taskId": "task_b",
                "dispatchStatus": "completed",
                "agentTerminalHandle": "term_b",
            },
        ]
    }
)
check(
    "workers",
    "old",
    old_workers,
    [
        {"dispatch_id": "ctx_a", "task_id": "task_a", "status": "in_progress", "terminal": "term_a"},
        {"dispatch_id": "ctx_b", "task_id": "task_b", "status": "completed", "terminal": "term_b"},
    ],
)

new_workers = m.workers(
    {
        "workers": [
            {"dispatchId": "ctx_c", "taskId": "task_c", "outcome": "in_progress", "terminal": "term_c"},
            {"dispatchId": "ctx_d", "taskId": "task_d", "outcome": "succeeded", "terminal": "term_d"},
        ]
    }
)
check(
    "workers",
    "new",
    new_workers,
    [
        {"dispatch_id": "ctx_c", "task_id": "task_c", "status": "in_progress", "terminal": "term_c"},
        {"dispatch_id": "ctx_d", "task_id": "task_d", "status": "succeeded", "terminal": "term_d"},
    ],
)

check("next_cursor", "old-more", m.next_cursor({"page": {"hasMore": True, "nextCursor": "abc"}}), "abc")
check("next_cursor", "old-last", m.next_cursor({"page": {"hasMore": False, "nextCursor": "abc"}}), None)
check("next_cursor", "new-more", m.next_cursor({"nextCursor": "xyz"}), "xyz")
check("next_cursor", "new-last", m.next_cursor({"nextCursor": ""}), None)

got = m.parse_envelope('{"ok":true,"result":{"a":1}}\n')
check("parse_envelope", "clean", got, (True, {"a": 1}, None))

got = m.parse_envelope('{"ok":false,"error":{"code":"x","message":"y"}}\nerror: x: y\n')
check("parse_envelope", "trailing-human-line", got, (False, None, {"code": "x", "message": "y"}))

got = m.parse_envelope('{"ok":true,"result":{"a":1}}\n{"ok":true,"result":{"b":2}}\n')
check("parse_envelope", "two-documents-last-wins", got, (True, {"b": 2}, None))
PYEOF
}

out=$(run_checks "$MODULE")
while IFS= read -r line; do
  [ -z "$line" ] && continue
  case "$line" in
    *:PASS) ok "$line" ;;
    *) fail "$line" ;;
  esac
done <<< "$out"

# --- failability: a mutant that reads only the old path must fail every ---
# --- new-shape (and new-only) case above. --------------------------------
mutant="$work/orca_json_old_path_only.py"
python3 - "$MODULE" "$mutant" <<'PYEOF'
import re
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = open(src_path, encoding="utf-8").read()

# Drop every "new path second" fallback: the last `return`/final expression
# in each reader function that falls through to the 1.4.246+ key. Matches the
# exact lines this module's docstring describes as the new-path reads.
mutations = [
    ('    return result.get("taskId")\n', '    return None\n'),
    ('    return result.get("runId")\n', '    return None\n'),
    (
        '    return result.get("terminalHandle") or result.get("handle")\n',
        "    return None\n",
    ),
    ('    return result.get("dispatchId")\n', '    return None\n'),
    ('    return result.get("status")\n', '    return None\n'),
    (
        'raw_status = worker.get("outcome")\n',
        'raw_status = None  # mutated: old path only\n',
    ),
    (
        'return result.get("nextCursor") or None\n',
        'return None  # mutated: old path only\n',
    ),
]
mutated = src
for old, new in mutations:
    if old not in mutated:
        print(f"mutation anchor not found: {old!r}", file=sys.stderr)
        sys.exit(1)
    mutated = mutated.replace(old, new, 1)

if mutated == src:
    print("mutation produced no change", file=sys.stderr)
    sys.exit(1)

with open(dst_path, "w", encoding="utf-8") as f:
    f.write(mutated)
PYEOF
if [ ! -s "$mutant" ]; then
  fail "could not build the old-path-only mutant; see stderr above"
else
  mutant_out=$(run_checks "$mutant")
  while IFS= read -r line; do
    case "$line" in
      task_id:new:PASS|run_id:new:PASS|terminal_handle:new-terminalHandle:PASS|terminal_handle:new-handle:PASS|dispatch_id:new:PASS|dispatch_status:new:PASS|workers:new:PASS|next_cursor:new-more:PASS)
        fail "failability: old-path-only mutant should not pass $line"
        ;;
    esac
  done <<< "$mutant_out"
  ok "failability: old-path-only mutant breaks every new-shape case (see FAIL lines above if not)"
fi

[ "$FAILED" -eq 0 ] && { echo "orca-json: all checks passed"; exit 0; }
echo "orca-json: FAILED"
exit 1
