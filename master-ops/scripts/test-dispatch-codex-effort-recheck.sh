#!/bin/bash
# Fixture coverage for the Codex start-screen effort re-check. The first five
# pane reads use the same footer, the sixth read is the post-delivery footer,
# and the register row is inspected after the wrapper's update.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

start_fn=$(awk '$0=="codex_start_screen_problem() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
recheck_fn=$(awk '$0=="codex_effort_recheck() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
record_fn=$(awk '$0=="record_codex_effort() {"{f=1} f{print} f&&$0=="EOF"{e=1} f&&e&&$0=="}"{exit}' "$dispatch")
markers=$(grep -E '^LIMIT_MARKERS=' "$dispatch")
start_block=$(awk '
  $0=="if [ \"$RUNTIME\" = codex ]; then"{f=1}
  f && $0=="# 4. dispatch --inject"{exit}
  f{print}
' "$dispatch")

[ -n "$start_fn" ] || { echo "FAIL: could not extract codex_start_screen_problem" >&2; exit 1; }
[ -n "$recheck_fn" ] || { echo "FAIL: could not extract codex_effort_recheck" >&2; exit 1; }
[ -n "$record_fn" ] || { echo "FAIL: could not extract record_codex_effort" >&2; exit 1; }
[ -n "$start_block" ] || { echo "FAIL: could not extract codex start-screen caller" >&2; exit 1; }

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-effort-recheck.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT

cat > "$work/orca" <<'BIN'
#!/bin/bash
if [ "$1 $2" = "terminal read" ]; then
  count=$(sed -n '1p' "$FAKE_COUNT")
  count=$((count + 1))
  printf '%s\n' "$count" > "$FAKE_COUNT"
  if [ "$count" -le 5 ]; then
    sed -n '1,$p' "$FAKE_START"
  else
    sed -n '1,$p' "$FAKE_RECHECK"
  fi
  exit 0
fi
exit 1
BIN
cat > "$work/sleep" <<'BIN'
#!/bin/bash
exit 0
BIN
chmod +x "$work/orca" "$work/sleep"

run_case() {
  local label="$1" start_pane="$2" recheck_pane="$3" expected_status="$4" expected_effort="$5" warning="$6" expected_reads="$7"
  local script_file="$work/$label.sh" ledger="$work/$label-ledger.jsonl" out status row reads
  printf '%s\n' "$start_pane" > "$work/start-pane"
  printf '%s\n' "$recheck_pane" > "$work/recheck-pane"
  printf '0\n' > "$work/count"
  printf '%s\n' '{"decision":"ALLOW","job_id":"ctx_fake","runtime":"codex"}' > "$ledger"
  {
    echo 'set -u'
    printf 'export FAKE_COUNT=%q FAKE_START=%q FAKE_RECHECK=%q\n' "$work/count" "$work/start-pane" "$work/recheck-pane"
    printf 'LEDGER=%q\nDISP=ctx_fake\nCHECK_ONLY=0\n' "$ledger"
    echo 'RUNTIME=codex MODEL=gpt-5.5 CODEX_REASONING_EFFORT=xhigh TERMINAL=term_fake'
    echo 'HOOKS_ANSWERED=0 HOOKS_ANSWER_BIN=missing'
    printf '%s\n' "$markers" "$start_fn" "$recheck_fn" "$record_fn"
    printf '%s\n' "$start_block"
    echo 'DELIVERY_SUCCEEDED=1'
    echo 'if [ "${CODEX_EFFORT_RECHECK:-0}" = 1 ]; then'
    echo '  CODEX_EFFORT_RECHECK_RC=1'
    echo '  CODEX_EFFORT_RECHECK_PROBLEM=""'
    echo '  for effort_attempt in 1 2 3 4 5 6 7 8 9 10; do'
    echo '    CODEX_RECHECK_PANE=$(orca terminal read --terminal "$TERMINAL" --limit 40)'
    echo '    CODEX_EFFORT_RECHECK_PROBLEM=$(codex_effort_recheck "$CODEX_RECHECK_PANE" "$MODEL" "$CODEX_REASONING_EFFORT")'
    echo '    CODEX_EFFORT_RECHECK_RC=$?'
    echo '    if [ "$CODEX_EFFORT_RECHECK_RC" = 0 ] || [ "$CODEX_EFFORT_RECHECK_RC" = 2 ] || [ "$CODEX_EFFORT_RECHECK_RC" = 3 ]; then break; fi'
    echo '    [ "$effort_attempt" -lt 10 ] && sleep 3'
    echo '  done'
    echo '  case "$CODEX_EFFORT_RECHECK_RC" in'
    echo '    0) record_codex_effort measured;;'
    echo '    1|2) record_codex_effort unverified; echo "⚠ codex effort unverified · $CODEX_EFFORT_RECHECK_PROBLEM" >&2;;'
    echo '    3) echo "✗ codex effort re-check · $CODEX_EFFORT_RECHECK_PROBLEM" >&2; exit 3;;'
    echo '    *) exit 3;;'
    echo '  esac'
    echo 'else'
    echo '  record_codex_effort measured'
    echo 'fi'
    echo 'exit 0'
  } > "$script_file"
  set +e
  out=$(PATH="$work:$PATH" bash "$script_file" 2>"$work/$label.stderr")
  status=$?
  set -e
  if [ "$status" != "$expected_status" ]; then
    echo "FAIL: $label expected exit $expected_status, got $status" >&2
    printf '%s\n' "$out" >&2
    sed -n '1,120p' "$work/$label.stderr" >&2
    return 1
  fi
  if [ "$warning" = 1 ] && ! grep -qF "start screen shows 'gpt-5.5 default'; requested 'gpt-5.5 xhigh'" "$work/$label.stderr"; then
    echo "FAIL: $label did not warn with both effort labels" >&2
    sed -n '1,120p' "$work/$label.stderr" >&2
    return 1
  fi
  if [ "$warning" = 2 ] && ! grep -qF "footer shows 'gpt-5.4 xhigh', requested 'gpt-5.5 xhigh'" "$work/$label.stderr"; then
    echo "FAIL: $label did not warn about the model mismatch" >&2
    sed -n '1,120p' "$work/$label.stderr" >&2
    return 1
  fi
  if [ "$warning" = 3 ] && ! grep -qF "effort label 'low' on start screen; requested 'gpt-5.5 xhigh'" "$work/$label.stderr" && ! grep -qF "start screen shows non-default effort 'gpt-5.5 low'; requested 'gpt-5.5 xhigh'" "$work/$label.stderr"; then
    echo "FAIL: $label did not reject a non-default effort mismatch" >&2
    sed -n '1,120p' "$work/$label.stderr" >&2
    return 1
  fi
  if [ "$warning" = 0 ] && [ -s "$work/$label.stderr" ]; then
    echo "FAIL: $label unexpectedly wrote stderr" >&2
    sed -n '1,120p' "$work/$label.stderr" >&2
    return 1
  fi
  if [ "$expected_status" != 0 ]; then
    reads=$(sed -n '1p' "$work/count")
    if [ "$reads" != "$expected_reads" ]; then
      echo "FAIL: $label expected $expected_reads pane reads, got $reads" >&2
      return 1
    fi
    echo "ok   : $label · exit=$status"
    return 0
  fi
  reads=$(sed -n '1p' "$work/count")
  if [ "$reads" != "$expected_reads" ]; then
    echo "FAIL: $label expected $expected_reads pane reads, got $reads" >&2
    return 1
  fi
  row=$(python3 -c 'import json,sys; print(json.dumps(json.loads(open(sys.argv[1]).readline()), sort_keys=True))' "$ledger")
  case "$expected_effort" in
    measured)
      case "$row" in
        *'"effort": "measured"'*) :;;
        *) echo "FAIL: $label ledger row lacks effort: measured: $row" >&2; return 1;;
      esac
      case "$row" in
        *effort_unverified*) echo "FAIL: $label ledger row should not be unverified: $row" >&2; return 1;;
      esac;;
    unverified)
      case "$row" in
        *'"effort_unverified": true'*) :;;
        *) echo "FAIL: $label ledger row lacks effort_unverified: true: $row" >&2; return 1;;
      esac
      case "$row" in
        *'"effort": "measured"'*) echo "FAIL: $label ledger row should not be measured: $row" >&2; return 1;;
      esac;;
  esac
  if [ "$(wc -l < "$ledger" | tr -d ' ')" != 1 ]; then
    echo "FAIL: $label created a second ledger row" >&2
    return 1
  fi
  echo "ok   : $label · exit=$status · effort=$expected_effort"
}

default_pane='› Ask Codex to do anything
  GPT-5.5 default · ~/worktree'
xhigh_pane='› Ask Codex to do anything
  GPT-5.5 xhigh · ~/worktree'
wrong_model_pane='› Ask Codex to do anything
  GPT-5.4 xhigh · ~/worktree'
wrong_effort_pane='› Ask Codex to do anything
  GPT-5.5 low · ~/worktree'

run_case matched-start "$xhigh_pane" "$wrong_model_pane" 0 measured 0 1
run_case default-repaints "$default_pane" "$xhigh_pane" 0 measured 0 6
run_case default-persists "$default_pane" "$default_pane" 0 unverified 1 15
run_case post-delivery-model-mismatch "$default_pane" "$wrong_model_pane" 0 unverified 2 6
run_case post-delivery-non-default-effort "$default_pane" "$wrong_effort_pane" 3 unused 3 6
run_case initial-non-default-effort "$wrong_effort_pane" "$xhigh_pane" 3 unused 3 5
run_case different-model "$wrong_model_pane" "$xhigh_pane" 3 unused 2 1

echo "dispatch codex effort re-check fixture tests passed"
