#!/bin/bash
# Static test: verify dispatch wrapper has the codex git index unlock fix
# Card: mgm-up2w

set -eu

DISPATCH="${DISPATCH:-$(dirname "$0")/dispatch}"

check_dispatch() {
  local dispatch="$1" guard_block guard_line status_line terminal_line

  [ -f "$dispatch" ] || return 1

  # Test 1: the linked-worktree guard must use this exact .git path.
  grep -Fq '[ -e "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 2: the directory-only guard is wrong for linked worktrees.
  ! grep -Fq '[ -d "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 3: locate an uncommented status command inside the exact guard.
  guard_block=$(awk '
    index($0, "[ -e \"$wt_path/.git\" ]") { inside=1 }
    inside {
      if ($0 ~ /^[[:space:]]*if([[:space:]]|$)/) depth++
      print
      if ($0 ~ /^[[:space:]]*fi[[:space:]]*$/) {
        depth--
        if (depth == 0) exit
      }
    }
  ' "$dispatch")
  printf '%s\n' "$guard_block" | grep -Eq '^[[:space:]]*if git -C "\$wt_path" status --porcelain([[:space:]]|$)' || return 1

  # Test 4: locate the guarded status command after the exact guard.
  guard_line=$(grep -nF '[ -e "$wt_path/.git" ]' "$dispatch" | cut -d: -f1 | head -1)
  status_line=$(grep -nE '^[[:space:]]*if git -C "\$wt_path" status --porcelain' "$dispatch" | cut -d: -f1 | head -1)
  [ -n "$guard_line" ] && [ -n "$status_line" ] || return 1
  [ "$guard_line" -lt "$status_line" ] || return 1

  # Test 5: the preflight must run before the Codex terminal is created.
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  [ "$status_line" -lt "$terminal_line" ] || return 1
}

check_shared_git_root() {
  local dispatch="$1" common_line launch_line terminal_line add_dir_count

  grep -Fq 'git -C "$wt_path" rev-parse --git-dir' "$dispatch" || return 1
  grep -Fq 'git -C "$wt_path" rev-parse --git-common-dir' "$dispatch" || return 1
  grep -Fq -- '--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")' "$dispatch" || return 1
  common_line=$(grep -nF 'git -C "$wt_path" rev-parse --git-common-dir' "$dispatch" | cut -d: -f1 | head -1)
  launch_line=$(grep -nF -- '--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")' "$dispatch" | cut -d: -f1 | head -1)
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  add_dir_count=$(grep -oF -- '--add-dir ' "$dispatch" | wc -l | tr -d ' ')
  [ "$add_dir_count" -eq 1 ] || return 1
  [ "$common_line" -lt "$terminal_line" ] || return 1

  # A linked worktree's shared Git directory is the only additional root.
  ! grep -Fq -- '--add-dir $(shell_quote "$wt_path")' "$dispatch" || return 1
  ! grep -Fq -- '--add-dir $(shell_quote "$(dirname "$CODEX_SHARED_GIT_DIR")")' "$dispatch" || return 1
}

check_runtime_root_value() {
  local dispatch="$1" work runtime_fn shell_quote_fn vars out
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-root.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  runtime_fn=$(awk '$0=="runtime_command() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  shell_quote_fn=$(awk '$0=="shell_quote() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  vars=$(grep -E '^CODEX_(REASONING_EFFORT|MIGRATION_ACK|BYPASS_FLAG|SHARED_GIT_DIR)=' "$dispatch")
  [ -n "$runtime_fn" ] && [ -n "$shell_quote_fn" ] || return 1
  {
    echo 'set -u'
    printf '%s\n' "$vars" "$shell_quote_fn" "$runtime_fn"
    echo 'MODEL=gpt-5.5 CODEX_SHARED_GIT_DIR=/repo/.git CODEX_BYPASS_FLAG= runtime_command codex'
  } > "$work/run.sh"
  out=$(bash "$work/run.sh")
  case "$out" in
    *"--add-dir /repo/.git"*) ;;
    *) return 1;;
  esac
  case "$out" in
    *"--add-dir /repo "*) return 1;;
    *) ;;
  esac
}

