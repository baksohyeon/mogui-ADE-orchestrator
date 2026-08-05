#!/bin/bash
# Regression test for the seat check in harness-selfcheck.sh.
#
# Cases 2 and 3 are the ones that matter: both were reported as
# "matches recorded" by the path-equality check that shipped on 2026-08-04,
# and both are the exact state a succession produces. Orca mints a new
# folderWorkspace record for the seat folder each time it is opened, so the
# successor lands in a clone that shares the recorded path.
#
# The seat block runs first in harness-selfcheck.sh, so the later checks
# (skills, hooks, tracker) do not affect the line under test. Assertions are
# on the Seat: line, not on the script's overall exit code, which also carries
# those later checks.
set -u

cd "$(dirname "$0")/.."

# Overridable so the previous, path-equality-only implementation can be run
# against the same cases to show which ones it lets through.
SELFCHECK_BIN="${SELFCHECK_BIN:-./scripts/harness-selfcheck.sh}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

SEAT_PATH="{{WORKSPACE_ROOT}}"
SEAT_WS="folder:aaaaaaaa-0000-0000-0000-000000000001"
CLONE_WS="folder:bbbbbbbb-0000-0000-0000-000000000002"

write_role_state() {
  # $1 = seat path line value, $2 = workspace id line value ("" to omit)
  {
    echo "# Role State"
    echo ""
    echo "Master seat (absolute path): \`$1\`"
    [ -n "$2" ] && echo "Master seat (workspace id): \`$2\`"
  } > "$TMP/role-state.md"
}

write_orca_data() {
  # each arg: id|path|archived
  python3 - "$TMP/orca-data.json" "$@" <<'EOF'
import json, sys
out, rows = sys.argv[1], sys.argv[2:]
ws = []
for r in rows:
    wid, path, archived = r.split("|")
    ws.append({"id": wid, "folderPath": path, "isArchived": archived == "1"})
json.dump({"folderWorkspaces": ws}, open(out, "w"))
EOF
}

pass=0
fail=0

run_seat() {
  ROLE_STATE_PATH="$TMP/role-state.md" \
  ORCA_DATA_PATH="$TMP/orca-data.json" \
  ORCA_WORKSPACE_ID="$1" \
  "$SELFCHECK_BIN" 2>/dev/null | grep '^Seat:'
}

# Some cases assert on the second Seat: line (the NOTICE), not the first.
check_line2() {
  local name="$1" expect="$2" line
  line=$(run_seat "$3" | sed -n 2p)
  if printf '%s' "$line" | grep -qF "$expect"; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect"
    echo "       actual line:        $line"
    fail=$((fail + 1))
  fi
}

check() {
  # $1 = case name, $2 = expected substring, $3 = ORCA_WORKSPACE_ID value
  local name="$1" expect="$2" wsid="$3" line
  line=$(ROLE_STATE_PATH="$TMP/role-state.md" \
         ORCA_DATA_PATH="$TMP/orca-data.json" \
         ORCA_WORKSPACE_ID="$wsid" \
         "$SELFCHECK_BIN" 2>/dev/null | grep -m1 '^Seat:')
  if printf '%s' "$line" | grep -qF "$expect"; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect"
    echo "       actual line:        $line"
    fail=$((fail + 1))
  fi
}

# 1. One live workspace owns the seat path, and it is the one recorded.
write_role_state "$SEAT_PATH" "$SEAT_WS"
write_orca_data "${SEAT_WS#folder:}|$SEAT_PATH|0"
check "sole workspace on the recorded path passes" "sole workspace" "$SEAT_WS"

# 2. Seated in the recorded workspace, but a clone of the path exists.
#    Nothing has gone wrong yet; the next succession is what lands in the clone,
#    so the ambiguity has to block now, while there is someone to fix it.
write_orca_data "${SEAT_WS#folder:}|$SEAT_PATH|0" "${CLONE_WS#folder:}|$SEAT_PATH|0"
check "clone sharing the seat path blocks" "AMBIGUOUS" "$SEAT_WS"

# 3. Seated in the clone instead. Same folder, different workspace: the 08-04
#    recurrence. Path equality alone calls this correct.
check "seat in a path-identical clone blocks" "AMBIGUOUS" "$CLONE_WS"

# 4. An archived clone is not a live owner and must not block.
write_orca_data "${SEAT_WS#folder:}|$SEAT_PATH|0" "${CLONE_WS#folder:}|$SEAT_PATH|1"
check "archived clone is ignored" "sole workspace" "$SEAT_WS"

# 5. Unmeasurable seat is a failure, never a soft pass.
write_orca_data "${SEAT_WS#folder:}|$SEAT_PATH|0"
check "unset workspace id is undecided" "undecided" ""

# 6. A workspace id absent from the registry cannot be placed. This is the
#    literal state this session booted in (global-floating-terminal), and the
#    previous check let it through with no exit code.
check "unresolvable workspace id is undecided" "undecided" "global-floating-terminal"

# 7. Recorded id resolves to a different folder than the recorded path.
write_orca_data "${SEAT_WS#folder:}|/tmp/mogui-elsewhere|0"
check "id resolving to the wrong path is MISSEATED" "MISSEATED" "$SEAT_WS"

# 8. The id rotates when a pane is adopted, so a successor legitimately arrives
#    with a new one. That is a record to correct, not a seat to reject.
write_role_state "$SEAT_PATH" "$SEAT_WS"
write_orca_data "${CLONE_WS#folder:}|$SEAT_PATH|0"
check "rotated id on a unique path is a notice, not a block" "sole workspace" "$CLONE_WS"
check_line2 "rotated id asks for the record to be updated" "NOTICE" "$CLONE_WS"

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
