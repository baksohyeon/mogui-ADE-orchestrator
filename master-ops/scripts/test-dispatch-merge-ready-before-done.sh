#!/bin/bash
# Regression check for merge-ready-before-done (#330): the standing-rule
# block that folds into every dispatched brief the same way mail-before-done
# and required-infra do (test-dispatch-required-infra.sh covers that
# sibling feature, and this test is lifted from the same shape). dispatch
# carries {{RUNTIME_ROOT}}/{{OPS_REPO}} template placeholders, so this
# extracts just the functions and the 1.6d block by exact-line awk range and
# runs that snippet in an isolated subshell with a fixture
# standing-rules.md, rather than invoking the whole script.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

merge_ready_before_done_always_test() (
  set +e
  set -u
  local dispatch="$1" work jqf_fn section_fn block_fn append_block mrbd_block script_file
  local out status mutant_block count

  jqf_fn=$(awk '$0=="jqf() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  section_fn=$(awk '$0=="markdown_section() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  block_fn=$(awk '$0=="standing_rule_block() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  append_block=$(awk '
    /^STANDING_RULE_NAMES=\$\(echo "\$CHK" \| jqf/{f=1}
    f{print}
    f && /^fi$/{exit}
  ' "$dispatch")
  mrbd_block=$(awk '
    /^# 1\.6d merge-ready-before-done ships to every brief/{f=1}
    f{print}
    f && /^esac$/{exit}
  ' "$dispatch")

  [ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; return 1; }
  [ -n "$section_fn" ] || { echo "FAIL: could not extract markdown_section" >&2; return 1; }
  [ -n "$block_fn" ] || { echo "FAIL: could not extract standing_rule_block" >&2; return 1; }
  [ -n "$append_block" ] || { echo "FAIL: could not extract the STANDING_RULE_NAMES append block" >&2; return 1; }
  [ -n "$mrbd_block" ] || { echo "FAIL: could not extract the merge-ready-before-done always-append block" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-merge-ready-before-done-test.$$"
  mkdir -p "$work/rules" "$work/scripts"
  trap 'rm -rf "${work:?}"' EXIT
  cat > "$work/rules/standing-rules.md" <<'RULES'
## headless

headless body text.

## merge-ready-before-done

merge-ready-before-done body text: run scripts/merge-ready --repo x/y --pr 1 and quote the line.
RULES

  write_script() {
    local outfile="$1" chat_json="$2" rules_file="${3:-$work/rules/standing-rules.md}"
    {
      echo 'set -u'
      printf 'OPS=%q\n' "$work/ops-root"
      printf 'SCRIPTS_DIR=%q\n' "$work/scripts"
      printf 'export DISPATCH_STANDING_RULES=%q\n' "$rules_file"
      printf 'export DISPATCH_STANDING_RULES_LOCAL=%q\n' "$work/config/standing-rules.overlay.md"
      printf '%s\n' "$jqf_fn"
      printf '%s\n' "$section_fn"
      printf '%s\n' "$block_fn"
      printf 'CHK=%s\n' "$(printf '%q' "$chat_json")"
      echo 'SPEC="original spec"'
      echo 'fail_after_tracker_claim() { echo "✗ $1"; exit "${2:-3}"; }'
      printf '%s\n' "$append_block"
      printf '%s\n' "$mrbd_block"
      echo 'printf "SPEC_TAIL::%s\n" "$SPEC"'
    } > "$outfile"
  }

  script_file="$work/run.sh"

  # Case: front matter has no standing_rules key at all (the omitted-block
  # case the contract's acceptance check 3 names): merge-ready-before-done
  # still appends and prints its own milestone line.
  write_script "$script_file" '{"allow": true, "front_matter": {}}'
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: front matter with no standing_rules key should not fail" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'merge-ready-before-done body text'; then
    echo "FAIL: merge-ready-before-done block text missing when standing_rules is absent" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF '📎 standing rules · merge-ready-before-done (always)'; then
    echo "FAIL: missing the always-milestone line when standing_rules is absent" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a front matter with no standing_rules key still gets merge-ready-before-done appended"

  # The block's own relative `scripts/merge-ready` is meaningless from a
  # worker's product-worktree cwd; the always-append step must resolve it
  # to this installation's own $OPS before it ships.
  if printf '%s\n' "$out" | grep -qF 'run scripts/merge-ready --repo'; then
    echo "FAIL: the unconditional append left the script path unresolved (still relative)" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF "run $work/ops-root/scripts/merge-ready --repo"; then
    echo "FAIL: the unconditional append did not resolve scripts/merge-ready to \$OPS/scripts/merge-ready" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : the unconditional append resolves the block's script path to \$OPS/scripts/merge-ready"

  # Case: the contract already names merge-ready-before-done: the original
  # loop appends it once, and the unconditional step must not append it
  # again.
  write_script "$script_file" '{"allow": true, "front_matter": {"standing_rules": ["merge-ready-before-done"]}}'
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: naming merge-ready-before-done explicitly should not fail" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  count=$(printf '%s\n' "$out" | grep -cF 'Standing rules (merge-ready-before-done):')
  if [ "$count" -ne 1 ]; then
    echo "FAIL: naming merge-ready-before-done explicitly should append its block exactly once, got $count" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if printf '%s\n' "$out" | grep -qF '(always)'; then
    echo "FAIL: a block the contract already named should not also print the always-milestone line" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF "run $work/ops-root/scripts/merge-ready --repo"; then
    echo "FAIL: naming merge-ready-before-done explicitly still left the script path unresolved" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : naming merge-ready-before-done explicitly appends its block exactly once, with no duplicate from the unconditional step, and its script path resolved the same way"

  # Case: a rules file that predates this feature (no merge-ready-before-done
  # heading) warns and continues rather than refusing the dispatch.
  : > "$work/rules/standing-rules-missing.md"
  write_script "$script_file" '{"allow": true, "front_matter": {}}' "$work/rules/standing-rules-missing.md"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: a rules file missing the merge-ready-before-done heading should warn, not fail the dispatch" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'merge-ready-before-done standing-rule block not found'; then
    echo "FAIL: missing the warning naming the absent merge-ready-before-done block" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'SPEC_TAIL::original spec'; then
    echo "FAIL: SPEC should stay unchanged when the block cannot be found" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a rules file predating merge-ready-before-done warns and continues rather than refusing the dispatch"

  # Failability: drop the always-milestone echo; the first case above must
  # then stop printing it, proving the assertion exercises the real line.
  mutant_block=${mrbd_block/'      echo "📎 standing rules · merge-ready-before-done (always)"'/'      :'}
  if [ "$mutant_block" = "$mrbd_block" ]; then
    echo "FAIL: always-milestone mutant did not change the source" >&2
    return 1
  fi
  {
    echo 'set -u'
    printf 'OPS=%s\n' "$work/ops-root"
    printf 'SCRIPTS_DIR=%s\n' "$work/scripts"
    printf 'export DISPATCH_STANDING_RULES=%s\n' "$work/rules/standing-rules.md"
    printf 'export DISPATCH_STANDING_RULES_LOCAL=%s\n' "$work/config/standing-rules.overlay.md"
    printf '%s\n' "$jqf_fn"
    printf '%s\n' "$section_fn"
    printf '%s\n' "$block_fn"
    printf 'CHK=%s\n' "$(printf '%q' '{"allow": true, "front_matter": {}}')"
    echo 'SPEC="original spec"'
    echo 'fail_after_tracker_claim() { echo "✗ $1"; exit "${2:-3}"; }'
    printf '%s\n' "$append_block"
    printf '%s\n' "$mutant_block"
    echo 'printf "SPEC_TAIL::%s\n" "$SPEC"'
  } > "$script_file"
  out=$(bash "$script_file" 2>&1)
  if printf '%s\n' "$out" | grep -qF '(always)'; then
    echo "FAIL: failability: dropping the always-milestone echo should have stopped printing it, but it still appeared" >&2
    return 1
  fi
  echo "ok   : failability: dropping the always-milestone echo makes the milestone-line assertion fail"
)
merge_ready_before_done_always_test "$dispatch" || exit 1

# The block is ALSO a known standing-rule name purely from the shipped
# rules file's own "## merge-ready-before-done" heading (dispatch_gate.py
# derives known names by scanning that file's headings; no separate
# allowlist to keep in sync).
rules_file=$(cd "$(dirname "$dispatch")/.." && pwd)/rules/standing-rules.md
grep -qxF '## merge-ready-before-done' "$rules_file" || {
  echo "FAIL: shipped standing-rules.md is missing the '## merge-ready-before-done' heading" >&2
  exit 1
}
echo "ok   : the shipped standing-rules.md declares '## merge-ready-before-done', so dispatch-gate accepts it as a known block"

echo "dispatch merge-ready-before-done-always regression test passed"
