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
  echo "ok   — codex launch carries --model, reasoning effort, update-check off, and the migration ack · rc=0"

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
    echo "FAIL: failability — mutant dropping check_for_update_on_startup=false still produced the exact wanted string" >&2
    return 1
  fi
  echo "ok   — failability: dropping check_for_update_on_startup=false breaks the exact-string match (mutant rc=$status)"
)
codex_launch_flags_test "$dispatch" || exit 1

# --- Feature: codex start-screen check before inject -------------------------
#
# 2026-10-01: a codex pane sitting on that migration menu, a folder-trust
# prompt, or a provider-limit notice reports idle exactly like a ready prompt
# — `terminal wait --for tui-idle` cannot tell them apart, only the footer
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
    echo "ok   — case $label · rc=$rc"
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
      echo "FAIL: failability — $label mutant still returns $blocked_rc" >&2
      return 1
    fi
    echo "ok   — failability: $label mutant changes rc $blocked_rc -> $rc"
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

echo "dispatch multi-vendor / check-only / contract-delivery / cursor-pretrust / codex-launch / codex-start-screen regression tests passed"
