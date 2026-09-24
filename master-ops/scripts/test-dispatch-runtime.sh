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
  local out status dest token_line_no mutant_block

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
  if ! printf '%s\n' "$out" | grep -qF "SPEC_TAIL::" || ! printf '%s\n' "$out" | grep -qF "$dest"; then
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

echo "dispatch multi-vendor / check-only / contract-delivery regression tests passed"
