#!/bin/bash
# Regression cases for spawn-test, from defects measured on 2026-08-04.
#
# Both of these shipped, ran green, and reported better news than the truth.
# Neither needed an agent, a sandbox, or a network call to catch — only a case
# table, which is why this file exists.
set -u

cd "$(dirname "$0")/.."

# The guard at the bottom of spawn-test keeps main from running on source.
SPAWN_TEST_LIB_ONLY=1
export SPAWN_TEST_LIB_ONLY
# shellcheck disable=SC1091
. ./scripts/spawn-test >/dev/null 2>&1 || true

pass=0
fail=0

check() {
  local name="$1" want="$2" got="$3"
  if [ "$got" = "$want" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       want: $want"
    echo "       got:  $got"
    fail=$((fail + 1))
  fi
}

# --- Defect 1: every failure rendered as SKIP -------------------------------
# The report row tested [ "$status" = "FAIL" ] for equality, but save_result
# always writes the reason into the status. The equality never matched, so
# failures fell through to the skip branch. On 2026-08-04 cursor and agy failed
# 2/3 and both printed SKIP next to a FLOOR MET banner.
check "status carrying a reason is a failure" \
  "FAIL" "$(report_status_kind 'FAIL(assertions:2/3)')"
check "clone failure is a failure" \
  "FAIL" "$(report_status_kind 'FAIL(clone)')"
check "coordinator-run failure is a failure" \
  "FAIL" "$(report_status_kind 'FAIL(coordinator-run)')"
check "bare FAIL is still a failure" \
  "FAIL" "$(report_status_kind 'FAIL')"
check "PASS is unaffected" \
  "PASS" "$(report_status_kind 'PASS')"
check "blocked stays its own kind, not a failure" \
  "BLOCKED" "$(report_status_kind 'blocked')"
# A runtime that never ran is the only thing allowed to read as skipped.
check "an unrecorded runtime is a skip" \
  "SKIP" "$(report_status_kind 'SKIPPED')"

# --- Defect 2: two runtimes were launched wrong -----------------------------
# The harness launched the bare runtime name. `cursor` on PATH is the updater,
# not the agent: it exited at once, the pane fell back to a shell prompt, and
# the onboarding prompt was typed into bash. Assertions A and B passed anyway.
check "cursor launches the agent binary, not the updater" \
  "cursor-agent --force --trust" "$(runtime_launch_command cursor)"
check "cursor-agent spelling resolves the same way" \
  "cursor-agent --force --trust" "$(runtime_launch_command cursor-agent)"
check "agy gets its approval flag" \
  "agy --dangerously-skip-permissions" "$(runtime_launch_command agy)"
# The three that pass through the harness's own trust-prompt handler must keep
# launching bare; adding flags there would change behaviour that was measured
# working.
for rt in claude codex grok; do
  check "$rt launches unchanged" "$rt" "$(runtime_launch_command $rt)"
done

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
