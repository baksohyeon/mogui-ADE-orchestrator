#!/usr/bin/env bash
# Regression checks for loop-check's six stop conditions and the progress
# file parser, plus one failability line per stop condition: each runs its
# case against a sed-mutated copy of the script and asserts the mutant exits
# 0 with a continue verdict, then asserts the unmutated copy exits 3 with the
# exact expected stop line. Mutates a temp copy only, never the committed
# script.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/loop-check"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# fixture <status> <rounds> <hours> <compactions> <started> <row...>
# Each row is "round|item|state|updated". Prints the new progress file's
# path, always a direct child of $work so the default --stop-file (STOP next
# to the progress file) resolves to "$work/STOP" for every case. A counter
# names each file, since BSD mktemp (macOS) does not randomize a template
# with a suffix after the X run: a literal "progress.XXXXXX.md" template
# collides with itself on the second call.
_fixture_n=0
fixture() {
  local status="$1" rounds="$2" hours="$3" compactions="$4" started="$5"
  shift 5
  _fixture_n=$((_fixture_n + 1))
  local file="$work/progress-$_fixture_n.md"
  {
    echo "# Loop fixture"
    echo "- started: $started"
    echo "- budget: rounds=$rounds hours=$hours"
    echo "- approved: test fixture"
    echo "- compactions-seen: $compactions"
    echo "- status: $status"
    if [ "$status" = stopped ]; then
      echo "- stop-reason: owner"
    else
      echo "- stop-reason:"
    fi
    echo "- next-proposal:"
    echo ""
    echo "| round | item | contract | state | task | dispatch | pr | sha | updated |"
    echo "|---|---|---|---|---|---|---|---|---|"
    local row rnd item state updated
    for row in "$@"; do
      IFS='|' read -r rnd item state updated <<<"$row"
      echo "| $rnd | $item | contract-$item | $state | task_$item | ctx_$item | #1 | sha0000 | $updated |"
    done
  } >"$file"
  printf '%s' "$file"
}

# run <interpreter> <file> <arg...> ; sets OUT, ERR, RC
run() {
  local interpreter="$1" file="$2"
  shift 2
  OUT="$("$interpreter" "$file" "$@" 2>"$work/stderr")"
  RC=$?
  ERR="$(cat "$work/stderr")"
}

assert_case() {  # label want_rc want_line file arg...
  local label="$1" want_rc="$2" want_line="$3" file="$4"
  shift 4
  run "$SCRIPT" "$file" "$@"
  if [ "$RC" -eq "$want_rc" ] && [ "$OUT" = "$want_line" ]; then
    ok "$label"
  else
    fail "$label: want rc=$want_rc out='$want_line', got rc=$RC out='$OUT' err='$ERR'"
  fi
}

assert_malformed() {  # label stderr_prefix file arg...
  local label="$1" prefix="$2" file="$3"
  shift 3
  run "$SCRIPT" "$file" "$@"
  if [ "$RC" -eq 2 ] && [ -z "$OUT" ] && printf '%s' "$ERR" | grep -q "$prefix"; then
    ok "$label: exit 2, no stdout, stderr names it"
  else
    fail "$label: want rc=2 no stdout stderr matching '$prefix', got rc=$RC out='$OUT' err='$ERR'"
  fi
}

# --- Case 1: continue_pick ---------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_case continue_pick 0 "continue round=2 pick" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 2: continue_in_flight ----------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready' '2|mgm-b|dispatched')"
assert_case continue_in_flight 0 "continue round=2 item=mgm-b state=dispatched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 3: ready_unknown ----------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_case ready_unknown 0 "continue round=2 pick ready=unknown" "$pf" \
  --now 2026-10-20T10:00:00+09:00

# --- Case 4: stop_round_budget ------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|merge-ready' '2|mgm-b|failed' '3|mgm-c|merge-ready')"
assert_case stop_round_budget 3 "stop reason=1: round budget spent (3/3)" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 5: stop_wall_clock ---------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_case stop_wall_clock 3 "stop reason=2: wall-clock budget spent (4.0h/4h)" "$pf" \
  --now 2026-10-20T13:00:00+09:00 --ready-count 2

# --- Case 6: stop_no_eligible --------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_case stop_no_eligible 3 "stop reason=3: no eligible item" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 0

