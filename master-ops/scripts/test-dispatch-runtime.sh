#!/bin/bash
# Regression checks for dispatch: the static agy capability mapping, plus the
# three seat-ported features (multi-vendor hosts, check-only leaving the real
# ledger untouched, contract delivery). dispatch carries {{RUNTIME_ROOT}} and
# {{OPS_REPO}} template placeholders, so it cannot be executed end to end
# unrendered here — each feature case below extracts just its function or
# block by exact-line sed/awk range and runs that snippet in an isolated
# subshell with fakes on PATH or in $HOME, rather than invoking the whole
# script.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}
for pattern in \
  'agy:gemini' \
  "if runtime == 'agy': runtime = 'gemini'" \
  'agy) echo "agy --model $model_arg --dangerously-skip-permissions"'; do
  grep -Fq "$pattern" "$dispatch" || { echo "FAIL: missing dispatch pattern: $pattern" >&2; exit 1; }
done

probe_args_expansion_guard_test() {
  local target="$1" probe_expansion='"${MODEL_PROBE_ARGS[@]+"${MODEL_PROBE_ARGS[@]}"}"'
  if ! grep -Fq "$probe_expansion" "$target"; then
    echo "FAIL: missing guarded MODEL_PROBE_ARGS expansion in dispatch register call" >&2
    return 1
  fi

  /bin/bash -uc "set -u; MODEL_PROBE_ARGS=(); : $probe_expansion" >/dev/null 2>&1
}

probe_args_expansion_guard_test "$dispatch" || {
  echo "FAIL: MODEL_PROBE_ARGS expansion is not bash 3.2 set -u safe when empty" >&2
  exit 1
}
echo "dispatch agy capability regression test passed"