check_git_escalation_event() {
  local dispatch="$1" work event_fn ledger row
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-event.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  event_fn=$(awk '$0=="record_ledger_event() {"{f=1} f{print} f&&$0=="EOF"{e=1} f&&e&&$0=="}"{exit}' "$dispatch")
  [ -n "$event_fn" ] || return 1
  ledger="$work/ledger.jsonl"
  {
    echo 'set -eu'
    printf 'LEDGER=%q\nLEDGER_LOCK=%q\n' "$ledger" "$work/ledger.lock"
    printf 'LEDGER_EVENT=git_escalation\nLEDGER_EVENT_DISPATCH_ID=disp-git\n'
    printf 'LEDGER_EVENT_RESULT=\nLEDGER_EVENT_REASON=\nLEDGER_EVENT_QUERY=\n'
    printf 'LEDGER_EVENT_SESSION_ID=\nWORKTREE=path:/repo/worker\n'
    printf 'LEDGER_EVENT_WORKTREE_PATH=/repo/worker\nLEDGER_EVENT_OPERATION=add\n'
    printf 'LEDGER_EVENT_ESCALATED=yes\nLEDGER_EVENT_REFUSAL=%q\n' $'fatal: Unable to create index.lock: Operation not permitted\nsecond line'
    printf '%s\n' "$event_fn"
    echo 'record_ledger_event'
  } > "$work/run.sh"
  bash "$work/run.sh"
  row=$(python3 - "$ledger" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    rows = [json.loads(line) for line in stream if line.strip()]
assert len(rows) == 1, rows
row = rows[0]
assert row["kind"] == "git_escalation", row
assert row["job_id"] == "disp-git", row
assert row["worktree"] == "/repo/worker", row
assert row["operation"] == "add", row
assert row["escalated"] is True, row
assert row["refusal"] == "fatal: Unable to create index.lock: Operation not permitted", row
assert set(row) == {"ts", "kind", "job_id", "worktree", "operation", "escalated", "refusal"}, row
print("ok")
PY
)
  [ "$row" = ok ] || return 1
}

check_git_escalation_cli() {
  local dispatch="$1" work rendered ledger operation result_code line_count
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-cli.$$"
  mkdir -p "$work/scripts" "$work/state"
  trap 'rm -rf "$work"' RETURN
  cp "$(dirname "$dispatch")/approval-prompt-markers.txt" "$work/scripts/approval-prompt-markers.txt"
  cat > "$work/scripts/dispatch-gate" <<'BIN'
#!/bin/bash
case "$*" in
  *" lock-path") printf '%s\n' "${MOGUI_TEST_LEDGER}.lock" ;;
  *" session-root --runtime"*) printf '%s\n' "$MOGUI_TEST_ROOT" ;;
  *) exit 1 ;;
esac
BIN
  chmod +x "$work/scripts/dispatch-gate"
  rendered="$work/scripts/dispatch"
  sed -e "s#{{RUNTIME_ROOT}}#$work#g" -e "s#{{OPS_REPO}}#$work#g" "$dispatch" > "$rendered"
  chmod +x "$rendered"
  ledger="$work/state/dispatch-ledger.jsonl"
  for operation in add commit fetch push; do
    MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id "disp-$operation" \
      --worktree-path "$work/worker" --operation "$operation" --escalated yes \
      --refusal "fatal: $operation refusal" >/dev/null 2>&1
    result_code=$?
    [ "$result_code" -eq 0 ] || return 1
  done
  line_count=$(wc -l < "$ledger" | tr -d ' ')
  [ "$line_count" -eq 4 ] || return 1

  if MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id disp-invalid \
      --worktree-path "$work/worker" --operation merge --escalated yes \
      --refusal "fatal: invalid operation" >/dev/null 2>&1; then
    return 1
  fi
  if MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id disp-no-refusal \
      --worktree-path "$work/worker" --operation add --escalated yes >/dev/null 2>&1; then
    return 1
  fi
  if MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id disp-no-worktree \
      --operation add --escalated yes --refusal "fatal: missing worktree" >/dev/null 2>&1; then
    return 1
  fi
}