# --- Case 7: stop_two_failures -------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|failed' '2|mgm-b|failed: verification')"
assert_case stop_two_failures 3 "stop reason=4: two consecutive failures (mgm-a, mgm-b)" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 8: stop_worker_question ----------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|blocked: worker-question')"
assert_case stop_worker_question 3 "stop reason=5: worker question on mgm-a" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 9: stop_escalation ----------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|blocked: escalation')"
assert_case stop_escalation 3 "stop reason=5: escalation on mgm-a" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 10: stop_file_empty_counts --------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
touch "$work/STOP"
assert_case stop_file_empty_counts 3 "stop reason=5: stop file present" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2
rm -f "$work/STOP"

# --- Case 11: stop_compaction_header (a row in flight) --------------------------
pf="$(fixture running 3 4 1 2026-10-20T09:00:00+09:00 '1|mgm-a|dispatched')"
assert_case stop_compaction_header 3 \
  "stop reason=6: compaction passed; drain item=mgm-a state=dispatched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 12: stop_compaction_flag (nothing in flight) ---------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_case stop_compaction_flag 3 \
  "stop reason=6: compaction passed; nothing in flight" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2 --compactions 1

# --- Case 13: status_stopped_wins ----------------------------------------------
pf="$(fixture stopped 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|dispatched')"
assert_case status_stopped_wins 3 "stop reason=stopped: owner drain item=mgm-a state=dispatched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 14: bot_round_count_parsed --------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|bot-round(3)')"
assert_case bot_round_count_parsed 0 "continue round=1 item=mgm-a state=bot-round(3)" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 15: in_flight_relaunched ----------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|merge-ready' '2|mgm-b|dispatched: relaunched')"
assert_case in_flight_relaunched 0 "continue round=2 item=mgm-b state=dispatched: relaunched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 16: started_requires_offset -------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00 '1|mgm-a|merge-ready')"
assert_malformed started_requires_offset '^loop-check: line 2:' "$pf"

# --- Case 17: now_before_start_is_malformed -------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
run "$SCRIPT" "$pf" --now 2026-10-20T08:00:00+09:00 --ready-count 2
if [ "$RC" -eq 2 ] && printf '%s' "$ERR" | grep -q 'now precedes started'; then
  ok "now_before_start_is_malformed: exit 2, stderr names the clock skew"
else
  fail "now_before_start_is_malformed: want rc=2 stderr 'now precedes started', got rc=$RC out='$OUT' err='$ERR'"
fi

# --- Case 18: unknown_state_is_malformed ----------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|done')"
assert_malformed unknown_state_is_malformed '^loop-check: line 12:' "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 18b: dispatched_variant_is_malformed -----------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|dispatched: stale')"
assert_malformed dispatched_variant_is_malformed '^loop-check: line 12:' "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 19: now_not_iso --------------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_malformed now_not_iso '^loop-check: --now:' "$pf" \
  --now not-a-time --ready-count 2

# --- Case 20: now_without_offset -------------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_malformed now_without_offset '^loop-check: --now:' "$pf" \
  --now 2026-10-20T10:00:00 --ready-count 2

# --- Case 21: negative_counts_are_malformed --------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
assert_malformed "negative_counts_are_malformed (--ready-count)" '^loop-check: --ready-count:' "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count -1
assert_malformed "negative_counts_are_malformed (--compactions)" '^loop-check: --compactions:' "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2 --compactions -1

# --- Case 22: running_requires_approval ------------------------------------------
pf_running="$work/progress-approval-running.md"
{
  echo "# Loop fixture"
  echo "- started: 2026-10-20T09:00:00+09:00"
  echo "- budget: rounds=3 hours=4"
  echo "- approved:"
  echo "- compactions-seen: 0"
  echo "- status: running"
  echo "- stop-reason:"
  echo "- next-proposal:"
  echo ""
  echo "| round | item | contract | state | task | dispatch | pr | sha | updated |"
  echo "|---|---|---|---|---|---|---|---|---|"
} >"$pf_running"
assert_malformed running_requires_approval '^loop-check: line 4:' "$pf_running" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

pf_stopped="$work/progress-approval-stopped.md"
{
  echo "# Loop fixture"
  echo "- started: 2026-10-20T09:00:00+09:00"
  echo "- budget: rounds=3 hours=4"
  echo "- approved:"
  echo "- compactions-seen: 0"
  echo "- status: stopped"
  echo "- stop-reason: owner"
  echo "- next-proposal:"
  echo ""
  echo "| round | item | contract | state | task | dispatch | pr | sha | updated |"
  echo "|---|---|---|---|---|---|---|---|---|"
} >"$pf_stopped"
assert_case running_requires_approval_allows_stopped 3 "stop reason=stopped: owner" "$pf_stopped" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 23: non_utf8_is_malformed ----------------------------------------------
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
pf_bin="$work/progress-non-utf8.md"
cp "$pf" "$pf_bin"
printf '\xff\xfe' >"$pf_bin"
assert_malformed non_utf8_is_malformed '^loop-check: line 0:' "$pf_bin" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 24: stop_round_budget_drains -------------------------------------------
# A row in flight when the round budget is also spent: the stop line still
# names the item to drain before the master writes status: stopped.
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|merge-ready' '2|mgm-b|failed' '3|mgm-c|merge-ready' '4|mgm-d|dispatched')"
assert_case stop_round_budget_drains 3 \
  "stop reason=1: round budget spent (3/3) drain item=mgm-d state=dispatched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Case 25: stop_file_drains ----------------------------------------------------