# --- Feature: multi-vendor hosts (cursor) -----------------------------------
#
# cursor-agent serves several vendors' model ids, so the mismatch check must
# validate a model against that host's own list instead of a vendor prefix.
# Extracts model_vendor, the MULTI_VENDOR_HOSTS/is_multi_vendor_host/
# host_model_ids block, runtime_accepts_vendor, and the if/elif branch that
# uses them, then runs that snippet against a fake cursor-agent on PATH.
cursor_multivendor_test() (
  set +e
  set -u
  local dispatch="$1" work model_vendor_fn multivendor_fns accepts_fn if_block
  local script_file out status mutant_fns

  model_vendor_fn=$(awk '$0=="model_vendor() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  multivendor_fns=$(awk '$0=="MULTI_VENDOR_HOSTS=\"cursor\""{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  accepts_fn=$(awk '$0=="runtime_accepts_vendor() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  if_block=$(awk '$0=="if is_multi_vendor_host \"$RUNTIME\"; then"{f=1} f{print} f&&$0=="fi"{exit}' "$dispatch")

  [ -n "$model_vendor_fn" ] || { echo "FAIL: could not extract model_vendor" >&2; return 1; }
  [ -n "$multivendor_fns" ] || { echo "FAIL: could not extract MULTI_VENDOR_HOSTS/is_multi_vendor_host/host_model_ids" >&2; return 1; }
  [ -n "$accepts_fn" ] || { echo "FAIL: could not extract runtime_accepts_vendor" >&2; return 1; }
  [ -n "$if_block" ] || { echo "FAIL: could not extract the multi-vendor mismatch-check branch" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-cursor-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/cursor-agent" <<'BIN'
#!/bin/bash
[ "$1" = models ] || exit 1
printf 'claude-opus-5-thinking-high - Anthropic\ngpt-5.3-codex - OpenAI\n'
BIN
  chmod +x "$work/cursor-agent"

  write_script() {
    local outfile="$1" fns="$2" branch="$3"
    {
      echo 'set -u'
      printf '%s\n' "$fns"
      printf '%s\n' "$accepts_fn"
      echo 'RUNTIME=cursor'
      echo 'MODEL=gpt-5.3-codex'
      echo 'POLICY=/dev/null'
      printf '%s\n' "$model_vendor_fn"
      echo 'MODEL_VENDOR=$(model_vendor "$MODEL")'
      printf '%s\n' "$branch"
      echo 'echo ACCEPTED'
    } > "$outfile"
  }

  script_file="$work/run.sh"
  write_script "$script_file" "$multivendor_fns" "$if_block"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?

  if [ "$status" -ne 0 ] || ! printf '%s\n' "$out" | grep -q '^ACCEPTED$'; then
    echo "FAIL: cursor multi-vendor host should accept gpt-5.3-codex from its own model list" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   — cursor accepts a model present in cursor-agent models output"

  # Failability: dropping cursor from MULTI_VENDOR_HOSTS falls back to the
  # single-vendor check, which rejects a model cursor legitimately offers.
  mutant_fns=${multivendor_fns/'MULTI_VENDOR_HOSTS="cursor"'/'MULTI_VENDOR_HOSTS=""'}
  if [ "$mutant_fns" = "$multivendor_fns" ]; then
    echo "FAIL: MULTI_VENDOR_HOSTS mutant did not change the source" >&2
    return 1
  fi
  write_script "$script_file" "$mutant_fns" "$if_block"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] && printf '%s\n' "$out" | grep -q '^ACCEPTED$'; then
    echo "FAIL: failability — mutant with cursor dropped from MULTI_VENDOR_HOSTS still accepted the model" >&2
    return 1
  fi
  echo "ok   — failability: dropping cursor from MULTI_VENDOR_HOSTS makes this case fail"
)
cursor_multivendor_test "$dispatch" || exit 1

# --- Feature: --check-only does not consume the fanout cap ------------------
#
# The template already meets this through dispatch-gate's own --no-record flag
# (record=not args.no_record) rather than the seat's GATE_LEDGER mktemp/cp/trap
# copy — the seat has not adopted --no-record yet, so it is behind here, not
# ahead; porting its copy mechanism would just be dead machinery next to the
# already-working one. This case guards the existing behaviour: extracts the
# TIER/top-approval/gate-check block through the --check-only exit path and
# runs it against a fake dispatch-gate that only appends to the ledger when
# called without --no-record.
checkonly_ledger_test() (
  set +e
  set -u
  local dispatch="$1" work jqf_fn tier_fn block
  local gate ledger policy contract script_file status before after out mutant_block

  jqf_fn=$(grep -m1 -F 'jqf() {' "$dispatch")
  tier_fn=$(awk '$0=="tier_for_model() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  block=$(awk '
    $0=="TIER=$(tier_for_model \"$MODEL\" 2>/dev/null || echo unknown)"{f=1}
    f{print}
    f && $0=="fi" && prev=="  exit 0"{exit}
    {prev=$0}
  ' "$dispatch")

  [ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; return 1; }
  [ -n "$tier_fn" ] || { echo "FAIL: could not extract tier_for_model" >&2; return 1; }
  [ -n "$block" ] || { echo "FAIL: could not extract the check-only gate block" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-checkonly-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  gate="$work/dispatch-gate"
  ledger="$work/ledger.jsonl"
  policy="$work/policy.json"
  contract="$work/contract.md"
  printf '{"tiers": {"efficient": [], "top": []}}\n' > "$policy"
  printf '# fake contract\n' > "$contract"
  cat > "$gate" <<'BIN'
#!/bin/bash
no_record=0
for a in "$@"; do [ "$a" = --no-record ] && no_record=1; done
if [ "$no_record" -eq 0 ]; then
  prev=""
  for a in "$@"; do
    [ "$prev" = --ledger ] && printf '{"kind":"recorded"}\n' >> "$a"
    prev=$a
  done
fi
printf '{"allow": true, "contract_sha": "abcdef0123456789"}\n'
BIN
  chmod +x "$gate"

  write_script() {
    local outfile="$1" body="$2"
    {
      echo 'set -u'
      printf '%s\n' "$jqf_fn"
      printf '%s\n' "$tier_fn"
      printf 'GATE=%s\n' "$gate"
      printf 'LEDGER=%s\n' "$ledger"
      printf 'POLICY=%s\n' "$policy"
      printf 'CONTRACT=%s\n' "$contract"
      echo 'RUNTIME=claude'
      echo 'MODEL=claude-haiku-4-5-20251001'
      echo 'EST=3000'
      echo 'TOP_APPROVED=""'
      echo 'CHECK_ONLY=1'
      echo 'COLLISION_CHECK=/bin/true'
      printf '%s\n' "$body"
    } > "$outfile"
  }

  script_file="$work/run.sh"
  printf '{"kind":"seed1"}\n{"kind":"seed2"}\n' > "$ledger"
  before=$(wc -l < "$ledger" | tr -d ' ')
  write_script "$script_file" "$block"
  out=$(bash "$script_file" 2>&1)
  status=$?
  after=$(wc -l < "$ledger" | tr -d ' ')

  if [ "$status" -ne 0 ]; then
    echo "FAIL: check-only gate block exited non-zero (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if [ "$before" -ne "$after" ]; then
    echo "FAIL: --check-only changed the real ledger's line count ($before -> $after)" >&2
    return 1
  fi
  echo "ok   — --check-only leaves the real ledger's line count unchanged"

  # Failability: if dispatch stopped passing --no-record under --check-only,
  # this fake gate would append to the real ledger and the case above would fail.
  mutant_block=${block/'"${GATE_ARGS[@]}" --no-record'/'"${GATE_ARGS[@]}"'}
  if [ "$mutant_block" = "$block" ]; then
    echo "FAIL: --no-record mutant did not change the source" >&2
    return 1
  fi
  printf '{"kind":"seed1"}\n{"kind":"seed2"}\n' > "$ledger"
  before=$(wc -l < "$ledger" | tr -d ' ')
  write_script "$script_file" "$mutant_block"
  bash "$script_file" >/dev/null 2>&1 || true
  after=$(wc -l < "$ledger" | tr -d ' ')
  if [ "$before" -eq "$after" ]; then
    echo "FAIL: failability — dropping --no-record under --check-only should have consumed ledger budget" >&2
    return 1
  fi
  echo "ok   — failability: dropping --no-record under --check-only would consume the fanout cap"
)
checkonly_ledger_test "$dispatch" || exit 1

# --- Feature: contract delivery ---------------------------------------------
#
# Extracts the `if [ -n "$CONTRACT" ]; then ... fi` block that copies the
# contract to $HOME/.mogui/dispatch-contracts/<sha8>-<name>, appends the
# acknowledgement token, and writes the delivered path into $SPEC, then runs
# it against a fake $HOME.
contract_delivery_test() (
  set +e
  set -u
  local dispatch="$1" work block contract fake_home sha script_file
  local out status dest token_line_no mutant_block spec_tail

  block=$(awk '$0=="if [ -n \"$CONTRACT\" ]; then"{f=1} f{print} f&&$0=="fi"{exit}' "$dispatch")
  [ -n "$block" ] || { echo "FAIL: could not extract the contract delivery block" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-contract-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  contract="$work/src-contract.md"
  printf '# fake contract\n\nbody text\n' > "$contract"
  fake_home="$work/home"
  mkdir -p "$fake_home"
  sha="abcdef0123456789beef"
  dest="$fake_home/.mogui/dispatch-contracts/${sha:0:8}-$(basename "$contract")"

  write_script() {
    local outfile="$1" body="$2"
    {
      echo 'set -u'
      printf 'CONTRACT=%s\n' "$contract"
      printf 'SHA=%s\n' "$sha"
      echo 'SPEC="original spec"'
      printf '%s\n' "$body"
      echo 'printf "SPEC_TAIL::%s\n" "$SPEC"'
    } > "$outfile"
  }

  script_file="$work/run.sh"
  write_script "$script_file" "$block"
  out=$(HOME="$fake_home" bash "$script_file" 2>&1)
  status=$?

  if [ "$status" -ne 0 ]; then
    echo "FAIL: contract delivery block exited non-zero" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if [ ! -f "$dest" ]; then
    echo "FAIL: contract was not delivered to $dest" >&2
    return 1
  fi
  if ! grep -q '^## Acknowledgement token$' "$dest"; then
    echo "FAIL: delivered contract is missing the acknowledgement token section" >&2
    return 1
  fi
  if ! grep -q '^    ack-' "$dest"; then
    echo "FAIL: delivered contract has no ack-<token> line" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -q 'contract delivered .* read-token required'; then
    echo "FAIL: dispatch did not print the contract-delivered confirmation line" >&2
    return 1
  fi
  # Match only inside the SPEC_TAIL:: marker's own output: $dest also appears in
  # the "contract delivered" confirmation line above, so matching against all of
  # $out would pass even if the path were never written into $SPEC.
  spec_tail=$(printf '%s\n' "$out" | awk '/^SPEC_TAIL::/{f=1} f{print}')
  if [ -z "$spec_tail" ]; then
    echo "FAIL: dispatch output has no SPEC_TAIL:: marker" >&2
    return 1
  fi
  if ! printf '%s\n' "$spec_tail" | grep -qF "$dest"; then
    echo "FAIL: delivered contract path was not written into the spec" >&2
    return 1
  fi
  echo "ok   — --contract delivers the file with an acknowledgement token and updates the spec"

  # Failability: drop the line that appends the token value; the delivered
  # file then has the token section but no ack-<token> line.
  token_line_no=$(printf '%s\n' "$block" | grep -Fn 'READ_TOKEN"' | head -1 | cut -d: -f1)
  [ -n "$token_line_no" ] || { echo "FAIL: could not locate the token-append line to mutate" >&2; return 1; }
  mutant_block=$(printf '%s\n' "$block" | sed "${token_line_no}d")
  if [ "$mutant_block" = "$block" ]; then
    echo "FAIL: read-token mutant did not change the source" >&2
    return 1
  fi
  rm -rf "$fake_home"
  mkdir -p "$fake_home"
  write_script "$script_file" "$mutant_block"
  HOME="$fake_home" bash "$script_file" >/dev/null 2>&1 || true
  if [ -f "$dest" ] && grep -q '^    ack-' "$dest"; then
    echo "FAIL: failability — mutant should have produced a delivered file without the ack-<token> line" >&2
    return 1
  fi
  echo "ok   — failability: dropping the token-append line leaves the delivered file without ack-<token>"
)
contract_delivery_test "$dispatch" || exit 1

# --- Feature: cursor pre-trust before launch --------------------------------
#
# Cursor Agent's launch flags (--force --trust) cover the approval/permission
# prompt but not the first-visit workspace-trust prompt (charter's
# dispatch-gate and worker-routing-review docs), so dispatch must run
# scripts/cursor-worker-pretrust before a cursor launch and fail closed on a
# skipped summary, the same way ensure_codex_pretrust does for codex. Extracts
# ensure_cursor_pretrust and runs it against a fake cursor-worker-pretrust.
cursor_pretrust_test() (
  set +e
  set -u
  local dispatch="$1" work fn script_file out status mutant_fn

  fn=$(awk '$0=="ensure_cursor_pretrust() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  [ -n "$fn" ] || { echo "FAIL: could not extract ensure_cursor_pretrust" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-cursor-pretrust-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/cursor-worker-pretrust" <<'BIN'
#!/bin/bash
printf '%s/.workspace-trusted: already trusted\n' "$1"
printf 'Summary: 0 added, 0 updated, 1 already trusted\n'
BIN
  chmod +x "$work/cursor-worker-pretrust"

  write_script() {
    local outfile="$1" body="$2"
    {
      echo 'set -u'
      printf 'CURSOR_PRETRUST_BIN=%s\n' "$work/cursor-worker-pretrust"
      printf '%s\n' "$body"
      printf 'ensure_cursor_pretrust cursor %s && echo TRUSTED\n' "$work"
    } > "$outfile"
  }

  script_file="$work/run.sh"
  write_script "$script_file" "$fn"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || ! printf '%s\n' "$out" | grep -q '^TRUSTED$' \
      || ! printf '%s\n' "$out" | grep -q 'pre-trust ✓ cursor'; then
    echo "FAIL: ensure_cursor_pretrust should succeed against a fake pre-trust binary reporting a trusted summary" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   — ensure_cursor_pretrust succeeds against a fake cursor-worker-pretrust reporting a trusted summary"

  # A skipped summary must fail closed: it leaves the trust prompt in place.
  cat > "$work/cursor-worker-pretrust" <<'BIN'
#!/bin/bash
printf 'SKIP no python3 found\n'
printf 'Summary: skipped — 0 added, 0 updated, 0 already trusted\n'
BIN
  chmod +x "$work/cursor-worker-pretrust"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "FAIL: ensure_cursor_pretrust should fail closed on a skipped pre-trust summary" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   — ensure_cursor_pretrust fails closed on a skipped pre-trust summary"

  # Failability: if the *skipped*) case stopped matching, a worktree the
  # pretrust binary could not actually trust would still be launched into.
  mutant_fn=${fn/'*skipped*)'/'*nevermatches*)'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: skipped-case mutant did not change the source" >&2
    return 1
  fi
  write_script "$script_file" "$mutant_fn"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || ! printf '%s\n' "$out" | grep -q '^TRUSTED$'; then
    echo "FAIL: failability — mutant dropping the *skipped*) case should have wrongly succeeded, but still failed closed" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   — failability: dropping the *skipped*) case makes the fail-closed assertion above fail"
)
cursor_pretrust_test "$dispatch" || exit 1

# --- Feature: codex launch flags ---------------------------------------------
#
# 2026-10-01: a bare `codex --model <id>` opened a model-retirement migration
# menu with "Try new model" preselected, and the injected spec's first
# keystroke confirmed it. Extracts shell_quote, runtime_command, and the two
# launch-flag variables, then compares the codex case's output against the
# exact string the three added -c flags must produce.
codex_launch_flags_test() (
  set +e
  set -u
  local dispatch="$1" work shell_quote_fn runtime_command_fn vars want got mutant_fn out status

  shell_quote_fn=$(awk '$0=="shell_quote() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  runtime_command_fn=$(awk '$0=="runtime_command() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  vars=$(grep -E '^CODEX_(REASONING_EFFORT|MIGRATION_ACK)=' "$dispatch")

  [ -n "$shell_quote_fn" ] || { echo "FAIL: could not extract shell_quote" >&2; return 1; }
  [ -n "$runtime_command_fn" ] || { echo "FAIL: could not extract runtime_command" >&2; return 1; }
  [ "$(printf '%s\n' "$vars" | grep -c .)" = 2 ] || { echo "FAIL: could not extract both CODEX_ launch variables" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-launch-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT

  write_script() {
    local outfile="$1" fn="$2"
    {
      echo 'set -u'
      printf '%s\n' "$vars"
      printf '%s\n' "$shell_quote_fn"
      printf '%s\n' "$fn"
      echo 'MODEL=gpt-5.5'
      echo 'runtime_command codex'
    } > "$outfile"
  }

  want='codex --model gpt-5.5 -c '"'"'model_reasoning_effort="xhigh"'"'"' -c check_for_update_on_startup=false -c '"'"'notice.model_migrations={"gpt-5.5"="gpt-6.1-sol"}'"'"''

  script_file="$work/run.sh"
  write_script "$script_file" "$runtime_command_fn"
  got=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ "$got" != "$want" ]; then
    echo "FAIL: codex launch command is '$got' (status=$status)" >&2
    echo "  want '$want'" >&2
    return 1
  fi
  echo "ok   : codex launch carries --model, reasoning effort, update-check off, and the migration ack · rc=0"

  # Failability: dropping check_for_update_on_startup=false must break the exact-string match.
  mutant_fn=${runtime_command_fn/' -c check_for_update_on_startup=false'/}
  if [ "$mutant_fn" = "$runtime_command_fn" ]; then
    echo "FAIL: launch-flag mutant did not change the source" >&2
    return 1
  fi
  write_script "$script_file" "$mutant_fn"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] && [ "$out" = "$want" ]; then
    echo "FAIL: failability: mutant dropping check_for_update_on_startup=false still produced the exact wanted string" >&2
    return 1
  fi
  echo "ok   : failability: dropping check_for_update_on_startup=false breaks the exact-string match (mutant rc=$status)"
)
codex_launch_flags_test "$dispatch" || exit 1

# --- Feature: codex start-screen check before inject -------------------------
#
# 2026-10-01: a codex pane sitting on that migration menu, a folder-trust
# prompt, or a provider-limit notice reports idle exactly like a ready prompt.
# `terminal wait --for tui-idle` cannot tell them apart, only the footer
# line "<model> <effort> · <path>" can. Extracts codex_start_screen_problem
# and the LIMIT_MARKERS it reuses, then runs it against the pane tails read
# that day (ready, mismatched footer, update notice, provider limit, the
# migration menu) plus an empty pane, checking both the returned exit code
# and the printed reason. One mutant per check inside the function, each
# breaking only the case it guards.
codex_start_screen_test() (
  set +e
  set -u
  local dispatch="$1" work fn markers ready mismatched update limit menu

  fn=$(awk '$0=="codex_start_screen_problem() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  markers=$(grep -E '^LIMIT_MARKERS=' "$dispatch")
  [ -n "$fn" ] || { echo "FAIL: could not extract codex_start_screen_problem" >&2; return 1; }
  [ -n "$markers" ] || { echo "FAIL: could not extract LIMIT_MARKERS" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-start-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT

  run_case() {  # fn-body  pane-text
    local body="$1" pane="$2" script_file="$work/case.sh"
    {
      echo 'set -u'
      printf '%s\n' "$markers"
      printf '%s\n' "$body"
      printf 'codex_start_screen_problem "$1" gpt-5.5 xhigh\n'
    } > "$script_file"
    bash "$script_file" "$pane"
  }

  ready='› Ask Codex to do anything
  GPT-5.5 xhigh · ~/worktree
  ? for shortcuts                                   ⚠ 1 warning · f2 to view'
  mismatched='Model changed to gpt-6.1-sol medium
› Ask Codex to do anything
  GPT-6.1-Sol medium · ~/worktree'
  update='Update available!'
  limit="out of credits
$ready"
  menu='  GPT-5.5 retires on October 14, 2026. Switch to GPT-6.1 Sol to continue working in Codex.
› 1. Try new model
  2. Use existing model
  enter/esc confirm · ctrl+c quit'

  assert_case() {  # label  want-rc  want-substring  pane
    local label="$1" want_rc="$2" want_sub="$3" pane="$4" out rc
    out=$(run_case "$fn" "$pane")
    rc=$?
    if [ "$rc" != "$want_rc" ]; then
      echo "FAIL: case $label expected rc $want_rc, got $rc (out: $out)" >&2
      return 1
    fi
    case "$out" in
      *"$want_sub"*) ;;
      *) echo "FAIL: case $label output '$out' lacks '$want_sub'" >&2; return 1;;
    esac
    echo "ok   : case $label · rc=$rc"
  }

  assert_case ready "0" "" "  >_ OpenAI Codex (v0.159.3)
$ready" || return 1
  assert_case footer-mismatch "1" "requested 'gpt-5.5 xhigh'" "$mismatched" || return 1
  assert_case update "1" "update notice" "$update" || return 1
  assert_case limit "1" "provider limit notice" "$limit" || return 1
  assert_case menu "1" "Try new model" "$menu" || return 1
  assert_case no-footer "2" "no model footer yet" "" || return 1

  mutate_line() {  # unique-substring-of-target-line  replacement-line
    local needle="$1" repl="$2" line out="" replaced=0
    while IFS= read -r line; do
      case "$line" in
        *"$needle"*) line="$repl"; replaced=1;;
      esac
      out="$out$line
"
    done <<EOF
$fn
EOF
    [ "$replaced" -eq 1 ] || return 1
    printf '%s' "$out"
  }

  failability_case() {  # label  needle  replacement-line  pane  blocked-rc
    local label="$1" needle="$2" repl="$3" pane="$4" blocked_rc="$5" mutant out rc
    mutant=$(mutate_line "$needle" "$repl") || { echo "FAIL: $label needle not found in function body" >&2; return 1; }
    if [ "$mutant" = "$fn" ]; then
      echo "FAIL: $label mutant did not change the source" >&2
      return 1
    fi
    out=$(run_case "$mutant" "$pane")
    rc=$?
    if [ "$rc" = "$blocked_rc" ]; then
      echo "FAIL: failability: $label mutant still returns $blocked_rc" >&2
      return 1
    fi
    echo "ok   : failability: $label mutant changes rc $blocked_rc -> $rc"
  }

  failability_case limit-marker 'grep -Eiq "$LIMIT_MARKERS"' \
    '  if printf "%s\n" "$state" | grep -Eiq "zz-never-matches-zz"; then' \
    "$limit" "1" || return 1
  failability_case update-phrase "grep -Eiq 'update available'" \
    '  if printf "%s\n" "$state" | grep -Eiq "zz-never-matches-zz"; then' \
    "$update" "1" || return 1
  failability_case menu-pattern "grep -Eq '^[[:space:]]*›[[:space:]]*[0-9]+\\.'; then" \
    '  if printf "%s\n" "$state" | grep -Eq "zz-never-matches-zz"; then' \
    "$menu" "1" || return 1
  failability_case no-footer-yet '[ -z "$footer" ]' \
    '  if [ -z "zz-never-empty-zz" ]; then' \
    "" "2" || return 1
  failability_case footer-mismatch-compare '[ "$shown" != "$want" ]' \
    '  if [ "$shown" = "$want" ]; then' \
    "$mismatched" "1" || return 1
)
codex_start_screen_test "$dispatch" || exit 1

# --- Feature: codex start-screen check actually gates --inject -------------
#
# The case-level test above proves codex_start_screen_problem classifies a
# pane correctly; it does not prove the wrapper acts on that classification.
# Extracts the call site itself (from the `if [ "$RUNTIME" = codex ]` guard
# through the `--inject` call and its own failure check) and runs it against
# a fake `orca` that records whether `orchestration dispatch --inject` was
# ever reached. A migration-menu pane must never reach it; a ready pane must.
codex_start_screen_wiring_test() (
  set +e
  set -u
  local dispatch="$1" work jqf_fn pane_classification_fn start_fn markers wiring_block
  local menu ready script_file out status

  jqf_fn=$(grep -m1 -F 'jqf() {' "$dispatch")
  pane_classification_fn=$(awk '$0=="pane_classification() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  start_fn=$(awk '$0=="codex_start_screen_problem() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  markers=$(grep -E '^(LIMIT_MARKERS|HOOK_TRUST_MARKERS|PREPARED_PROMPT_MARKERS|PREPARED_UNICODE_PROMPT_MARKERS)=' "$dispatch")
  wiring_block=$(awk '
    $0=="if [ \"$RUNTIME\" = codex ]; then"{f=1}
    f{print}
    f && /dispatch failed/{exit}
  ' "$dispatch")

  [ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; return 1; }
  [ -n "$pane_classification_fn" ] || { echo "FAIL: could not extract pane_classification" >&2; return 1; }
  [ -n "$start_fn" ] || { echo "FAIL: could not extract codex_start_screen_problem" >&2; return 1; }
  [ -n "$wiring_block" ] || { echo "FAIL: could not extract the codex start-screen wiring block" >&2; return 1; }
  printf '%s\n' "$wiring_block" | grep -Fq 'codex_start_screen_problem' || { echo "FAIL: extracted block does not call codex_start_screen_problem" >&2; return 1; }
  printf '%s\n' "$wiring_block" | grep -Fq 'orca orchestration dispatch' || { echo "FAIL: extracted block does not reach the inject call" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-codex-wiring-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT

  cat > "$work/orca" <<'BIN'
#!/bin/bash
if [ "$1 $2" = "terminal read" ]; then
  cat "$FAKE_PANE_FILE"
  exit 0
fi
if [ "$1 $2" = "orchestration dispatch" ]; then
  echo INJECTED >> "$FAKE_MARKER"
  printf '{"result":{"dispatch":{"id":"disp_fake"}}}\n'
  exit 0
fi
exit 1
BIN
  chmod +x "$work/orca"

  write_script() {
    local outfile="$1" body="$2" pane="$3"
    printf '%s\n' "$pane" > "$work/pane.txt"
    {
      echo 'set -u'
      printf 'export FAKE_MARKER=%s\n' "$work/injected"
      printf 'export FAKE_PANE_FILE=%s\n' "$work/pane.txt"
      printf '%s\n' "$jqf_fn"
      printf '%s\n' "$markers"
      printf '%s\n' "$pane_classification_fn"
      printf '%s\n' "$start_fn"
      echo 'RUNTIME=codex'
      echo 'MODEL=gpt-5.5'
      echo 'CODEX_REASONING_EFFORT=xhigh'
      echo 'TERMINAL=term_fake'
      echo 'TASK=task_fake'
      printf '%s\n' "$body"
      echo 'echo WIRING_SURVIVED'
    } > "$outfile"
  }

  menu='  GPT-5.5 retires on October 14, 2026. Switch to GPT-6.1 Sol to continue working in Codex.
› 1. Try new model
  2. Use existing model
  enter/esc confirm · ctrl+c quit'
  ready='› Ask Codex to do anything
  GPT-5.5 xhigh · ~/worktree
  ? for shortcuts                                   ⚠ 1 warning · f2 to view'

  script_file="$work/run.sh"
  rm -f "$work/injected"
  write_script "$script_file" "$wiring_block" "$menu"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] || [ -f "$work/injected" ]; then
    echo "FAIL: a migration-menu codex pane should exit nonzero and never reach --inject (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a migration-menu codex pane never reaches orca orchestration dispatch --inject"

  rm -f "$work/injected"
  write_script "$script_file" "$wiring_block" "$ready"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ ! -f "$work/injected" ] || ! printf '%s\n' "$out" | grep -q '^WIRING_SURVIVED$'; then
    echo "FAIL: a ready codex pane should reach --inject and fall through the wiring block" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a ready codex pane reaches orca orchestration dispatch --inject"

  # Failability: a copy of the wiring block whose gate conditional is disabled
  # (the shape of a guard caller silently dropped from the wrapper) must
  # still inject even on a migration-menu pane.
  mutant_wiring=${wiring_block/'if [ "$CODEX_START_RC" != 0 ]; then'/'if false; then'}
  if [ "$mutant_wiring" = "$wiring_block" ]; then
    echo "FAIL: gate-disabled mutant did not change the source" >&2
    return 1
  fi
  rm -f "$work/injected"
  write_script "$script_file" "$mutant_wiring" "$menu"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] && [ ! -f "$work/injected" ]; then
    echo "FAIL: failability: gate-disabled mutant should have injected on a migration-menu pane, but still didn't" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: disabling the gate conditional injects on a migration-menu pane (status=$status, injected=$([ -f "$work/injected" ] && echo yes || echo no))"
)
codex_start_screen_wiring_test "$dispatch" || exit 1

# --- Feature: codex_hooks_vet -------------------------------------------------
#
# 2026-10-01: codex's "Hooks need review" modal is answerable under dispatch
# authority only once the hooks it would trust are read, not just trusted on
# faith. Extracts codex_hooks_vet and runs it against fixture hooks.json
# files shaped like the real file measured on this host (top-level "hooks",
# per-event arrays of {matcher, hooks:[{command}]}): one with only
# already-resolvable commands, one with a builtin first word, one with a
# missing absolute path, one with a first word not on PATH, one with a
# malformed event shape, and one home with no hooks.json at all. The
# badpath/badword fixtures carry a valid hook in an earlier event before the
# invalid one, so a vet that stops checking after the first event or the
# first command would still pass them.
codex_hooks_vet_test() (
  set +e
  set -u
  local dispatch="$1" work fn

  fn=$(awk '$0=="codex_hooks_vet() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  [ -n "$fn" ] || { echo "FAIL: could not extract codex_hooks_vet" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-hooks-vet-test.$$"
  mkdir -p "$work/pass" "$work/builtin" "$work/badpath" "$work/badword" "$work/badshape" "$work/missing"
  trap 'rm -rf "$work"' EXIT

  cat > "$work/pass/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
EOF
  cat > "$work/builtin/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "cd /tmp && echo hi"}]}]}}
EOF
  cat > "$work/badpath/hooks.json" <<'EOF'
{"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}], "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "/no/such/binary --flag"}]}]}}
EOF
  cat > "$work/badword/hooks.json" <<'EOF'
{"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}], "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "zz-mogui-never-on-path --flag"}]}]}}
EOF
  cat > "$work/badshape/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": {}}}
