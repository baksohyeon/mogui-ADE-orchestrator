#!/bin/bash
# Regression coverage for the codex CLI's prepared-prompt placeholder. A new
# file because test-dispatch-runtime.sh is past the 1,000-line rule
# (CONTRIBUTING.md "When a file is full").
#
# 2026-11-08 20:58 KST: a fresh `codex` pane (codex-cli 0.159.3) carries its
# own placeholder ("Ask Codex to do anything") next to the arrow instead of
# the claude placeholder or a bare arrow, so PREPARED_UNICODE_PROMPT_MARKERS
# read it as unknown before and after inject, and a worker that finished
# inside the delivery window never registered as delivered. Extracts
# pane_classify_text and the four marker variables from dispatch, the
# convention test-dispatch-runtime.sh already uses, and runs them against
# the three measured pane lines.
set -u

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

markers=$(grep -E '^(LIMIT_MARKERS|HOOK_TRUST_MARKERS|PREPARED_PROMPT_MARKERS|PREPARED_UNICODE_PROMPT_MARKERS)=' "$dispatch")
classify_fn=$(awk '$0=="pane_classify_text() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")

[ "$(printf '%s\n' "$markers" | grep -c .)" = 4 ] || { echo "FAIL: could not extract all four marker variables" >&2; exit 1; }
[ -n "$classify_fn" ] || { echo "FAIL: could not extract pane_classify_text" >&2; exit 1; }

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-prompt-marker.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT

pane=$(printf '%s\n%s\n%s' \
  '› Ask Codex to do anything' \
  '  GPT-6-Astra high · ~/worktree' \
  '  ? for shortcuts                                                                      ⚠ 4 warnings · f2 to view')

write_script() {
  local outfile="$1" markers_body="$2"
  {
    echo 'set -u'
    printf '%s\n' "$markers_body"
    printf '%s\n' "$classify_fn"
    printf 'pane_classify_text %s\n' "$(printf '%q' "$pane")"
  } > "$outfile"
}

script_file="$work/run.sh"
write_script "$script_file" "$markers"
out=$(bash "$script_file" 2>&1)
status=$?
if [ "$status" -ne 0 ] || [ "$out" != "prepared-prompt" ]; then
  echo "FAIL: a fresh codex TUI prompt pane should classify as prepared-prompt, got '$out' (status=$status)" >&2
  exit 1
fi
echo "ok   : a fresh codex TUI prompt's placeholder arrow line classifies as prepared-prompt"

# Failability: dropping the codex placeholder group must misclassify the
# same pane as unknown.
mutant_markers=${markers/'([\xc2\xa0 ]+Ask Codex to do anything)?'/}
if [ "$mutant_markers" = "$markers" ]; then
  echo "FAIL: codex-marker mutant did not change the source" >&2
  exit 1
fi
write_script "$script_file" "$mutant_markers"
out=$(bash "$script_file" 2>&1)
status=$?
if [ "$status" -ne 0 ] || [ "$out" != "unknown" ]; then
  echo "FAIL: failability: mutant dropping the codex placeholder should have classified the pane as unknown, got '$out' (status=$status)" >&2
  exit 1
fi
echo "ok   : failability: dropping the codex placeholder misclassifies the fresh prompt pane as unknown"

echo "dispatch codex prepared-prompt marker regression tests passed"