# The owner's stop file with a row still in flight: drain it before stopping.
pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|dispatched')"
touch "$work/STOP"
assert_case stop_file_drains 3 \
  "stop reason=5: stop file present drain item=mgm-a state=dispatched" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2
rm -f "$work/STOP"

# --- Case 26: needs_approval_does_not_spend_a_round --------------------------------
# Two needs-approval rows would spend the whole 2-round budget if counted;
# excluded, the loop keeps going instead of stopping.
pf="$(fixture running 2 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|blocked: needs-approval' '2|mgm-b|blocked: needs-approval')"
assert_case needs_approval_does_not_spend_a_round 0 "continue round=1 pick" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

# --- Failability: one per stop condition ----------------------------------------
# Each mutates a fresh temp copy of the real script, re-runs the case that
# proves the condition, and requires the mutant to exit 0 with a `continue`
# verdict; then re-runs the unmutated script and requires it to exit 3 with
# the exact expected stop line. A mutant that exits 2 or prints nothing fails
# the pair.
failability() {  # condition_label sed_expr expected_stop_line file arg...
  local label="$1" expr="$2" expected_stop="$3" file="$4"
  shift 4
  local mutant="$work/loop-check-mutant-$label"
  sed "$expr" "$SCRIPT" >"$mutant"
  chmod +x "$mutant"
  if cmp -s "$SCRIPT" "$mutant"; then
    fail "failability $label: sed expression did not change the script"
    return
  fi

  run "$mutant" "$file" "$@"
  if [ "$RC" -ne 0 ]; then
    fail "failability $label: mutant did not continue: rc=$RC out='$OUT' err='$ERR'"
    return
  fi
  case "$OUT" in
    "continue "*) ok "failability: $label mutant no longer stops (now: '$OUT')" ;;
    *)
      fail "failability $label: mutant did not print a continue line: '$OUT'"
      return
      ;;
  esac

  run "$SCRIPT" "$file" "$@"
  if [ "$RC" -eq 3 ] && [ "$OUT" = "$expected_stop" ]; then
    ok "failability: $label restored script still stops ('$OUT')"
  else
    fail "failability $label: restored script should stop with '$expected_stop', got rc=$RC out='$OUT' err='$ERR'"
  fi
}

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|merge-ready' '2|mgm-b|failed' '3|mgm-c|merge-ready')"
failability condition1-round-budget 's/completed >= p.rounds/completed > p.rounds/' \
  "stop reason=1: round budget spent (3/3)" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
failability condition2-wall-clock 's/elapsed_hours >= p.hours/elapsed_hours > p.hours/' \
  "stop reason=2: wall-clock budget spent (4.0h/4h)" "$pf" \
  --now 2026-10-20T13:00:00+09:00 --ready-count 2

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
failability condition3-no-eligible 's/ready_count == 0/ready_count == 999/' \
  "stop reason=3: no eligible item" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 0

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 \
  '1|mgm-a|failed' '2|mgm-b|failed: verification')"
failability condition4-two-failures 's/len(completed_rows) >= 2/len(completed_rows) >= 99/' \
  "stop reason=4: two consecutive failures (mgm-a, mgm-b)" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|blocked: worker-question')"
failability condition5-blocked 's/blocked: worker-question/never-matches/' \
  "stop reason=5: worker question on mgm-a" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2

pf="$(fixture running 3 4 0 2026-10-20T09:00:00+09:00 '1|mgm-a|merge-ready')"
failability condition6-compaction 's/effective_compactions >= 1/effective_compactions >= 99/' \
  "stop reason=6: compaction passed; nothing in flight" "$pf" \
  --now 2026-10-20T10:00:00+09:00 --ready-count 2 --compactions 1

[ "$FAILED" -eq 0 ] && { echo "loop-check regression tests passed"; exit 0; }
echo "loop-check: FAILED"
exit 1
