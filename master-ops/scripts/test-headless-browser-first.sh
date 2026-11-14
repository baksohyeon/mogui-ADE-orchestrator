#!/bin/bash
# Regression coverage for the contract-selective headless-browser-first rule.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}
rules_file=$(cd "$(dirname "$dispatch")/.." && pwd)/rules/standing-rules.md
rule_name=headless-browser-first

grep -Fq "## $rule_name" "$rules_file" || {
  echo "FAIL: missing standing-rules section: $rule_name" >&2
  exit 1
}

jqf_fn=$(awk '$0=="jqf() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
block_fn=$(awk '$0=="standing_rule_block() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
append_block=$(awk '
  /^STANDING_RULE_NAMES=\$\(echo "\$CHK" \| jqf/{f=1}
  f{print}
  f && /^fi$/{exit}
' "$dispatch")

[ -n "$jqf_fn" ] || { echo "FAIL: could not extract jqf" >&2; exit 1; }
[ -n "$block_fn" ] || { echo "FAIL: could not extract standing_rule_block" >&2; exit 1; }
[ -n "$append_block" ] || { echo "FAIL: could not extract the standing-rules append block" >&2; exit 1; }

work=$(mktemp -d "${TMPDIR:-/tmp}/mogui-headless-browser-first.XXXXXX")
trap 'rm -rf "$work"' EXIT
fixture_rules="$work/standing-rules.md"
mutant_rules="$work/standing-rules-mutant.md"
script_file="$work/run.sh"
mkdir -p "$work/scripts" "$work/config"
cp "$rules_file" "$fixture_rules"

write_script() {
  local outfile="$1" rules_path="$2" chat_json
  chat_json="{\"allow\": true, \"front_matter\": {\"standing_rules\": [\"$rule_name\"]}}"
  {
    echo 'set -u'
    printf 'SCRIPTS_DIR=%s\n' "$work/scripts"
    printf 'export DISPATCH_STANDING_RULES=%s\n' "$rules_path"
    printf 'export DISPATCH_STANDING_RULES_LOCAL=%s\n' "$work/config/standing-rules.overlay.md"
    printf '%s\n' "$jqf_fn"
    printf '%s\n' "$block_fn"
    printf 'CHK=%s\n' "$(printf '%q' "$chat_json")"
    echo 'SPEC="original spec"'
    echo 'fail_after_tracker_claim() { echo "FAIL: $1"; exit "${2:-3}"; }'
    printf '%s\n' "$append_block"
    echo 'printf "SPEC_TAIL::%s\n" "$SPEC"'
  } > "$outfile"
}

write_script "$script_file" "$fixture_rules"
out=$(bash "$script_file" 2>&1)
if ! printf '%s\n' "$out" | grep -qF "Standing rules ($rule_name):"; then
  echo "FAIL: dispatch did not label the injected $rule_name block" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! printf '%s\n' "$out" | grep -qF "Orca's embedded browser first"; then
  echo "FAIL: dispatch did not inject the $rule_name body" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : a contract listing $rule_name receives its standing-rules block"

awk -v name="## $rule_name" '
  $0 == name {drop=1; next}
  drop && /^## / {drop=0}
  !drop {print}
' "$fixture_rules" > "$mutant_rules"
write_script "$script_file" "$mutant_rules"
set +e
out=$(bash "$script_file" 2>&1)
status=$?
set -e
if [ "$status" -ne 3 ] || ! printf '%s\n' "$out" | grep -qF "standing rule block not found: $rule_name"; then
  echo "FAIL: missing-section mutant should fail injection with exit 3" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : failability: dropping the $rule_name section makes injection fail"
