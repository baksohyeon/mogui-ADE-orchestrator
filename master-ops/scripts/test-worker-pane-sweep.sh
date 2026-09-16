#!/usr/bin/env bash
# worker-pane-sweep must read the shared approval markers and classify a pane sitting on the codex
# hook-trust modal as `approval`# with exit 1, and must leave an idle pane at `idle` with exit 0. The sweep reads panes through
# bare `orca`, so a fake orca on PATH feeds it one pane whose frame is $SWEEP_FRAME.
set -u
SWEEP="$(cd "$(dirname "$0")" && pwd)/worker-pane-sweep"; FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }; ok() { echo "  ok:   $*"; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cat > "$T/orca" <<'FAKE'
#!/usr/bin/env bash
case "$1 $2" in
  "terminal list") echo "term_00000000-0000-0000-0000-000000000001  fake worker pane";;
  "terminal read") printf '%s\n' "$SWEEP_FRAME";;
esac
FAKE
chmod +x "$T/orca"

grep -Fq 'approval-prompt-markers.txt' "$SWEEP" && ok "sweep reads the shared marker file" || fail "sweep does not reference approval-prompt-markers.txt"
grep -qE 'grep -qE "do you want to proceed' "$SWEEP" && fail "sweep still carries an inline marker list" || ok "sweep carries no inline marker list"

run() { env -u ORCA_TERMINAL_HANDLE SWEEP_FRAME="$1" PATH="$T:$PATH" "$SWEEP" 2>&1; }
expect() { # label frame verdict exit
  out=$(run "$2"); rc=$?
  line=$(printf '%s\n' "$out" | grep -E "^[A-Za-z]+ +$3 " || true)
  [ -n "$line" ] && [ "$rc" -eq "$4" ] && ok "$1: verdict $3, exit $rc" || fail "$1: expected $3/exit $4, got exit $rc: $(printf '%s' "$out" | head -3 | tr '\n' '|')"
}

# Verbatim pane preview of the codex 0.154.0 modal, 2026-09-15.
MODAL='Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.
1. Review hooks
2. Trust all and continue
3. Continue without trusting
Press enter to confirm or esc to go back'
expect "codex hook-trust modal" "$MODAL" approval 1
expect "proceed question" 'Do you want to proceed?' approval 1
# Each new marker alone, so removing any one of them fails here and not only in the modal sample.
expect "marker alone: hooks need review" 'Hooks need review' approval 1
expect "marker alone: trust all and continue" 'Trust all and continue' approval 1
expect "marker alone: press enter to confirm" 'Press enter to confirm' approval 1
expect "idle prompt" '❯ ' idle 0
expect "idle prompt under a status line that says always-approve bypass permissions" 'always-approve bypass permissions
❯ ' idle 0

[ "$FAILED" -eq 0 ] && echo "worker-pane-sweep: all checks passed" || { echo "worker-pane-sweep: FAILED"; exit 1; }