if [ "${MUTANT_EXPECTED:-0}" = 1 ]; then
  check_dispatch "$DISPATCH" && check_shared_git_root "$DISPATCH"
  exit $?
fi

check_dispatch "$DISPATCH" || {
  echo "✗ dispatch git index preflight checks failed: $DISPATCH" >&2
  exit 1
}
echo "✓ dispatch uses the exact linked-worktree guard, an uncommented status command, and pre-launch ordering"

check_shared_git_root "$DISPATCH" || {
  echo "✗ dispatch does not add only the shared Git directory to Codex" >&2
  exit 1
}
echo "✓ Codex launch derives and adds the shared Git directory only"

check_runtime_root_value "$DISPATCH" || {
  echo "✗ Codex launch root is not the shared Git directory" >&2
  exit 1
}
echo "✓ Codex launch carries the shared Git directory and excludes its parent checkout"

check_git_escalation_event "$DISPATCH" || {
  echo "✗ one git escalation did not produce one five-field ledger event" >&2
  exit 1
}
echo "✓ one git escalation produces one locked ledger event with the five required fields"

check_git_escalation_cli "$DISPATCH" || {
  echo "✗ git_escalation CLI validation did not cover accepted operations and refusals" >&2
  exit 1
}
echo "✓ git_escalation CLI accepts the four operations and refuses invalid inputs"

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-index.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT
mutant="$work/dispatch-mutant"
sed '/^[[:space:]]*if git -C "\$wt_path" status --porcelain/d' "$DISPATCH" > "$mutant"

if MUTANT_EXPECTED=1 DISPATCH="$mutant" "$0"; then
  echo "✗ mutant run unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ mutant run failed as expected: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")"
fi

root_mutant="$work/dispatch-root-mutant"
sed 's/--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")/--add-dir $(shell_quote "$wt_path")/' "$DISPATCH" > "$root_mutant"
if MUTANT_EXPECTED=1 DISPATCH="$root_mutant" "$0"; then
  echo "✗ parent/root mutant unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$root_mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ root-scope mutant failed as expected: the worker worktree is not the shared Git root"
fi

extra_root_mutant="$work/dispatch-extra-root-mutant"
sed 's/--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")/--add-dir \/etc --add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")/' "$DISPATCH" > "$extra_root_mutant"
if MUTANT_EXPECTED=1 DISPATCH="$extra_root_mutant" "$0"; then
  echo "✗ extra-root mutant unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$extra_root_mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ extra-root mutant failed as expected: Codex gets exactly one additional root"
fi

scope_mutant="$work/dispatch-scope-mutant"
awk '
  index($0, "[ -e \"$wt_path/.git\" ]") { inside=1 }
  inside {
    if ($0 ~ /^[[:space:]]*if([[:space:]]|$)/) depth++
    if ($0 ~ /^[[:space:]]*if git -C "\$wt_path" status --porcelain/) { status_line=$0; next }
    print
    if ($0 ~ /^[[:space:]]*fi[[:space:]]*$/) {
      depth--
      if (depth == 0) {
        print status_line
        inside=0
      }
    }
    next
  }
  { print }
' "$DISPATCH" > "$scope_mutant"
if MUTANT_EXPECTED=1 DISPATCH="$scope_mutant" "$0"; then
  echo "✗ scope mutant unexpectedly passed: the git status check escaped its worktree guard" >&2
  exit 1
else
  echo "✓ scope mutant failed as expected: git status remains nested in the worktree guard"
fi

event_mutant="$work/dispatch-event-mutant"
sed 's/"refusal": (refusal.splitlines() or \[""\])\[0\]/"refusal": refusal/' "$DISPATCH" > "$event_mutant"
if DISPATCH="$event_mutant" check_git_escalation_event "$event_mutant" 2>/dev/null; then
  echo "✗ refusal-first-line mutant unexpectedly passed" >&2
  exit 1
else
  echo "✓ refusal-first-line mutant failed as expected"
fi

echo "✓ All static checks passed"
