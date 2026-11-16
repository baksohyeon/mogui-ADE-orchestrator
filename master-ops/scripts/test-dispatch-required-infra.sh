#!/bin/bash
# Regression check for required-infra (#317 stage 2): the standing-rule block
# that folds into every dispatched brief the same way mail-before-done does
# (test-dispatch-runtime.sh covers that sibling feature). dispatch carries
# {{RUNTIME_ROOT}}/{{OPS_REPO}} template placeholders, so this extracts just
# the functions and the 1.6c block by exact-line awk range and runs that
# snippet in an isolated subshell with a fixture standing-rules.md, rather
# than invoking the whole script.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

required_infra_always_test() (
  set +e
  set -u
  local dispatch="$1" work jqf_fn block_fn append_block rif_block script_file
  local out status mutant_block count

  jqf_fn=$(awk '$0=="jqf() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  block_fn=$(awk '$0=="standing_rule_block() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
  append_block=$(awk '
    /^STANDING_RULE_NAMES=\$\(echo "\$CHK" \| jqf/{f=1}
    f{print}
    f && /^fi$/{exit}
  ' "$dispatch")
  rif_block=$(awk '
    /^# 1\.6c required-infra ships to every brief/{f=1}
    f{print}
    f && /^esac$/{exit}
  ' "$dispatch")

  [ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; return 1; }
  [ -n "$block_fn" ] || { echo "FAIL: could not extract standing_rule_block" >&2; return 1; }
  [ -n "$append_block" ] || { echo "FAIL: could not extract the STANDING_RULE_NAMES append block" >&2; return 1; }
  [ -n "$rif_block" ] || { echo "FAIL: could not extract the required-infra always-append block" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-required-infra-test.$$"
  mkdir -p "$work/rules" "$work/scripts"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/rules/standing-rules.md" <<'RULES'
## headless

headless body text.

## required-infra

required-infra body text.
RULES

  write_script() {
    local outfile="$1" chat_json="$2" rules_file="${3:-$work/rules/standing-rules.md}"
    {
      echo 'set -u'
      printf 'SCRIPTS_DIR=%q\n' "$work/scripts"
      printf 'export DISPATCH_STANDING_RULES=%q\n' "$rules_file"
      printf 'export DISPATCH_STANDING_RULES_LOCAL=%q\n' "$work/config/standing-rules.overlay.md"
      printf '%s\n' "$jqf_fn"
      printf '%s\n' "$block_fn"
      printf 'CHK=%s\n' "$(printf '%q' "$chat_json")"
      echo 'SPEC="original spec"'
      echo 'fail_after_tracker_claim() { echo "✗ $1"; exit "${2:-3}"; }'
      printf '%s\n' "$append_block"
      printf '%s\n' "$rif_block"
      echo 'printf "SPEC_TAIL::%s\n" "$SPEC"'
    } > "$outfile"
  }

  script_file="$work/run.sh"

  # Case: front matter has no standing_rules key at all — required-infra
  # still appends and prints its own milestone line.
  write_script "$script_file" '{"allow": true, "front_matter": {}}'
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: front matter with no standing_rules key should not fail" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'required-infra body text.'; then
    echo "FAIL: required-infra block text missing when standing_rules is absent" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF '📎 standing rules · required-infra (always)'; then
    echo "FAIL: missing the always-milestone line when standing_rules is absent" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a front matter with no standing_rules key still gets required-infra appended"

  # Case: the contract already names required-infra — the original loop
  # appends it once, and the unconditional step must not append it again.
  write_script "$script_file" '{"allow": true, "front_matter": {"standing_rules": ["required-infra"]}}'
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: naming required-infra explicitly should not fail" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  count=$(printf '%s\n' "$out" | grep -cF 'Standing rules (required-infra):')
  if [ "$count" -ne 1 ]; then
    echo "FAIL: naming required-infra explicitly should append its block exactly once, got $count" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if printf '%s\n' "$out" | grep -qF '(always)'; then
    echo "FAIL: a block the contract already named should not also print the always-milestone line" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : naming required-infra explicitly appends its block exactly once, with no duplicate from the unconditional step"

  # Case: a rules file that predates this feature (no required-infra
  # heading) warns and continues rather than refusing the dispatch.
  : > "$work/rules/standing-rules-missing.md"
  write_script "$script_file" '{"allow": true, "front_matter": {}}' "$work/rules/standing-rules-missing.md"
  out=$(bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: a rules file missing the required-infra heading should warn, not fail the dispatch" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'required-infra standing-rule block not found'; then
    echo "FAIL: missing the warning naming the absent required-infra block" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'SPEC_TAIL::original spec'; then
    echo "FAIL: SPEC should stay unchanged when the block cannot be found" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  echo "ok   : a rules file predating required-infra warns and continues rather than refusing the dispatch"

  # Failability: drop the always-milestone echo; the first case above must
  # then stop printing it, proving the assertion exercises the real line.
  mutant_block=${rif_block/'      echo "📎 standing rules · required-infra (always)"'/'      :'}
  if [ "$mutant_block" = "$rif_block" ]; then
    echo "FAIL: always-milestone mutant did not change the source" >&2
    return 1
  fi
  {
    echo 'set -u'
    printf 'SCRIPTS_DIR=%s\n' "$work/scripts"
    printf 'export DISPATCH_STANDING_RULES=%s\n' "$work/rules/standing-rules.md"
    printf 'export DISPATCH_STANDING_RULES_LOCAL=%s\n' "$work/config/standing-rules.overlay.md"
    printf '%s\n' "$jqf_fn"
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
required_infra_always_test "$dispatch" || exit 1

# The block is ALSO a known standing-rule name purely from the shipped
# rules file's own "## required-infra" heading (dispatch_gate.py derives
# known names by scanning that file's headings; no separate allowlist to
# keep in sync).
rules_file=$(cd "$(dirname "$dispatch")/.." && pwd)/rules/standing-rules.md
grep -qxF '## required-infra' "$rules_file" || {
  echo "FAIL: shipped standing-rules.md is missing the '## required-infra' heading" >&2
  exit 1
}
echo "ok   : the shipped standing-rules.md declares '## required-infra', so dispatch-gate accepts it as a known block"

echo "dispatch required-infra-always regression test passed"
