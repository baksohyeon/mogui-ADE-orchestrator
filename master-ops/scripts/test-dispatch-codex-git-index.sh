#!/bin/bash
# Static test: verify dispatch wrapper has the codex git index unlock fix
# Card: mgm-up2w

set -eu

DISPATCH="${DISPATCH:-$(dirname "$0")/dispatch}"

check_dispatch() {
  local dispatch="$1" guard_line status_line terminal_line

  [ -f "$dispatch" ] || return 1

  # Test 1: the linked-worktree guard must use this exact .git path.
  grep -Fq '[ -e "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 2: the directory-only guard is wrong for linked worktrees.
  ! grep -Fq '[ -d "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 3: locate an uncommented status command after the exact guard.
  guard_line=$(grep -nF '[ -e "$wt_path/.git" ]' "$dispatch" | cut -d: -f1 | head -1)
  status_line=$(grep -nE '^[[:space:]]*if git -C "\$wt_path" status --porcelain' "$dispatch" | cut -d: -f1 | head -1)
  [ -n "$guard_line" ] && [ -n "$status_line" ] || return 1
  [ "$guard_line" -lt "$status_line" ] || return 1

  # Test 4: the preflight must run before the Codex terminal is created.
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  [ "$status_line" -lt "$terminal_line" ] || return 1
}

check_shared_git_root() {
  local dispatch="$1" common_line launch_line terminal_line

  grep -Fq 'git -C "$wt_path" rev-parse --git-dir' "$dispatch" || return 1
  grep -Fq 'git -C "$wt_path" rev-parse --git-common-dir' "$dispatch" || return 1
  grep -Fq -- '--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")' "$dispatch" || return 1
  common_line=$(grep -nF 'git -C "$wt_path" rev-parse --git-common-dir' "$dispatch" | cut -d: -f1 | head -1)
  launch_line=$(grep -nF -- '--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")' "$dispatch" | cut -d: -f1 | head -1)
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
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

event_mutant="$work/dispatch-event-mutant"
sed 's/"refusal": (refusal.splitlines() or \[""\])\[0\]/"refusal": refusal/' "$DISPATCH" > "$event_mutant"
if DISPATCH="$event_mutant" check_git_escalation_event "$event_mutant" 2>/dev/null; then
  echo "✗ refusal-first-line mutant unexpectedly passed" >&2
  exit 1
else
  echo "✓ refusal-first-line mutant failed as expected"
fi

echo "✓ All static checks passed"
