#!/usr/bin/env bash
# The blocked-marker regex in hooks/worker-block-warn.sh must catch every approval prompt a worker
# can sit on, including the codex hook-trust modal it missed until 2026-09-15. The regex is tested
# in isolation and pinned to the hook text, because the full hook reads live `orca terminal list`.
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/hooks/worker-block-warn.sh"; FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }; ok() { echo "  ok:   $*"; }

PATTERN='do you want to proceed|1\. yes|2\. yes, and|\[y/n\]|\(y/n\)|press enter to continue|trust this (folder|workspace)|hooks need review|trust all and continue|press enter to confirm'
grep -Fq "grep -icE \"$PATTERN\"" "$HOOK" && ok "hook carries the expected blocked regex" || fail "hook blocked regex differs from the pinned pattern"

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

negative "idle status line" '~/dev/example on main · idle'
negative "token counter" 'Reading 1.28k tokens'
negative "stripped runtime flags" 'always-approve bypass permissions'

# Failability: with one new marker removed, its marker-only sample must miss.
REDUCED='do you want to proceed|1\. yes|2\. yes, and|\[y/n\]|\(y/n\)|press enter to continue|trust this (folder|workspace)|hooks need review|press enter to confirm'
[ "$(printf '%s' 'Trust all and continue' | grep -icE "$REDUCED" || true)" -eq 0 ] && ok "failability: removing a marker breaks its sample" || fail "failability: reduced pattern still matched"

[ "$FAILED" -eq 0 ] && echo "worker-block-warn: all checks passed" || { echo "worker-block-warn: FAILED"; exit 1; }