EOF

  run_case() {  # fn-body  home-dir
    local body="$1" home="$2" script_file="$work/case.sh"
    {
      echo 'set -u'
      printf '%s\n' "$body"
      printf 'codex_hooks_vet "$1"\n'
    } > "$script_file"
    bash "$script_file" "$home"
  }

  assert_case() {  # label  want-rc  want-substring  home
    local label="$1" want_rc="$2" want_sub="$3" home="$4" out rc
    out=$(run_case "$fn" "$home")
    rc=$?
    if [ "$rc" != "$want_rc" ]; then
      echo "FAIL: case $label expected rc $want_rc, got $rc (out: $out)" >&2
      return 1
    fi
    case "$out" in
      *"$want_sub"*) ;;
      *) echo "FAIL: case $label output '$out' lacks '$want_sub'" >&2; return 1;;
    esac
    echo "ok   : case $label · rc=$rc"
  }

  assert_case all-local "0" "command(s) checked" "$work/pass" || return 1
  assert_case builtin-first-word "0" "command(s) checked" "$work/builtin" || return 1
  assert_case bad-abs-path "1" "/no/such/binary: no such file" "$work/badpath" || return 1
  assert_case bad-path-word "1" "zz-mogui-never-on-path: not found on PATH" "$work/badword" || return 1
  assert_case bad-event-shape "1" "wrong shape" "$work/badshape" || return 1
  assert_case missing-hooks-json "2" "not found" "$work/missing" || return 1

  mutate_line() {  # unique-substring-of-target-line  replacement-line
    local needle="$1" repl="$2" line out="" replaced=0
    while IFS= read -r line; do
      case "$line" in
        *"$needle"*) line="$repl"; replaced=1;;
      esac
      out="$out$line
