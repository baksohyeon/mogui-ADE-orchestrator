#!/bin/bash
# Regression checks for dispatch-smoke's pure functions: the milestone parser
# and layer verdict, the isolation comparison, the expected-token derivation,
# and the precondition that refuses an unrendered wrapper. No Orca, no
# network, no claude: each case extracts just its function by exact-line
# awk range and runs that snippet in an isolated subshell with canned input.
set -eu

smoke=$(cd "$(dirname "$0")" && pwd)/dispatch-smoke
smoke=${1:-$smoke}

extract_fn() {  # wrapper-ish-file, "name() {"
  awk -v hdr="$2" '$0==hdr{f=1} f{print} f&&$0=="}"{exit}' "$1"
}

# --- Feature: normal_case_verdict (milestone parser + layer verdict) -------
#
# One canned log per layer named in the contract's localization table: gate,
# orca at terminal-create, register, delivery with class=hook-trust, and a
# full pass. Each must produce the documented verdict or PASS.
verdict_test() (
  set +e
  set -u
  local smoke="$1" fn work script_file

  fn=$(extract_fn "$smoke" 'normal_case_verdict() {')
  [ -n "$fn" ] || { echo "FAIL: could not extract normal_case_verdict" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-smoke-verdict-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT

  run_case() {  # fn-body  rc  log-content  want
    local body="$1" rc="$2" content="$3" want="$4" logfile="$work/case.log" out
    printf '%s' "$content" > "$logfile"
    script_file="$work/run.sh"
    {
      echo 'set -u'
      printf '%s\n' "$body"
      printf 'normal_case_verdict %s %s\n' "$rc" "$(printf '%q' "$logfile")"
    } > "$script_file"
    out=$(bash "$script_file" 2>&1)
    if [ "$out" != "$want" ]; then
      echo "FAIL: expected '$want', got '$out' for rc=$rc" >&2
      return 1
    fi
  }

  run_case "$fn" 2 "✗ gate DENY · reason · model=gpt-5.6-sol tier=top
" "layer=gate" || return 1
  echo "ok   : normal_case_verdict · gate denial (exit 2) reports layer=gate"

  run_case "$fn" 3 "⚙ gate ✓ top · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
✗ terminal create failed
" "layer=orca step=terminal-create" || return 1
  echo "ok   : normal_case_verdict · orca failure at terminal-create (exit 3) reports layer=orca step=terminal-create"

  run_case "$fn" 4 "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
✗ register denied · dispatch=ctx_999 (worker IS running, resolve register manually)
" "layer=register" || return 1
  echo "ok   : normal_case_verdict · register denial (exit 4) reports layer=register"

  run_case "$fn" 5 "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=hook-trust class=hook-trust
✗ delivery FAILED · claude's folder-trust dialog is still present; the spec was NOT consumed
" "layer=delivery step=hook-trust" || return 1
  echo "ok   : normal_case_verdict · delivery class=hook-trust (exit 5) reports layer=delivery step=hook-trust"

  run_case "$fn" 0 "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=unknown class=agent-started
✓ delivery ✓ agent left its prepared prompt after inject and began processing
" "PASS" || return 1
  echo "ok   : normal_case_verdict · full milestone set with class=agent-started (exit 0) reports PASS"

  # Failability: change the agent-started literal the delivery-class check
  # compares against; the full-pass case above must then stop reporting PASS.
  mutant_fn=${fn/'"$class" != agent-started'/'"$class" != nevermatches'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: agent-started mutant did not change the source" >&2
    return 1
  fi
  logfile="$work/mutant.log"
  printf '%s' "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=unknown class=agent-started
✓ delivery ✓ agent left its prepared prompt after inject and began processing
" > "$logfile"
  script_file="$work/run.sh"
  {
    echo 'set -u'
    printf '%s\n' "$mutant_fn"
    printf 'normal_case_verdict 0 %s\n' "$(printf '%q' "$logfile")"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  if [ "$out" = "PASS" ]; then
    echo "FAIL: failability: mutant replacing the agent-started literal should have broken the full-pass case, still got PASS" >&2
    return 1
  fi
  echo "ok   : failability: replacing the agent-started literal makes the full-pass case stop reporting PASS (got '$out')"

  # 2026-10-23: a worker that completes inside the delivery window returns
  # the pane to a prepared prompt, so the wrapper's own pane-transition class
  # reads done (a positive class, same shape as agent-started) while the rest
  # of the milestone set is unchanged.
  run_case "$fn" 0 "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=prepared-prompt status=completed class=done
✓ delivery ✓ worker completed inside the window (dispatch completed)
" "PASS" || return 1
  echo "ok   : normal_case_verdict · full milestone set with class=done (exit 0) reports PASS"

  # class=unknown with a dispatch status read by the caller: completed folds
  # into one combined step instead of leaving "delivery unverified" next to a
  # dispatch-show that already says the worker is done.
  run_case_with_status() {  # fn-body  rc  log-content  status  want
    local body="$1" rc="$2" content="$3" dstatus="$4" want="$5" logfile="$work/case-status.log" out
    printf '%s' "$content" > "$logfile"
    script_file="$work/run.sh"
    {
      echo 'set -u'
      printf '%s\n' "$body"
      printf 'normal_case_verdict %s %s %s\n' "$rc" "$(printf '%q' "$logfile")" "$(printf '%q' "$dstatus")"
    } > "$script_file"
    out=$(bash "$script_file" 2>&1)
    if [ "$out" != "$want" ]; then
      echo "FAIL: expected '$want', got '$out' for rc=$rc status=$dstatus" >&2
      return 1
    fi
  }

  UNKNOWN_LOG="⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=unknown status=completed class=unknown
⚠ delivery UNVERIFIED · pane is not a recognized prepared prompt
"
  run_case_with_status "$fn" 0 "$UNKNOWN_LOG" completed "layer=delivery step=unknown worker=completed" || return 1
  echo "ok   : normal_case_verdict · class=unknown with dispatch status completed reports layer=delivery step=unknown worker=completed"

  run_case_with_status "$fn" 0 "$UNKNOWN_LOG" active "layer=delivery step=unknown" || return 1
  echo "ok   : normal_case_verdict · class=unknown with dispatch status active reports layer=delivery step=unknown"

  # Failability: drop the unknown+completed fold; the completed-status case
  # above must then stop reporting worker=completed.
  mutant_fn=${fn/'    if [ "$class" = unknown ] && [ "$status" = completed ]; then
      printf '"'"'layer=delivery step=unknown worker=completed\n'"'"'
    else
      printf '"'"'layer=delivery step=%s\n'"'"' "$class"
    fi'/'    printf '"'"'layer=delivery step=%s\n'"'"' "$class"'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: unknown-completed-fold mutant did not change the source" >&2
    return 1
  fi
  logfile="$work/mutant-unknown-completed.log"
  printf '%s' "$UNKNOWN_LOG" > "$logfile"
  script_file="$work/run.sh"
  {
    echo 'set -u'
    printf '%s\n' "$mutant_fn"
    printf 'normal_case_verdict 0 %s completed\n' "$(printf '%q' "$logfile")"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  if [ "$out" = "layer=delivery step=unknown worker=completed" ]; then
    echo "FAIL: failability: mutant dropping the unknown+completed fold should have stopped reporting worker=completed" >&2
    return 1
  fi
  echo "ok   : failability: dropping the unknown+completed fold stops the completed-status case from reporting worker=completed (got '$out')"

  # Failability: a done-class milestone set must stop reporting PASS if the
  # done literal the delivery-class check compares against is renamed away.
  mutant_fn=${fn/'"$class" != done'/'"$class" != nevermatches'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: done mutant did not change the source" >&2
    return 1
  fi
  logfile="$work/mutant-done.log"
  printf '%s' "⚙ gate ✓ efficient · claude-haiku-4-5 · est 3.0k · 계약 abcdef12
📄 contract delivered · /tmp/x · read-token required
→ task_abc123 → term_def456-0000-0000-0000-000000000000 (신규)
⚡ register ✓ ctx_111222 · probe: job=원장대조 model=scoped-to-worktree
delivery pre=prepared-prompt post=prepared-prompt status=completed class=done
✓ delivery ✓ worker completed inside the window (dispatch completed)
" > "$logfile"
  script_file="$work/run.sh"
  {
    echo 'set -u'
    printf '%s\n' "$mutant_fn"
    printf 'normal_case_verdict 0 %s\n' "$(printf '%q' "$logfile")"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  if [ "$out" = "PASS" ]; then
    echo "FAIL: failability: mutant replacing the done literal should have broken the done-class pass case, still got PASS" >&2
    return 1
  fi
  echo "ok   : failability: replacing the done literal makes the done-class case stop reporting PASS (got '$out')"
)
verdict_test "$smoke" || exit 1

# --- Feature: isolation_diff -------------------------------------------------
isolation_test() (
  set +e
  set -u
  local smoke="$1" fn work script_file out mutant_fn rc

  fn=$(extract_fn "$smoke" 'isolation_diff() {')
  [ -n "$fn" ] || { echo "FAIL: could not extract isolation_diff" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-smoke-isolation-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  script_file="$work/run.sh"

  write_script() {
    local outfile="$1" body="$2"
    {
      echo 'set -u'
      printf '%s\n' "$body"
      printf 'isolation_diff %q %q %q %q\n' "$3" "$4" "$5" "$6"
    } > "$outfile"
  }

  write_script "$script_file" "$fn" shaA shaA "a
b" "a
b"
  out=$(bash "$script_file" 2>&1)
  rc=$?
  [ "$rc" = 0 ] || { echo "FAIL: matching sha and listing should exit 0, got rc=$rc output='$out'" >&2; return 1; }
  [ -z "$out" ] || { echo "FAIL: matching sha and listing should report nothing, got '$out'" >&2; return 1; }
  echo "ok   : isolation_diff reports nothing when both the ledger sha and the contracts listing match"

  write_script "$script_file" "$fn" shaA shaB "a
b" "a
b"
  out=$(bash "$script_file" 2>&1)
  [ "$out" = "ledger" ] || { echo "FAIL: a differing sha should report 'ledger', got '$out'" >&2; return 1; }
  echo "ok   : isolation_diff reports 'ledger' when the sha differs"

  write_script "$script_file" "$fn" shaA shaA "a
b" "a
b
c"
  out=$(bash "$script_file" 2>&1)
  [ "$out" = "contracts" ] || { echo "FAIL: a differing listing should report 'contracts', got '$out'" >&2; return 1; }
  echo "ok   : isolation_diff reports 'contracts' when the listing differs"

  # Failability: drop the sha comparison; a differing sha then goes unreported.
  mutant_fn=$(printf '%s\n' "$fn" | grep -v 'ledger_sha_before.*ledger_sha_after.*out="\$out ledger"')
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: sha-compare mutant did not change the source" >&2
    return 1
  fi
  write_script "$script_file" "$mutant_fn" shaA shaB "a" "a"
  out=$(bash "$script_file" 2>&1)
  rc=$?
  [ "$rc" = 0 ] || { echo "FAIL: mutant should exit 0, got rc=$rc output='$out'" >&2; return 1; }
  [ -z "$out" ] || { echo "FAIL: failability mutant unexpectedly still reported a diff ('$out')" >&2; return 1; }
  echo "ok   : failability: dropping the sha comparison makes a real ledger difference go unreported"
)
isolation_test "$smoke" || exit 1

# --- Feature: expected_token -------------------------------------------------
token_test() (
  set +e
  set -u
  local smoke="$1" fn work fixture sha want got script_file mutant_fn

  fn=$(extract_fn "$smoke" 'expected_token() {')
  [ -n "$fn" ] || { echo "FAIL: could not extract expected_token" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-smoke-token-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  fixture="$work/fixture.md"
  printf '# fixture contract\n\nsome body text\n' > "$fixture"
  sha=$(shasum -a 256 "$fixture" | awk '{print $1}')
  want="ack-${sha:8:12}"

  script_file="$work/run.sh"
  {
    echo 'set -u'
    printf '%s\n' "$fn"
    printf 'expected_token %q\n' "$fixture"
  } > "$script_file"
  got=$(bash "$script_file" 2>&1)
  [ "$got" = "$want" ] || { echo "FAIL: expected_token gave '$got', want '$want'" >&2; return 1; }
  echo "ok   : expected_token equals ack- plus characters 9 to 20 of the fixture's sha256"

  # Failability: shift the substring window (characters 1 to 12 instead of 9
  # to 20); the fixture's token must then stop matching.
  mutant_fn=${fn/'${sha:8:12}'/'${sha:0:12}'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: substring-window mutant did not change the source" >&2
    return 1
  fi
  {
    echo 'set -u'
    printf '%s\n' "$mutant_fn"
    printf 'expected_token %q\n' "$fixture"
  } > "$script_file"
  got=$(bash "$script_file" 2>&1)
  if [ "$got" = "$want" ]; then
    echo "FAIL: failability: mutant shifting the substring window still produced the correct token" >&2
    return 1
  fi
  echo "ok   : failability: shifting the substring window produces a token that no longer matches the fixture"
)
token_test "$smoke" || exit 1

# --- Feature: wrapper_is_rendered (precondition 1) --------------------------
rendered_precondition_test() (
  set +e
  set -u
  local smoke="$1" fn work rendered unrendered script_file out mutant_fn

  fn=$(extract_fn "$smoke" 'wrapper_is_rendered() {')
  [ -n "$fn" ] || { echo "FAIL: could not extract wrapper_is_rendered" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-smoke-rendered-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  rendered="$work/dispatch-rendered"
  unrendered="$work/dispatch-unrendered"
  printf '#!/bin/bash\nOPS=/opt/ops\nGATE=/opt/ops/scripts/dispatch-gate\n' > "$rendered"
  printf '#!/bin/bash\nOPS={{OPS_REPO}}\nGATE={{RUNTIME_ROOT}}/scripts/dispatch-gate\n' > "$unrendered"

  script_file="$work/run.sh"
  {
    echo 'set -u'
    printf '%s\n' "$fn"
    printf 'wrapper_is_rendered %q && echo RENDERED || echo UNRENDERED\n' "$rendered"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  [ "$out" = "RENDERED" ] || { echo "FAIL: a copy with no {{ token should pass as rendered, got '$out'" >&2; return 1; }
  echo "ok   : wrapper_is_rendered passes a copy with no {{ template token"

  {
    echo 'set -u'
    printf '%s\n' "$fn"
    printf 'wrapper_is_rendered %q && echo RENDERED || echo UNRENDERED\n' "$unrendered"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  [ "$out" = "UNRENDERED" ] || { echo "FAIL: a copy carrying {{RUNTIME_ROOT}} should be refused, got '$out'" >&2; return 1; }
  echo "ok   : wrapper_is_rendered refuses a copy carrying {{RUNTIME_ROOT}}"

  # Failability: drop the negation, so a template copy reports rendered.
  mutant_fn=${fn/'! grep -qF'/'grep -qF'}
  if [ "$mutant_fn" = "$fn" ]; then
    echo "FAIL: negation mutant did not change the source" >&2
    return 1
  fi
  {
    echo 'set -u'
    printf '%s\n' "$mutant_fn"
    printf 'wrapper_is_rendered %q && echo RENDERED || echo UNRENDERED\n' "$unrendered"
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  if [ "$out" = "UNRENDERED" ]; then
    echo "FAIL: failability: mutant dropping the negation should have misreported the unrendered copy as rendered" >&2
    return 1
  fi
  echo "ok   : failability: dropping the negation makes the unrendered copy misreport as rendered"
)
rendered_precondition_test "$smoke" || exit 1

echo "dispatch-smoke pure-function regression tests passed"
