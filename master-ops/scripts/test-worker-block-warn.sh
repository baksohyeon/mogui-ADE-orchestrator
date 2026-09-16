#!/usr/bin/env bash
# The approval markers live in approval-prompt-markers.txt and hooks/worker-block-warn.sh reads
# them from there. This pins the file's marker set, checks the hook reads the file rather than a
# copy, and runs the loaded pattern against samples. The full hook needs live `orca terminal list`.
set -u
S="$(cd "$(dirname "$0")" && pwd)"; HOOK="$S/hooks/worker-block-warn.sh"; MARKERS="$S/approval-prompt-markers.txt"; FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }; ok() { echo "  ok:   $*"; }

grep -Fq 'approval-prompt-markers.txt' "$HOOK" && ok "hook reads the shared marker file" || fail "hook does not reference approval-prompt-markers.txt"
grep -qE 'grep -icE "(do you want to proceed|hooks need review)' "$HOOK" && fail "hook still carries an inline marker list" || ok "hook carries no inline marker list"

PATTERN=$(grep -vE '^[[:space:]]*(#|$)' "$MARKERS" | paste -sd'|' -)
[ -n "$PATTERN" ] && ok "marker file loads ($(printf '%s' "$PATTERN" | tr '|' '\n' | wc -l | tr -d ' ') markers)" || fail "marker file empty or unreadable"
for m in 'do you want to proceed' '1\. yes' '2\. yes, and' '\[y/n\]' '\(y/n\)' 'press enter to continue' 'trust this (folder|workspace)' 'hooks need review' 'trust all and continue' 'press enter to confirm'; do
  grep -Fxq "$m" "$MARKERS" && ok "pinned marker present: $m" || fail "pinned marker missing: $m"
done

count() { printf '%s' "$1" | grep -icE "$PATTERN" || true; }
positive() { c=$(count "$2"); [ "$c" -ge 1 ] && ok "positive: $1 ($c)" || fail "positive: $1 matched 0"; }
negative() { c=$(count "$2"); [ "$c" -eq 0 ] && ok "negative: $1" || fail "negative: $1 matched $c"; }

# Verbatim pane preview of the codex 0.154.0 modal, 2026-09-15.
CODEX_MODAL='Hooks need review / 6 hooks are new or changed. / Hooks can run outside the sandbox after you trust them. / 1. Review hooks / 2. Trust all and continue / 3. Continue without trusting / Press enter to confirm or esc to go back'
positive "codex hook-trust modal preview" "$CODEX_MODAL"
positive "proceed question" 'Do you want to proceed?'
positive "trust folder" 'Trust this folder'
positive "[y/n]" '[y/n]'
positive "press enter to continue" 'Press enter to continue'
positive "marker alone: hooks need review" 'Hooks need review'
positive "marker alone: trust all and continue" 'Trust all and continue'
positive "marker alone: press enter to confirm" 'Press enter to confirm'

negative "idle status line" '~/dev/example on main · idle'
negative "token counter" 'Reading 1.28k tokens'
negative "stripped runtime flags" 'always-approve bypass permissions'

# Failability: the pattern minus one marker must miss that marker's sample.
REDUCED=$(grep -vE '^[[:space:]]*(#|$)' "$MARKERS" | grep -vFx 'trust all and continue' | paste -sd'|' -)
[ "$(printf '%s' 'Trust all and continue' | grep -icE "$REDUCED" || true)" -eq 0 ] && ok "failability: removing a marker breaks its sample" || fail "failability: reduced pattern still matched"

[ "$FAILED" -eq 0 ] && echo "worker-block-warn: all checks passed" || { echo "worker-block-warn: FAILED"; exit 1; }
