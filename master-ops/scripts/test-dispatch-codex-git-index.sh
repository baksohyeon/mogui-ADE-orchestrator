#!/bin/bash
# Static test: verify dispatch wrapper has the codex git index unlock fix
# Card: mgm-j2qy

set -eu

DISPATCH="${DISPATCH:-$(dirname "$0")/dispatch}"
WORKTREE_GIT_GUARD='[ -e "$wt_path/.git" ]'
SHARED_ADD_DIR='--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")'
ADD_DIR_FLAG='--add-dir '
GIT_ESCALATION_KIND=git_escalation
GIT_ESCALATION_DISPATCH_ID=disp-git
GIT_ESCALATION_OPERATION=add
GIT_ESCALATION_WORKTREE=/repo/worker
RECORD_LEDGER_EVENT_HEADER='record_ledger_event() {'
CAPTURE_SURFACE_HEADER='capture_codex_shared_git_surface() {'
RESOLVE_ROOT_HEADER='resolve_codex_shared_git_roots() {'
RUNTIME_COMMAND_HEADER='runtime_command() {'
SHELL_QUOTE_HEADER='shell_quote() {'
CODEX_PRETRUST_HEADER='ensure_codex_pretrust() {'

extract_shell_function() {
  local dispatch="$1" header="$2"
  awk -v header="$header" '
    $0 == header { found=1 }
    found {
      print
      opens=gsub(/{/, "{")
      closes=gsub(/}/, "}")
      depth += opens - closes
      if (depth == 0) exit
    }
  ' "$dispatch"
}

