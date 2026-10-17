#!/bin/bash
# Regression checks for the two optional codex launch keys dispatch reads from
# the instance runtime config: codex_reasoning_effort and
# codex_bypass_approvals_and_sandbox. Absent keys keep today's launch line, a
# valid effort changes both the launch line and the footer the start-screen
# check expects, a true bypass appends the flag, and an invalid value is
# refused with exit 2. A new file because test-dispatch-runtime.sh is past the
# 1,000-line rule (CONTRIBUTING.md "When a file is full").
#
# dispatch carries template placeholders, so each case extracts the launch
# variables and functions by exact-line awk range, the convention
# test-dispatch-runtime.sh already uses, and runs them in an isolated subshell
# against a scratch config file.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

extract_fn() {  # fn-name
  awk -v fn="$1() {" '$0==fn{f=1} f{print} f&&$0=="}"{exit}' "$dispatch"
}

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-instance-config.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT

vars=$(grep -E '^CODEX_(REASONING_EFFORT|MIGRATION_ACK|BYPASS_FLAG)=' "$dispatch")
markers=$(grep -E '^LIMIT_MARKERS=' "$dispatch")
shell_quote_fn=$(extract_fn shell_quote)
read_fn=$(extract_fn codex_instance_launch_config)
apply_fn=$(extract_fn apply_codex_instance_launch_config)
runtime_command_fn=$(extract_fn runtime_command)
start_fn=$(extract_fn codex_start_screen_problem)

[ "$(printf '%s\n' "$vars" | grep -c .)" = 3 ] || { echo "FAIL: could not extract the three CODEX_ launch variables" >&2; exit 1; }
for name in markers shell_quote_fn read_fn apply_fn runtime_command_fn start_fn; do
  [ -n "${!name}" ] || { echo "FAIL: could not extract $name from dispatch" >&2; exit 1; }
done
grep -qx 'apply_codex_instance_launch_config' "$dispatch" \
  || { echo "FAIL: dispatch never calls apply_codex_instance_launch_config" >&2; exit 1; }

today='codex --model gpt-5.5 -c '"'"'model_reasoning_effort="xhigh"'"'"' -c check_for_update_on_startup=false -c '"'"'notice.model_migrations={"gpt-5.5"="gpt-6.1-sol"}'"'"''
high=${today/'"xhigh"'/'"high"'}
bypass="$today --dangerously-bypass-approvals-and-sandbox"

# run_case  read-fn  apply-fn  config-json|-  [footer-pane]
# Prints the codex launch line; with a pane, also the start-screen verdict.
run_case() {
  local read_body="$1" apply_body="$2" json="$3" pane="${4:-}" config="$work/instance-runtime.json"
  rm -f "$config"
  [ "$json" = - ] || printf '%s\n' "$json" > "$config"
  printf '%s\n' "$pane" > "$work/pane.txt"
  {
    echo 'set -u'
    printf 'INSTANCE_RUNTIME_CONFIG=%s\n' "$config"
    printf '%s\n' "$vars" "$markers" "$shell_quote_fn" "$read_body" "$apply_body" "$runtime_command_fn" "$start_fn"
    echo 'apply_codex_instance_launch_config'
    echo 'MODEL=gpt-5.5'
    echo 'runtime_command codex'
    if [ -n "$pane" ]; then
      printf 'codex_start_screen_problem "$(cat %s)" "$MODEL" "$CODEX_REASONING_EFFORT"; echo "footer-rc=$?"\n' "$work/pane.txt"
    fi
  } > "$work/run.sh"
  bash "$work/run.sh" 2>&1
}

expect() {  # label  want  got
  if [ "$2" != "$3" ]; then
    echo "FAIL: $1" >&2
    echo "  want: $2" >&2
    echo "  got:  $3" >&2
    exit 1
  fi
  echo "ok   : $1"
}

mutate() {  # source  needle  replacement
  local out=${1/"$2"/"$3"}
  [ "$out" != "$1" ] || { echo "FAIL: mutant did not change the source ($2)" >&2; exit 1; }
  printf '%s\n' "$out"
}

high_pane='› Ask Codex to do anything
  GPT-5.5 high · ~/worktree'
xhigh_pane='› Ask Codex to do anything
  GPT-5.5 xhigh · ~/worktree'