"
    done <<EOF
$fn
EOF
    [ "$replaced" -eq 1 ] || return 1
    printf '%s' "$out"
  }

  failability_case() {  # label  needle  replacement-line  home  blocked-rc
    local label="$1" needle="$2" repl="$3" home="$4" blocked_rc="$5" mutant out rc
    mutant=$(mutate_line "$needle" "$repl") || { echo "FAIL: $label needle not found in function body" >&2; return 1; }
    if [ "$mutant" = "$fn" ]; then
      echo "FAIL: $label mutant did not change the source" >&2
      return 1
    fi
    out=$(run_case "$mutant" "$home")
    rc=$?
    if [ "$rc" = "$blocked_rc" ]; then
      echo "FAIL: failability: $label mutant still returns $blocked_rc" >&2
      return 1
    fi
    echo "ok   : failability: $label mutant changes rc $blocked_rc -> $rc"
  }

  failability_case abs-path-check \
    '                if token.startswith("/") and not os.path.exists(token):' \
    '                if False:' \
    "$work/badpath" "1" || return 1
  failability_case path-word-check \
    '                if shutil.which(first) is None:' \
    '                if False:' \
    "$work/badword" "1" || return 1
  failability_case missing-file-check \
    '    print(f"hooks-vet: {path}: not found")' \
    '    sys.exit(0)' \
    "$work/missing" "2" || return 1
  failability_case entries-shape-check \
    '    if not isinstance(entries, list):' \
    '    if False:' \
    "$work/badshape" "1" || return 1
  failability_case early-stop \
    '            checked += 1' \
    '            checked += 1
            sys.exit(0)' \
    "$work/badpath" "1" || return 1
)
codex_hooks_vet_test "$dispatch" || exit 1

