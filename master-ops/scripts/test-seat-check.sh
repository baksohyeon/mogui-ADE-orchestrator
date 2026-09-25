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

# Exercise the candidate-line parser directly without running the full self-check.
eval "$(sed -n '/^tracker_candidate_from_line()/,/^}/p' "$SELFCHECK_BIN")"
colon_path="$TMP/ops:colon/.beads"
mkdir -p "$colon_path"
if [ "$(tracker_candidate_from_line "$colon_path")" = "$colon_path" ]; then
  echo "ok   — colon-bearing raw path is preserved"
  pass=$((pass + 1))
else
  echo "FAIL — colon-bearing raw path is preserved"
  fail=$((fail + 1))
fi
if [ "$(tracker_candidate_from_line "Tracker label: $colon_path")" = "$colon_path" ]; then
  echo "ok   — labeled tracker path is extracted"
  pass=$((pass + 1))
else
  echo "FAIL — labeled tracker path is extracted"
  fail=$((fail + 1))
fi

# Ported from the seat's check_template cases (owner direction 2026-09-23).
# Exercise template_adoption_probe directly, like tracker_candidate_from_line
# above, instead of running the whole self-check: the later Skills/Hooks/Card
# checks abort this script early in a bare template checkout (no real
# WORKSPACE_ROOT), which would make the aggregate exit code meaningless for
# asserting this probe's own exit-code contribution.
eval "$(sed -n '/^template_adoption_probe()/,/^}/p' "$SELFCHECK_BIN")"

check_template() {
  # $1 = case name, $2 = expected substring, $3 = expected exit code,
  # $4 = TEMPLATE_MANIFEST_FILE, $5 = TEMPLATE_ADOPTION_LEDGER
  local name="$1" expect="$2" expect_rc="$3" manifest="$4" ledger="$5" line rc
  line=$(TEMPLATE_MANIFEST_FILE="$manifest" TEMPLATE_ADOPTION_LEDGER="$ledger" template_adoption_probe)
  rc=$?
  if printf '%s' "$line" | grep -qF "$expect" && [ "$rc" -eq "$expect_rc" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect (exit $expect_rc)"
    echo "       actual line:        $line (exit $rc)"
    fail=$((fail + 1))
  fi
}

# Generated-mutant guard: a no-op sed must not pass this failability check silently.
template_mutant_check() {
  # $1 = case label, $2 = sed pattern to break the verdict, $3 = manifest fixture,
  # $4 = ledger fixture, $5 = the untouched verdict substring the mutant must lose.
  local label="$1" pattern="$2" manifest="$3" ledger="$4" original="$5"
  local mut="$TMP/harness-selfcheck.mutant.$$.sh" mline
  sed "$pattern" "$SELFCHECK_BIN" > "$mut"
  if [ ! -f "$mut" ] || cmp -s "$SELFCHECK_BIN" "$mut"; then
    echo "FAIL: mutant not generated" >&2
    exit 1
  fi
  mline=$(
    eval "$(sed -n '/^template_adoption_probe()/,/^}/p' "$mut")"
    TEMPLATE_MANIFEST_FILE="$manifest" TEMPLATE_ADOPTION_LEDGER="$ledger" template_adoption_probe
  )
  rm -f "$mut"
  case "$mline" in
    *"$original"*)
      echo "FAIL — failability: $label mutant still reported the original verdict"
      fail=$((fail + 1))
      ;;
    *)
      echo "ok   — failability: $label mutant verdict differs, so the case would fail"
      pass=$((pass + 1))
      ;;
  esac
}

TEMPLATE_MANIFEST_ABSENT="$TMP/no-manifest.json"
TEMPLATE_MANIFEST_STAMPED="$TMP/manifest-stamped.json"
cat > "$TEMPLATE_MANIFEST_STAMPED" <<'EOF'
{"template_version": "v0.4.1", "files": ["a"]}
EOF
TEMPLATE_LEDGER_MISSING="$TMP/no-ledger.md"
TEMPLATE_LEDGER_PRESENT="$TMP/template-adoption-2026-08-08.md"
echo "# Adoption ledger" > "$TEMPLATE_LEDGER_PRESENT"

# T1. Manifest absent: non-zero exit.
check_template "manifest absent is reported" \
  "Template: absent (MANIFEST.json missing)" 1 \
  "$TEMPLATE_MANIFEST_ABSENT" "$TEMPLATE_LEDGER_MISSING"
template_mutant_check "manifest-absent" \
  's/absent (MANIFEST.json missing)/MUTANT-VERDICT/' \
  "$TEMPLATE_MANIFEST_ABSENT" "$TEMPLATE_LEDGER_MISSING" \
  "absent (MANIFEST.json missing)"

# T2. Stamped manifest, adoption ledger missing: non-zero exit.
check_template "stamped manifest with missing ledger is reported" \
  "Template: v0.4.1 stamped, adoption ledger missing" 1 \
  "$TEMPLATE_MANIFEST_STAMPED" "$TEMPLATE_LEDGER_MISSING"
template_mutant_check "ledger-missing" \
  's/stamped, adoption ledger missing/MUTANT-VERDICT/' \
  "$TEMPLATE_MANIFEST_STAMPED" "$TEMPLATE_LEDGER_MISSING" \
  "stamped, adoption ledger missing"

# T3. Stamped manifest, adoption ledger present: zero exit.
check_template "stamped manifest with ledger present is reported" \
  "Template: v0.4.1 stamped, adoption incomplete" 0 \
  "$TEMPLATE_MANIFEST_STAMPED" "$TEMPLATE_LEDGER_PRESENT"