check_dispatch() {
  local dispatch="$1" guard_block guard_line status_line terminal_line

  [ -f "$dispatch" ] || return 1

  # Test 1: the linked-worktree guard must use this exact .git path.
  grep -Fq "$WORKTREE_GIT_GUARD" "$dispatch" || return 1

  # Test 2: the directory-only guard is wrong for linked worktrees.
  ! grep -Fq '[ -d "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 3: locate an uncommented status command inside the exact guard.
  guard_block=$(awk -v guard="$WORKTREE_GIT_GUARD" '
    index($0, guard) { inside=1 }
    inside {
      if ($0 ~ /^[[:space:]]*if([[:space:]]|$)/) depth++
      print
      if ($0 ~ /^[[:space:]]*fi[[:space:]]*$/) {
        depth--
        if (depth == 0) exit
      }
    }
  ' "$dispatch")
  printf '%s\n' "$guard_block" | grep -Eq '^[[:space:]]*if env -u GIT_DIR -u GIT_COMMON_DIR git -C "\$wt_path" status --porcelain([[:space:]]|$)' || return 1

  # Test 4: locate the guarded status command after the exact guard.
  guard_line=$(grep -nF "$WORKTREE_GIT_GUARD" "$dispatch" | cut -d: -f1 | head -1)
  status_line=$(grep -nE '^[[:space:]]*if env -u GIT_DIR -u GIT_COMMON_DIR git -C "\$wt_path" status --porcelain' "$dispatch" | cut -d: -f1 | head -1)
  [ -n "$guard_line" ] && [ -n "$status_line" ] || return 1
  [ "$guard_line" -lt "$status_line" ] || return 1

  # Test 5: the preflight must run before the Codex terminal is created.
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  [ "$status_line" -lt "$terminal_line" ] || return 1

  grep -Fq 'env -u GIT_DIR -u GIT_COMMON_DIR git -C "$wt_path" rev-parse --path-format=absolute --git-dir' "$dispatch" || return 1
  grep -Fq 'env -u GIT_DIR -u GIT_COMMON_DIR git -C "$wt_path" rev-parse --path-format=absolute --git-common-dir' "$dispatch" || return 1
  grep -Fq 'case "$CODEX_WORKTREE_GIT_DIR:$CODEX_SHARED_GIT_DIR" in /*:/*)' "$dispatch" || return 1
  grep -Fq 'codex shared git dir skipped · received worktree selector' "$dispatch" || return 1
  grep -Fq 'DISPATCH_LEDGER_LOCK_FD' "$dispatch" || return 1
  grep -Fq 'codex shared Git surface changed after dispatch' "$dispatch" || return 1
}

check_shared_git_root() {
  local dispatch="$1" common_line launch_line terminal_line add_dir_count

  grep -Fq 'env -u GIT_DIR -u GIT_COMMON_DIR git -C "$wt_path" rev-parse --path-format=absolute --git-dir' "$dispatch" || return 1
  grep -Fq 'env -u GIT_DIR -u GIT_COMMON_DIR git -C "$wt_path" rev-parse --path-format=absolute --git-common-dir' "$dispatch" || return 1
  grep -Fq -- "$SHARED_ADD_DIR" "$dispatch" || return 1
  common_line=$(grep -nF 'env -u GIT_DIR -u GIT_COMMON_DIR git -C "$wt_path" rev-parse --path-format=absolute --git-common-dir' "$dispatch" | cut -d: -f1 | head -1)
  launch_line=$(grep -nF -- "$SHARED_ADD_DIR" "$dispatch" | cut -d: -f1 | head -1)
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  add_dir_count=$(grep -oF -- "$ADD_DIR_FLAG" "$dispatch" | wc -l | tr -d ' ')
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

check_shared_git_root_behavior() {
  local dispatch="$1" work main linked other expected output actual parent
  local helper_fn capture_fn runtime_fn shell_quote_fn vars
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-behavior.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  main="$work/main"
  linked="$work/linked"
  other="$work/other"
  git init -q "$main"
  git -C "$main" -c user.name=test -c user.email=test@example.invalid commit --allow-empty -qm init
  git -C "$main" worktree add -q -b linked-branch "$linked"
  git init -q "$other"
  expected=$(env -u GIT_DIR -u GIT_COMMON_DIR git -C "$linked" rev-parse --path-format=absolute --git-common-dir)
  helper_fn=$(extract_shell_function "$dispatch" "$RESOLVE_ROOT_HEADER")
  capture_fn=$(extract_shell_function "$dispatch" "$CAPTURE_SURFACE_HEADER")
  runtime_fn=$(extract_shell_function "$dispatch" "$RUNTIME_COMMAND_HEADER")
  shell_quote_fn=$(extract_shell_function "$dispatch" "$SHELL_QUOTE_HEADER")
  vars=$(grep -E '^CODEX_(REASONING_EFFORT|MIGRATION_ACK|BYPASS_FLAG|SHARED_GIT_DIR|WORKTREE_GIT_DIR|SHARED_GIT_CONFIG_HASH|SHARED_GIT_HOOKS_LISTING|SHARED_GIT_SURFACE_CAPTURED)=' "$dispatch")
  [ -n "$helper_fn" ] && [ -n "$capture_fn" ] && [ -n "$runtime_fn" ] && [ -n "$shell_quote_fn" ] || return 1
  {
    echo 'set -eu'
    printf '%s\n' "$vars" "$capture_fn" "$helper_fn" "$shell_quote_fn" "$runtime_fn"
    printf 'MODEL=gpt-5.5 WORKTREE=%q CODEX_BYPASS_FLAG=\n' "path:$linked"
    echo 'resolve_codex_shared_git_roots'
    echo 'runtime_command codex'
  } > "$work/run.sh"
  output=$(GIT_DIR="$other/.git" GIT_COMMON_DIR="$other/.git" bash "$work/run.sh")
  actual=$(printf '%s\n' "$output" | sed -n 's/.*--add-dir //p' | sed 's/ --approve-for-me.*//')
  [ "$actual" = "$expected" ] || return 1
  [ "$actual" != "$linked" ] || return 1
  [ "$actual" != "$main" ] || return 1
  parent=$(dirname "$main")
  [ "$actual" != "$parent" ] || return 1
  printf '%s\n' "$output" | grep -Fq 'codex --model gpt-5.5' || return 1
}

check_non_path_selector_behavior() {
  local dispatch="$1" work helper_fn capture_fn runtime_fn shell_quote_fn vars output
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-selector.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  helper_fn=$(extract_shell_function "$dispatch" "$RESOLVE_ROOT_HEADER")
  capture_fn=$(extract_shell_function "$dispatch" "$CAPTURE_SURFACE_HEADER")
  runtime_fn=$(extract_shell_function "$dispatch" "$RUNTIME_COMMAND_HEADER")
  shell_quote_fn=$(extract_shell_function "$dispatch" "$SHELL_QUOTE_HEADER")
  vars=$(grep -E '^CODEX_(REASONING_EFFORT|MIGRATION_ACK|BYPASS_FLAG|SHARED_GIT_DIR|WORKTREE_GIT_DIR|SHARED_GIT_CONFIG_HASH|SHARED_GIT_HOOKS_LISTING|SHARED_GIT_SURFACE_CAPTURED)=' "$dispatch")
  [ -n "$helper_fn" ] && [ -n "$capture_fn" ] && [ -n "$runtime_fn" ] && [ -n "$shell_quote_fn" ] || return 1
  {
    echo 'set -eu'
    printf '%s\n' "$vars" "$capture_fn" "$helper_fn" "$shell_quote_fn" "$runtime_fn"
    echo 'WORKTREE=id:worker-271'
    echo 'resolve_codex_shared_git_roots'
    echo 'MODEL=gpt-5.5 CODEX_BYPASS_FLAG= runtime_command codex'
  } > "$work/run.sh"
  output=$(bash "$work/run.sh")
  printf '%s\n' "$output" | grep -Fq "received worktree selector 'id:worker-271'" || return 1
  [ -z "$(printf '%s\n' "$output" | grep -F -- 'absolute worktree path')" ] || return 1
  [ -z "$(printf '%s\n' "$output" | grep -F -- '--add-dir')" ] || return 1
}

check_shared_git_surface_warning() {
  local dispatch="$1" work shared capture_fn warn_fn vars output
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-surface.$$"
  mkdir -p "$work/shared/hooks"
  trap 'rm -rf "$work"' RETURN
  shared="$work/shared"
  printf '[core]\n\trepositoryformatversion = 0\n' > "$shared/config"
  : > "$shared/hooks/original"
  capture_fn=$(extract_shell_function "$dispatch" "$CAPTURE_SURFACE_HEADER")
  warn_fn=$(extract_shell_function "$dispatch" 'warn_codex_shared_git_surface_changes() {')
  vars=$(grep -E '^CODEX_(SHARED_GIT_DIR|SHARED_GIT_CONFIG_HASH|SHARED_GIT_HOOKS_LISTING|SHARED_GIT_SURFACE_CAPTURED)=' "$dispatch")
  [ -n "$capture_fn" ] && [ -n "$warn_fn" ] || return 1
  {
    echo 'set -eu'
    printf '%s\n' "$vars" "$capture_fn" "$warn_fn"
    printf 'CODEX_SHARED_GIT_DIR=%q\n' "$shared"
    echo 'capture_codex_shared_git_surface "$CODEX_SHARED_GIT_DIR"'
    echo 'printf "%s\\n" changed >> "$CODEX_SHARED_GIT_DIR/config"'
    echo 'printf "%s\\n" changed > "$CODEX_SHARED_GIT_DIR/hooks/original"'
    echo 'warn_codex_shared_git_surface_changes'
  } > "$work/run.sh"
  output=$(bash "$work/run.sh")
  printf '%s\n' "$output" | grep -Fq 'config hash and hooks listing' || return 1
}

check_completion_warning_wiring() {
  local dispatch="$1" completion_block status_line call_line
  completion_block=$(awk '
    index($0, "if [ \"$DISPATCH_STATUS\" = completed ]") { inside=1 }
    inside {
      if ($0 ~ /^[[:space:]]*if([[:space:]]|$)/) depth++
      print
      if ($0 ~ /^[[:space:]]*fi[[:space:]]*$/) {
        depth--
        if (depth == 0) exit
      }
    }
  ' "$dispatch")
  printf '%s\n' "$completion_block" | grep -Fq 'warn_codex_shared_git_surface_changes' || return 1
  status_line=$(grep -nF 'if [ "$DISPATCH_STATUS" = completed ]' "$dispatch" | cut -d: -f1 | tail -1)
  call_line=$(grep -nF 'warn_codex_shared_git_surface_changes' "$dispatch" | cut -d: -f1 | tail -1)
  [ -n "$status_line" ] && [ -n "$call_line" ] && [ "$status_line" -lt "$call_line" ] || return 1
}

check_non_path_pretrust_behavior() {
  local dispatch="$1" work pretrust_fn output
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-pretrust-selector.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  pretrust_fn=$(extract_shell_function "$dispatch" "$CODEX_PRETRUST_HEADER")
  [ -n "$pretrust_fn" ] || return 1
  {
    echo 'set -eu'
    printf '%s\n' "$pretrust_fn"
    echo 'if ensure_codex_pretrust codex id:worker-271; then exit 1; fi'
  } > "$work/run.sh"
  output=$(bash "$work/run.sh" 2>&1)
  printf '%s\n' "$output" | grep -Fq "received 'id:worker-271'" || return 1
}

check_git_escalation_event() {
  local dispatch="$1" work event_fn ledger row selector
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-event.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  event_fn=$(extract_shell_function "$dispatch" "$RECORD_LEDGER_EVENT_HEADER")
  [ -n "$event_fn" ] || return 1
  ledger="$work/ledger.jsonl"
  selector="path:$GIT_ESCALATION_WORKTREE/../worker"
  {
    echo 'set -eu'
    printf 'LEDGER=%q\nLEDGER_LOCK=%q\n' "$ledger" "$work/ledger.lock"
    printf 'LEDGER_EVENT=%q\nLEDGER_EVENT_DISPATCH_ID=%q\n' "$GIT_ESCALATION_KIND" "$GIT_ESCALATION_DISPATCH_ID"
    printf 'LEDGER_EVENT_RESULT=\nLEDGER_EVENT_REASON=\nLEDGER_EVENT_QUERY=\n'
    printf 'LEDGER_EVENT_SESSION_ID=\nWORKTREE=%q\n' "$selector"
    printf 'LEDGER_EVENT_WORKTREE_PATH=\nLEDGER_EVENT_OPERATION=%q\n' "$GIT_ESCALATION_OPERATION"
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

check_git_escalation_lock_fd() {
  local dispatch="$1" work event_fn ledger run_script holder_script
  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-lock.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' RETURN
  event_fn=$(extract_shell_function "$dispatch" "$RECORD_LEDGER_EVENT_HEADER")
  [ -n "$event_fn" ] || return 1
  ledger="$work/ledger.jsonl"
  run_script="$work/run.sh"
  {
    echo 'set -eu'
    printf 'LEDGER=%q\nLEDGER_LOCK=%q\n' "$ledger" "$work/ledger.lock"
    printf 'LEDGER_EVENT=%q\nLEDGER_EVENT_DISPATCH_ID=disp-lock\n' "$GIT_ESCALATION_KIND"
    printf 'LEDGER_EVENT_RESULT=\nLEDGER_EVENT_REASON=\nLEDGER_EVENT_QUERY=\nLEDGER_EVENT_SESSION_ID=\n'
    printf 'WORKTREE=%q\nLEDGER_EVENT_WORKTREE_PATH=%q\n' "$GIT_ESCALATION_WORKTREE" "$GIT_ESCALATION_WORKTREE"
    printf 'LEDGER_EVENT_OPERATION=%q\nLEDGER_EVENT_ESCALATED=yes\nLEDGER_EVENT_REFUSAL=%q\n' "$GIT_ESCALATION_OPERATION" 'fatal: lock test'
    printf '%s\n' "$event_fn"
    echo 'record_ledger_event'
  } > "$run_script"
  holder_script="$work/holder.py"
  cat > "$holder_script" <<'PY'
import fcntl
import os
import subprocess
import sys

lock_path, run_script = sys.argv[1:]
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    no_fd = subprocess.Popen(["bash", run_script])
    try:
        no_fd.wait(timeout=1)
    except subprocess.TimeoutExpired:
        no_fd.kill()
        no_fd.wait()
    else:
        raise SystemExit("ledger writer ignored its lock without an inherited fd")
    env = os.environ.copy()
    env["DISPATCH_LEDGER_LOCK_FD"] = str(fd)
    with_fd = subprocess.run(
        ["bash", run_script], env=env, pass_fds=(fd,), timeout=2, check=False
    )
    if with_fd.returncode != 0:
        raise SystemExit("ledger writer did not honor the inherited lock fd")
finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
PY
  python3 "$holder_script" "$work/ledger.lock" "$run_script"
}

check_git_escalation_cli() {
  local dispatch="$1" work rendered ledger worktree_path operation result_code line_count
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
  worktree_path="$work/worker"
  for operation in add commit fetch push; do
    MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id "disp-$operation" \
      --worktree-path "$worktree_path" --operation "$operation" --escalated yes \
      --refusal "fatal: $operation refusal" >/dev/null 2>&1
    result_code=$?
    [ "$result_code" -eq 0 ] || return 1
  done
  line_count=$(wc -l < "$ledger" | tr -d ' ')
  [ "$line_count" -eq 4 ] || return 1

  if MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id disp-invalid \
      --worktree-path "$worktree_path" --operation merge --escalated yes \
      --refusal "fatal: invalid operation" >/dev/null 2>&1; then
    return 1
  fi
  if MOGUI_STATE_DIR="$work/state" MOGUI_TEST_LEDGER="$ledger" MOGUI_TEST_ROOT="$work" \
      "$rendered" --ledger-event git_escalation --dispatch-id disp-no-refusal \
      --worktree-path "$worktree_path" --operation add --escalated yes >/dev/null 2>&1; then
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

check_shared_git_root_behavior "$DISPATCH" || {
  echo "✗ real linked-worktree probe did not derive the absolute shared Git root" >&2
  exit 1
}
echo "✓ real linked-worktree probe matches git's absolute shared Git root with GIT_DIR set"

check_non_path_selector_behavior "$DISPATCH" || {
  echo "✗ non-path worktree selectors were not reported and skipped" >&2
  exit 1
}
echo "✓ non-path worktree selectors skip the shared root with the received selector named"

check_shared_git_surface_warning "$DISPATCH" || {
  echo "✗ shared Git config and hooks changes did not produce the completion warning" >&2
  exit 1
}
echo "✓ completed Codex dispatches warn when the shared Git config or hooks listing changes"

check_completion_warning_wiring "$DISPATCH" || {
  echo "✗ completion path does not invoke the shared Git surface warning" >&2
  exit 1
}
echo "✓ completion path invokes the shared Git surface warning after reading completion status"

check_non_path_pretrust_behavior "$DISPATCH" || {
  echo "✗ fresh Codex pre-trust did not fail closed for a non-path selector" >&2
  exit 1
}
echo "✓ fresh Codex pre-trust fails closed for a non-path selector and names the input"

check_git_escalation_event "$DISPATCH" || {
  echo "✗ one git escalation did not produce one five-field ledger event" >&2
  exit 1
}
echo "✓ one git escalation produces one locked ledger event with the five required fields"

check_git_escalation_lock_fd "$DISPATCH" || {
  echo "✗ git_escalation did not honor the inherited lock fd and retain its own flock" >&2
  exit 1
}
echo "✓ git_escalation honors DISPATCH_LEDGER_LOCK_FD and still serializes without it"

check_git_escalation_cli "$DISPATCH" || {
  echo "✗ git_escalation CLI validation did not cover accepted operations and refusals" >&2
  exit 1
}
echo "✓ git_escalation CLI accepts the four operations and refuses invalid inputs"

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-index.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT
mutant="$work/dispatch-mutant"
sed '/^[[:space:]]*if env -u GIT_DIR -u GIT_COMMON_DIR git -C "\$wt_path" status --porcelain/d' "$DISPATCH" > "$mutant"

if MUTANT_EXPECTED=1 DISPATCH="$mutant" "$0"; then
  echo "✗ mutant run unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ mutant run failed as expected: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")"
fi

root_mutant="$work/dispatch-root-mutant"
sed 's/--add-dir $(shell_quote "$CODEX_SHARED_GIT_DIR")/--add-dir $(shell_quote "$(dirname "$CODEX_SHARED_GIT_DIR")")/' "$DISPATCH" > "$root_mutant"
if MUTANT_EXPECTED=1 DISPATCH="$root_mutant" "$0"; then
  echo "✗ dirname-root mutant unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$root_mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ dirname-root mutant failed as expected: the parent of the shared Git root is rejected"
fi

absolute_case_mutant="$work/dispatch-absolute-case-mutant"
sed '/&& case "\$CODEX_WORKTREE_GIT_DIR:/ s#&& case.*esac#\&\& true#' "$DISPATCH" > "$absolute_case_mutant"
if MUTANT_EXPECTED=1 DISPATCH="$absolute_case_mutant" "$0"; then
  echo "✗ absolute-path validation mutant unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$absolute_case_mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ absolute-path validation mutant failed as expected: relative roots are rejected"
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
awk -v guard="$WORKTREE_GIT_GUARD" '
  index($0, guard) { inside=1 }
  inside {
    if ($0 ~ /^[[:space:]]*if([[:space:]]|$)/) depth++
    if ($0 ~ /^[[:space:]]*if env -u GIT_DIR -u GIT_COMMON_DIR git -C "\$wt_path" status --porcelain/) { status_line=$0; next }
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

lock_mutant="$work/dispatch-lock-mutant"
sed '/fcntl\.flock(lock\.fileno(), fcntl\.LOCK_EX)/d' "$DISPATCH" > "$lock_mutant"
if DISPATCH="$lock_mutant" check_git_escalation_lock_fd "$lock_mutant" 2>/dev/null; then
  echo "✗ ledger-flock mutant unexpectedly passed" >&2
  exit 1
else
  echo "✓ ledger-flock mutant failed as expected: the event writer must retain its flock"
fi

echo "✓ All static checks passed"