# --- Feature: HOOKS_ANSWER_BIN resolves beside the wrapper -----------------
#
# Round two of PR #157: the wrapper pointed HOOKS_ANSWER_BIN at
# {{RUNTIME_ROOT}}/scripts/codex-hooks-review-answer, a path no install has;
# the tool ships in the same directory as the wrapper itself. Extracts the
# HOOKS_ANSWER_BIN assignment and evaluates it with SCRIPTS_DIR set to the
# wrapper's real directory, then to an empty temp directory, to prove the
# assignment tracks SCRIPTS_DIR.
hooks_answer_bin_path_test() (
  set +e
  set -u
  local dispatch="$1" assign real_dir empty_dir script_file out rc

  assign=$(grep -E '^HOOKS_ANSWER_BIN=' "$dispatch")
  [ -n "$assign" ] || { echo "FAIL: could not extract HOOKS_ANSWER_BIN assignment" >&2; return 1; }

  script_file="${TMPDIR:-/tmp}/mogui-dispatch-hooks-answer-bin-test.$$.sh"
  trap 'rm -f "$script_file"' EXIT
  {
    echo 'set -u'
    printf '%s\n' "$assign"
    echo '[ -x "$HOOKS_ANSWER_BIN" ] && printf "%s\n" "$HOOKS_ANSWER_BIN"'
  } > "$script_file"

  real_dir=$(cd "$(dirname "$dispatch")" && pwd)
  out=$(SCRIPTS_DIR="$real_dir" bash "$script_file")
  rc=$?
  if [ "$rc" != 0 ] || [ "$out" != "$real_dir/codex-hooks-review-answer" ]; then
    echo "FAIL: HOOKS_ANSWER_BIN did not resolve to $real_dir/codex-hooks-review-answer under the wrapper's real SCRIPTS_DIR" >&2
    return 1
  fi
  echo "ok   : HOOKS_ANSWER_BIN resolves to $real_dir/codex-hooks-review-answer under the real SCRIPTS_DIR"

  empty_dir="${TMPDIR:-/tmp}/mogui-dispatch-hooks-answer-bin-empty.$$"
  mkdir -p "$empty_dir"
  out=$(SCRIPTS_DIR="$empty_dir" bash "$script_file")
  rc=$?
  rm -rf "$empty_dir"
  if [ "$rc" -eq 0 ]; then
    echo "FAIL: failability: an empty SCRIPTS_DIR should not resolve HOOKS_ANSWER_BIN to an executable, but the check passed" >&2
    return 1
  fi
  echo "ok   : failability: an empty SCRIPTS_DIR fails the existence check (rc=$rc)"
)
hooks_answer_bin_path_test "$dispatch" || exit 1