template_mutant_check "ledger-present" \
  's/stamped, adoption incomplete/MUTANT-VERDICT/' \
  "$TEMPLATE_MANIFEST_STAMPED" "$TEMPLATE_LEDGER_PRESENT" \
  "stamped, adoption incomplete"

# Ported from the seat's Twins: probe (owner instruction 2026-08-06, seat lines
# 282-311), now that harness-selfcheck.sh carries twins_probe(). Exercised the
# same way as template_adoption_probe above: directly, with CARD_* and OPS_DIR
# overridden, since running the whole script aborts at Hooks: in a bare
# template checkout (no real WORKSPACE_ROOT).
eval "$(sed -n '/^twins_probe()/,/^}/p' "$SELFCHECK_BIN")"

check_twins() {
  # $1 = case name, $2 = expected substring, $3 = expected exit code,
  # $4 = OPS_DIR, $5 = CARD_CLAUDE_CANONICAL, $6 = CARD_AGENTS_CANONICAL,
  # $7 = CARD_AGENTS_DEPLOYED
  local name="$1" expect="$2" expect_rc="$3" ops_dir="$4" claude_c="$5" agents_c="$6" agents_d="$7" out rc
  out=$(OPS_DIR="$ops_dir" CARD_CLAUDE_CANONICAL="$claude_c" CARD_AGENTS_CANONICAL="$agents_c" CARD_AGENTS_DEPLOYED="$agents_d" twins_probe)
  rc=$?
  if printf '%s' "$out" | grep -qF "$expect" && [ "$rc" -eq "$expect_rc" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect (exit $expect_rc)"
    echo "       actual output:      $out (exit $rc)"
    fail=$((fail + 1))
  fi
}

# Generated-mutant guard: a no-op sed must not pass this failability check silently.
twins_mutant_check() {
  # $1 = case label, $2 = sed pattern to break the verdict, $3 = OPS_DIR,
  # $4 = CARD_CLAUDE_CANONICAL, $5 = CARD_AGENTS_CANONICAL, $6 = CARD_AGENTS_DEPLOYED,
  # $7 = the untouched verdict substring the mutant must lose.
  local label="$1" pattern="$2" ops_dir="$3" claude_c="$4" agents_c="$5" agents_d="$6" original="$7"
  local mut="$TMP/harness-selfcheck.mutant.$$.sh" mline
  sed "$pattern" "$SELFCHECK_BIN" > "$mut"
  if [ ! -f "$mut" ] || cmp -s "$SELFCHECK_BIN" "$mut"; then
    echo "FAIL: mutant not generated" >&2
    exit 1
  fi
  mline=$(
    eval "$(sed -n '/^twins_probe()/,/^}/p' "$mut")"
    OPS_DIR="$ops_dir" CARD_CLAUDE_CANONICAL="$claude_c" CARD_AGENTS_CANONICAL="$agents_c" CARD_AGENTS_DEPLOYED="$agents_d" twins_probe
  )
  rm -f "$mut"
  case "$mline" in
    *"$original"*)
      echo "FAIL — failability: $label mutant still reported the original verdict"
      fail=$((fail + 1))
      ;;
    *)
      echo "ok   — failability: $label mutant verdict differs, so the case would fail"
      pass=$((pass + 1))
      ;;
  esac
}

TWINS_CARD_DIR="$TMP/twins-card"
TWINS_OPS_DIR="$TMP/twins-ops"
mkdir -p "$TWINS_CARD_DIR" "$TWINS_OPS_DIR"
echo "workspace card content" > "$TWINS_CARD_DIR/CLAUDE.md"
cp "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md"
TWINS_DEPLOYED_AGENTS="$TMP/twins-deployed-AGENTS.md"
cp "$TWINS_CARD_DIR/AGENTS.md" "$TWINS_DEPLOYED_AGENTS"
cp "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_OPS_DIR/CLAUDE.md"
cp "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_OPS_DIR/AGENTS.md"
echo "diverged" > "$TWINS_CARD_DIR/AGENTS.md.diverged"

# W1. Canonical pair diverged: non-zero exit.
check_twins "canonical pair diverged is reported" \
  "Twins: canonical pair DIVERGED" 1 \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md.diverged" "$TWINS_DEPLOYED_AGENTS"
twins_mutant_check "canonical-diverged" \
  's/canonical pair DIVERGED/MUTANT-VERDICT/' \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md.diverged" "$TWINS_DEPLOYED_AGENTS" \
  "canonical pair DIVERGED"

# W2. Deployed copy missing: non-zero exit.
check_twins "deployed AGENTS.md missing is reported" \
  "Twins: AGENTS.md not deployed to the workspace root" 1 \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md" "$TMP/twins-nonexistent-AGENTS.md"
twins_mutant_check "deployed-missing" \
  's/AGENTS.md not deployed to the workspace root/MUTANT-VERDICT/' \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md" "$TMP/twins-nonexistent-AGENTS.md" \
  "AGENTS.md not deployed to the workspace root"

# W3. Canonical, deployed, and ops pairs all identical: zero exit.
check_twins "all pairs identical passes" \
  "Twins: canonical, deployed, and ops entry pairs all byte-identical" 0 \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md" "$TWINS_DEPLOYED_AGENTS"
twins_mutant_check "all-identical" \
  's/canonical, deployed, and ops entry pairs all byte-identical/MUTANT-VERDICT/' \
  "$TWINS_OPS_DIR" "$TWINS_CARD_DIR/CLAUDE.md" "$TWINS_CARD_DIR/AGENTS.md" "$TWINS_DEPLOYED_AGENTS" \
  "canonical, deployed, and ops entry pairs all byte-identical"

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