# --- Case: absent keys keep today's launch line ------------------------------
expect "no config file keeps today's launch line" "$today" "$(run_case "$read_fn" "$apply_fn" -)"
expect "config without the codex keys keeps today's launch line" "$today" \
  "$(run_case "$read_fn" "$apply_fn" '{"master_host_runtime": "claude"}')"
expect "null codex keys keep today's launch line" "$today" \
  "$(run_case "$read_fn" "$apply_fn" '{"codex_reasoning_effort": null, "codex_bypass_approvals_and_sandbox": null}')"
mutant=$(mutate "$read_fn" 'print(1 if bypass else 0)' 'print(1)')
got=$(run_case "$mutant" "$apply_fn" '{"master_host_runtime": "claude"}')
[ "$got" != "$today" ] || { echo "FAIL: failability: a bypass-by-default mutant still produced today's line" >&2; exit 1; }
echo "ok   : failability: defaulting the bypass on breaks the absent-key case"

# --- Case: a valid effort changes the launch line and the footer check -------
got=$(run_case "$read_fn" "$apply_fn" '{"codex_reasoning_effort": "high"}' "$high_pane")
expect "effort high changes the launch line and accepts a 'high' footer" "$high
footer-rc=0" "$got"
got=$(run_case "$read_fn" "$apply_fn" '{"codex_reasoning_effort": "high"}' "$xhigh_pane")
expect "effort high rejects an 'xhigh' footer" "$high
footer shows 'gpt-5.5 xhigh', requested 'gpt-5.5 high'
footer-rc=1" "$got"
mutant=$(mutate "$read_fn" '    effort = value' '    pass')
got=$(run_case "$mutant" "$apply_fn" '{"codex_reasoning_effort": "high"}' "$high_pane")
[ "$got" != "$high
footer-rc=0" ] || { echo "FAIL: failability: ignoring the configured effort still matched" >&2; exit 1; }
echo "ok   : failability: ignoring the configured effort breaks the high case"

# --- Case: bypass true appends the flag ---------------------------------------
expect "bypass true appends --dangerously-bypass-approvals-and-sandbox" "$bypass" \
  "$(run_case "$read_fn" "$apply_fn" '{"codex_bypass_approvals_and_sandbox": true}')"
expect "bypass false keeps today's launch line" "$today" \
  "$(run_case "$read_fn" "$apply_fn" '{"codex_bypass_approvals_and_sandbox": false}')"
mutant=$(mutate "$apply_fn" "CODEX_BYPASS_FLAG=' --dangerously-bypass-approvals-and-sandbox'" ':')
got=$(run_case "$read_fn" "$mutant" '{"codex_bypass_approvals_and_sandbox": true}')
[ "$got" != "$bypass" ] || { echo "FAIL: failability: dropping the flag assignment still produced the bypass line" >&2; exit 1; }
echo "ok   : failability: dropping the flag assignment breaks the bypass case"

# --- Case: invalid values are refused with exit 2 -----------------------------
refused() {  # label  json  want-substring  [read-fn]
  local out status
  run_case "${4:-$read_fn}" "$apply_fn" "$2" > "$work/out.txt"
  status=$?
  out=$(cat "$work/out.txt")
  case "$status:$out" in
    "2:✗ invalid codex launch setting"*"$3"*) echo "ok   : $1 · rc=$status";;
    *) echo "FAIL: $1 (rc=$status, out: $out)" >&2; return 1;;
  esac
}
set +e
refused "unknown effort is refused" '{"codex_reasoning_effort": "turbo"}' "'turbo'; expected one of" || exit 1
refused "non-string effort is refused" '{"codex_reasoning_effort": 5}' "5; expected one of" || exit 1
refused "non-boolean bypass is refused" '{"codex_bypass_approvals_and_sandbox": "yes"}' "expected true or false" || exit 1
mutant=$(mutate "$read_fn" ' or value not in efforts' '')
refused "mutant" '{"codex_reasoning_effort": "turbo"}' "expected one of" "$mutant" >/dev/null 2>&1
[ $? -ne 0 ] || { echo "FAIL: failability: dropping the effort allowlist still refused 'turbo'" >&2; exit 1; }
echo "ok   : failability: dropping the effort allowlist lets 'turbo' through"
set -e

echo "dispatch codex instance-config regression tests passed"