# --- Feature: hooks-review modal answered only after a vetted pass ---------
#
# 2026-10-01: PR #156 made codex_start_screen_problem read the "Hooks need
# review" modal as a selection menu and take the exit-3 path, same as any
# other menu it cannot act on, closing the door codex-hooks-review-answer
# (shipped in PR #133) was meant to open. Extracts the 3b wiring block plus
# codex_hooks_vet_homes/codex_hooks_homes/codex_accounts_dir/codex_hooks_vet
# and HOOKS_ANSWER_BIN, and runs it against a fake orca (terminal read
# returns the hooks-review pane once, then a ready pane), a fake answer
# tool, and a fake $HOME whose .codex/hooks.json either passes or fails the
# vet.
codex_hooks_vet_wiring_test() (
  set +e
  set -u
  local dispatch="$1" work jqf_fn pane_classification_fn start_fn markers wiring_block
  local vet_fn homes_fn accounts_fn vet_homes_fn hooks_answer_var
  local menu ready script_file out status mutant_wiring
  local mutant_homes homes_fn_saved

  jqf_fn=$(grep -m1 -F 'jqf() {' "$dispatch")
  pane_classification_fn=$(awk '$0=="pane_classification() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  start_fn=$(awk '$0=="codex_start_screen_problem() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  markers=$(grep -E '^(LIMIT_MARKERS|HOOK_TRUST_MARKERS|PREPARED_PROMPT_MARKERS|PREPARED_UNICODE_PROMPT_MARKERS)=' "$dispatch")
  accounts_fn=$(awk '$0=="codex_accounts_dir() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  homes_fn=$(awk '$0=="codex_hooks_homes() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  vet_fn=$(awk '$0=="codex_hooks_vet() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  vet_homes_fn=$(awk '$0=="codex_hooks_vet_homes() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  hooks_answer_var=$(grep -E '^HOOKS_ANSWER_BIN=' "$dispatch")
  wiring_block=$(awk '
    $0=="if [ \"$RUNTIME\" = codex ]; then"{f=1}
    f{print}
    f && /dispatch failed/{exit}
  ' "$dispatch")

  [ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; return 1; }
  [ -n "$pane_classification_fn" ] || { echo "FAIL: could not extract pane_classification" >&2; return 1; }
  [ -n "$start_fn" ] || { echo "FAIL: could not extract codex_start_screen_problem" >&2; return 1; }
  [ -n "$accounts_fn" ] || { echo "FAIL: could not extract codex_accounts_dir" >&2; return 1; }
  [ -n "$homes_fn" ] || { echo "FAIL: could not extract codex_hooks_homes" >&2; return 1; }
  [ -n "$vet_fn" ] || { echo "FAIL: could not extract codex_hooks_vet" >&2; return 1; }
  [ -n "$vet_homes_fn" ] || { echo "FAIL: could not extract codex_hooks_vet_homes" >&2; return 1; }
  [ -n "$hooks_answer_var" ] || { echo "FAIL: could not extract HOOKS_ANSWER_BIN" >&2; return 1; }
  [ -n "$wiring_block" ] || { echo "FAIL: could not extract the codex start-screen wiring block" >&2; return 1; }
  printf '%s\n' "$wiring_block" | grep -Fq 'codex_hooks_vet_homes' || { echo "FAIL: extracted block does not call codex_hooks_vet_homes" >&2; return 1; }
  printf '%s\n' "$wiring_block" | grep -Fq '"$HOOKS_ANSWER_BIN"' || { echo "FAIL: extracted block does not call HOOKS_ANSWER_BIN" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-hooks-wiring-test.$$"
  mkdir -p "$work/fakehome-pass/.codex" "$work/fakehome-fail/.codex"
  trap 'rm -rf "$work"' EXIT

  cat > "$work/fakehome-pass/.codex/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
EOF
  cat > "$work/fakehome-fail/.codex/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "/no/such/binary"}]}]}}
EOF

  cat > "$work/orca" <<'BIN'
#!/bin/bash
if [ "$1 $2" = "terminal read" ]; then
  n=$(( $(cat "$FAKE_READ_COUNT" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$FAKE_READ_COUNT"
  if [ "$n" -eq 1 ]; then cat "$FAKE_PANE_FILE"; else cat "$FAKE_READY_PANE_FILE"; fi
  exit 0
fi
if [ "$1 $2" = "orchestration dispatch" ]; then
  echo INJECTED >> "$FAKE_MARKER"
  printf '{"result":{"dispatch":{"id":"disp_fake"}}}\n'
  exit 0
fi
exit 1
BIN
  chmod +x "$work/orca"

  cat > "$work/fake-hooks-answer" <<'BIN'
#!/bin/bash
echo ANSWERED >> "$FAKE_ANSWER_MARKER"
echo "hooks-review ✓ codex · trusted 1 new/changed hook(s) by dispatch authority (charter §4)"
exit 0
BIN
  chmod +x "$work/fake-hooks-answer"

  menu='Hooks need review
4 hooks are new or changed
› 1. Review hooks
  2. Trust all and continue
  3. Continue without trusting'
  ready='› Ask Codex to do anything
  GPT-5.5 xhigh · ~/worktree
  ? for shortcuts                                   ⚠ 1 warning · f2 to view'
  printf '%s\n' "$menu" > "$work/pane.txt"
  printf '%s\n' "$ready" > "$work/ready.txt"

  write_script() {  # outfile  home  wiring-text  [hooks-answer-bin]  [accounts-dir]  [worktree]
    local outfile="$1" home="$2" wiring_text="$3" hooks_answer_bin="${4:-$work/fake-hooks-answer}"
    local accounts_dir="${5:-$work/no-accounts-dir}" worktree="${6:-}"
    {
      echo 'set -u'
      printf 'export FAKE_MARKER=%s\n' "$work/injected"
      printf 'export FAKE_ANSWER_MARKER=%s\n' "$work/answered"
      printf 'export FAKE_READ_COUNT=%s\n' "$work/read-count"
      printf 'export FAKE_PANE_FILE=%s\n' "$work/pane.txt"
      printf 'export FAKE_READY_PANE_FILE=%s\n' "$work/ready.txt"
      printf '%s\n' "$jqf_fn"
      printf '%s\n' "$markers"
      printf '%s\n' "$pane_classification_fn"
      printf '%s\n' "$start_fn"
      printf '%s\n' "$accounts_fn"
      printf '%s\n' "$homes_fn"
      printf '%s\n' "$vet_fn"
      printf '%s\n' "$vet_homes_fn"
      echo 'RUNTIME=codex'
      echo 'MODEL=gpt-5.5'
      echo 'CODEX_REASONING_EFFORT=xhigh'
      echo 'TERMINAL=term_fake'
      echo 'TASK=task_fake'
      printf 'HOME=%s\n' "$home"
      printf 'CODEX_ACCOUNTS_DIR=%s\n' "$accounts_dir"
      printf 'WORKTREE=%s\n' "$worktree"
      printf 'HOOKS_ANSWER_BIN=%s\n' "$hooks_answer_bin"
      printf '%s\n' "$wiring_text"
      echo 'echo WIRING_SURVIVED'
    } > "$outfile"
  }

  script_file="$work/run.sh"

  # Vet passes: the modal is answered, dispatch --inject is reached.
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ ! -f "$work/answered" ] || [ ! -f "$work/injected" ] \
      || ! printf '%s\n' "$out" | grep -q '^WIRING_SURVIVED$'; then
    echo "FAIL: a vetted-pass hooks-review pane should answer the modal and reach --inject" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a vetted-pass hooks-review pane answers the modal and reaches orca orchestration dispatch --inject"

  # Vet passes, but HOOKS_ANSWER_BIN names no file: the wiring block takes
  # the exit-3 path before trying to run anything.
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/no-such-hooks-answer"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 3 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a missing HOOKS_ANSWER_BIN should take the exit-3 path without answering or injecting (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s\n' "$out" | grep -q 'hooks-review answer tool missing or not executable' || { echo "FAIL: missing-answer-tool case did not print the missing-or-not-executable message" >&2; return 1; }
  echo "ok   : a missing HOOKS_ANSWER_BIN takes the exit-3 path without answering the modal or reaching --inject"

  # Failability: a copy of the wiring block whose existence check is disabled
  # still exits 3 on a missing HOOKS_ANSWER_BIN, since the shell can't exec a
  # file that isn't there. It drops the exit-3 path's own message, the call
  # was attempted instead of refused.
  mutant_wiring=${wiring_block/'if [ ! -f "$HOOKS_ANSWER_BIN" ] || [ ! -x "$HOOKS_ANSWER_BIN" ]; then'/'if false; then'}
  if [ "$mutant_wiring" = "$wiring_block" ]; then
    echo "FAIL: existence-check mutant did not change the source" >&2
    return 1
  fi
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$mutant_wiring" "$work/no-such-hooks-answer"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if printf '%s\n' "$out" | grep -q 'hooks-review answer tool missing or not executable'; then
    echo "FAIL: failability: disabling the existence check should drop the missing-tool message, but it is still printed" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: disabling the existence check attempts the call instead of refusing it (status=$status, message dropped)"

  # Vet passes, but HOOKS_ANSWER_BIN names an executable directory: -x alone
  # would pass for a directory, so the guard also checks -f and takes the
  # exit-3 path before trying to run anything.
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  mkdir -p "$work/dir-hooks-answer"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/dir-hooks-answer"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 3 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a directory at HOOKS_ANSWER_BIN should take the exit-3 path without answering or injecting (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s\n' "$out" | grep -q 'hooks-review answer tool missing or not executable' || { echo "FAIL: directory case did not print the missing-or-not-executable message" >&2; return 1; }
  echo "ok   : a directory at HOOKS_ANSWER_BIN takes the exit-3 path without answering the modal or reaching --inject"

  # Failability: a copy of the wiring block whose guard drops back to -x
  # alone lets an executable directory through instead of refusing it.
  mutant_wiring=${wiring_block/'if [ ! -f "$HOOKS_ANSWER_BIN" ] || [ ! -x "$HOOKS_ANSWER_BIN" ]; then'/'if [ ! -x "$HOOKS_ANSWER_BIN" ]; then'}
  if [ "$mutant_wiring" = "$wiring_block" ]; then
    echo "FAIL: directory-check mutant did not change the source" >&2
    return 1
  fi
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$mutant_wiring" "$work/dir-hooks-answer"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if printf '%s\n' "$out" | grep -q 'hooks-review answer tool missing or not executable'; then
    echo "FAIL: failability: dropping the -f check should let an executable directory through, but the guard still refused it" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: dropping the -f check lets an executable directory through instead of refusing it (status=$status)"

  # Vet passes and the answer tool runs, but it exits 1 (did not clear the
  # modal): the fail-closed answer-error path, not the always-exits-0 fake
  # tool every other case above uses.
  cat > "$work/fake-hooks-answer-fail" <<'BIN'
#!/bin/bash
echo ANSWERED >> "$FAKE_ANSWER_MARKER"
echo "hooks-review: still blocked after answering (some-reason)" >&2
exit 1
BIN
  chmod +x "$work/fake-hooks-answer-fail"
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/fake-hooks-answer-fail"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 3 ] || [ ! -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: an answer tool that exits 1 should take the exit-3 path without injecting (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s\n' "$out" | grep -q 'hooks-review answer did not clear the modal' || { echo "FAIL: answer-failure case did not print the modal-not-cleared message" >&2; return 1; }
  echo "ok   : an answer tool exit 1 takes the exit-3 path without injecting (status=$status)"

  # Failability: a copy of the wiring block that ignores the answer tool's
  # own exit code would inject even though the modal was never cleared.
  mutant_wiring=${wiring_block/'if [ "$HOOKS_ANSWER_RC" != 0 ]; then'/'if false; then'}
  if [ "$mutant_wiring" = "$wiring_block" ]; then
    echo "FAIL: answer-rc-check mutant did not change the source" >&2
    return 1
  fi
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$mutant_wiring" "$work/fake-hooks-answer-fail"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ ! -f "$work/injected" ]; then
    echo "FAIL: failability: ignoring the answer tool's exit code should still inject (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: ignoring the answer tool's exit code injects despite the modal never clearing (status=$status)"

  # Vet fails: the modal is never answered, --inject is never reached.
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-fail" "$wiring_block"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a vet-failed hooks-review pane should not answer the modal or reach --inject (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s\n' "$out" | grep -q 'hooks-vet:' || { echo "FAIL: vet-failed case did not print the vet's own line" >&2; return 1; }
  echo "ok   : a vet-failed hooks-review pane prints the vet's line and never answers the modal"

  # Failability: a copy of the wiring block whose vet gate is disabled would
  # answer the modal even on a vet-failed home.
  mutant_wiring=${wiring_block/'if codex_hooks_vet_homes; then'/'if true; then'}
  if [ "$mutant_wiring" = "$wiring_block" ]; then
    echo "FAIL: vet-gate mutant did not change the source" >&2
    return 1
  fi
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-fail" "$mutant_wiring"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ ! -f "$work/answered" ]; then
    echo "FAIL: failability: disabling the vet gate should have answered the modal on a vet-failed home, but didn't (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: disabling the vet gate answers the modal on a vet-failed home (status=$status)"

  # Account-seat home: $HOME's own hooks.json passes, but codex_accounts_dir
  # enumerates a seat whose hooks.json fails. "every codex home" means every
  # home, not just $HOME.
  mkdir -p "$work/accounts/seat1/home"
  cat > "$work/accounts/seat1/home/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "/no/such/binary"}]}]}}
EOF
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/fake-hooks-answer" "$work/accounts"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a failing account-seat home should block the modal even though \$HOME's own hooks.json passes (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a failing account-seat home blocks the modal despite a passing \$HOME hooks.json (status=$status)"

  # Project sources: a worktree under a repository's .orca/worktrees/ carries
  # its own `.codex/hooks.json`, and so can the repository root. Both are in
  # scope even when $HOME's own hooks.json passes.
  mkdir -p "$work/repo/.orca/worktrees/wt/.codex"
  cat > "$work/repo/.orca/worktrees/wt/.codex/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "/no/such/binary"}]}]}}
EOF
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/fake-hooks-answer" "$work/no-accounts-dir" "path:$work/repo/.orca/worktrees/wt"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a failing worktree .codex/hooks.json should block the modal (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a failing worktree .codex/hooks.json blocks the modal (status=$status)"

  rm -rf "$work/repo/.orca/worktrees/wt/.codex"
  mkdir -p "$work/repo/.codex"
  cat > "$work/repo/.codex/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "/no/such/binary"}]}]}}
EOF
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/fake-hooks-answer" "$work/no-accounts-dir" "path:$work/repo/.orca/worktrees/wt"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -eq 0 ] || [ -f "$work/answered" ] || [ -f "$work/injected" ]; then
    echo "FAIL: a failing repository-root .codex/hooks.json should block the modal (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a failing repository-root .codex/hooks.json blocks the modal via the .orca/worktrees derivation (status=$status)"

  # Failability: a copy of codex_hooks_homes that never resolves WORKTREE
  # reads neither project source, so the repo-root failure above would go
  # unseen and the modal would be answered.
  mutant_homes=${homes_fn/'  wt="${WORKTREE#path:}"'/'  wt=""'}
  if [ "$mutant_homes" = "$homes_fn" ]; then
    echo "FAIL: worktree-resolution mutant did not change the source" >&2
    return 1
  fi
  homes_fn_saved="$homes_fn"
  homes_fn="$mutant_homes"
  rm -f "$work/injected" "$work/answered" "$work/read-count"
  write_script "$script_file" "$work/fakehome-pass" "$wiring_block" "$work/fake-hooks-answer" "$work/no-accounts-dir" "path:$work/repo/.orca/worktrees/wt"
  out=$(PATH="$work:$PATH" bash "$script_file" 2>&1)
  status=$?
  homes_fn="$homes_fn_saved"
  if [ "$status" -ne 0 ] || [ ! -f "$work/answered" ]; then
    echo "FAIL: failability: a codex_hooks_homes that never resolves WORKTREE should answer the modal despite the failing repo-root hooks.json (status=$status)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : failability: a codex_hooks_homes that never resolves WORKTREE answers the modal despite the failing repo-root hooks.json (status=$status)"
)
codex_hooks_vet_wiring_test "$dispatch" || exit 1

echo "dispatch multi-vendor / check-only / contract-delivery / cursor-pretrust / codex-launch / codex-start-screen / codex-start-screen-wiring / codex-hooks-vet / codex-hooks-vet-wiring regression tests passed"
