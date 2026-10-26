#!/usr/bin/env bash
# The modal handler must (1) do nothing when the terminal is already idle, (2) answer with the
# retry id orca hands back when the first keystroke is refused, (3) fail loudly when blocked on
# something else. A fake orca on PATH replays the JSON shapes measured on 2026-09-14.
set -u
S="$(cd "$(dirname "$0")" && pwd)/codex-hooks-review-answer"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }; ok() { echo "  ok:   $*"; }
cat > "$T/orca" <<'FAKE'
#!/usr/bin/env bash
# scenario in $SCN; call log in $LOG
echo "$*" >> "$LOG"
case "$SCN:$1 $2" in
  idle:"terminal wait")     echo '{"ok":true,"result":{"wait":{"satisfied":true}}}';;
  modal:"terminal wait")
    n=$(grep -c 'terminal wait' "$LOG")
    if [ "$n" -le 1 ]; then echo '{"ok":true,"result":{"wait":{"satisfied":false,"blockedReason":"agent-hooks-review-prompt"}}}'
    else echo '{"ok":true,"result":{"wait":{"satisfied":true}}}'; fi;;
  modal:"terminal read")    echo 'Hooks need review. 2 hooks are new or changed.';;
  modal:"terminal send")
    case "$*" in *--retry-request*) echo '{"ok":true,"result":{"send":{"accepted":true}}}';;
      *) echo '{"ok":false,"error":{"code":"agent_prompt_blocked","data":{"orchestrationRequestId":"req-123"}}}';; esac;;
  other:"terminal wait")    echo '{"ok":true,"result":{"wait":{"satisfied":false,"blockedReason":"agent-login-prompt"}}}';;
  modal2:"terminal wait")
    n=$(grep -c 'terminal wait' "$LOG")
    if [ "$n" -le 1 ]; then echo '{"ok":true,"result":{"wait":{"satisfied":false,"blockedReason":"agent-hooks-review-prompt"}}}'
    else echo '{"ok":true,"result":{"wait":{"satisfied":false,"blockedReason":"agent-login-prompt"}}}'; fi;;
  modal2:"terminal read")   echo 'Hooks need review. 2 hooks are new or changed.';;
  modal2:"terminal send")
    case "$*" in *--retry-request*) echo '{"ok":true,"result":{"send":{"accepted":true}}}';;
      *) echo '{"ok":false,"error":{"code":"agent_prompt_blocked","data":{"orchestrationRequestId":"req-123"}}}';; esac;;
  other:"terminal read")    echo 'Sign in to continue';;
esac
FAKE
chmod +x "$T/orca"

export LOG="$T/log"; : > "$LOG"
SCN=idle ORCA_BIN="$T/orca" "$S" term_x >"$T/out" 2>&1; [ $? -eq 0 ] && grep -q 'not shown' "$T/out" && ok "idle terminal: exit 0, no keystroke sent ($(grep -c 'terminal send' "$LOG") sends)" || fail "idle: $(cat "$T/out")"
[ "$(grep -c 'terminal send' "$LOG")" -eq 0 ] || fail "idle: sent a keystroke to an idle terminal"

: > "$LOG"
SCN=modal ORCA_BIN="$T/orca" "$S" term_x >"$T/out" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "modal: exit 0" || fail "modal: exit $rc: $(cat "$T/out")"
grep -q -- '--retry-request req-123' "$LOG" && ok "modal: re-sent with the retry id orca returned" || fail "modal: no --retry-request req-123 in calls"
grep -q 'trusted 2 new/changed' "$T/out" && ok "modal: record names the count (2)" || fail "modal: count missing: $(cat "$T/out")"
[ "$(grep -c 'terminal wait' "$LOG")" -eq 2 ] && ok "modal: waited, answered, waited again" || fail "modal: wait count $(grep -c 'terminal wait' "$LOG")"

: > "$LOG"
SCN=other ORCA_BIN="$T/orca" "$S" term_x >"$T/out" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q 'agent-login-prompt' "$T/out" && ok "other prompt: exit 1, named the reason, did not answer" || fail "other: exit $rc: $(cat "$T/out")"
[ "$(grep -c 'terminal send' "$LOG")" -eq 0 ] || fail "other: sent a keystroke to a non-hook prompt"

# After answering, a different prompt must be reported by its own name, from the second wait.
: > "$LOG"
SCN=modal2 ORCA_BIN="$T/orca" "$S" term_x >"$T/out" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q 'still blocked after answering (agent-login-prompt)' "$T/out" && ok "modal then other: names the second prompt" || fail "modal then other: exit $rc: $(cat "$T/out" | tr '\n' ' ' | cut -c1-200)"
# Failability: a copy that never refreshes the reason names the first prompt instead.
: > "$LOG"; sed '/^W=\$(wait_once)$/{n;/^BLK=/d;}' "$S" > "$T/stale-mutant"; chmod +x "$T/stale-mutant"
if [ ! -f "$T/stale-mutant" ] || cmp -s "$S" "$T/stale-mutant"; then
  echo "FAIL: mutant not generated" >&2
  exit 1
fi
SCN=modal2 ORCA_BIN="$T/orca" "$T/stale-mutant" term_x >"$T/out" 2>&1 || true
grep -q 'still blocked after answering (agent-hooks-review-prompt)' "$T/out" && ok "failability: stale mutant names the first prompt, so the refresh check would fail" || fail "failability: stale mutant did not name the first prompt: $(cat "$T/out" | tr '\n' ' ' | cut -c1-200)"

# Unreachable orca: the fake prints nothing for an unknown scenario, so wait returns empty; exit 2 as documented.
: > "$LOG"
SCN=unreachable ORCA_BIN="$T/orca" "$S" term_x >"$T/out" 2>&1; rc=$?
[ $rc -eq 2 ] && grep -q 'unreachable' "$T/out" && ok "unreachable orca: exit 2, named" || fail "unreachable: exit $rc: $(cat "$T/out" | tr '\n' ' ' | cut -c1-160)"

# Failability: a copy of the script with the retry removed must leave no --retry-request in the call log.
: > "$LOG"; sed 's/--retry-request "\$RID" //' "$S" > "$T/answer-mutant"; chmod +x "$T/answer-mutant"
if [ ! -f "$T/answer-mutant" ] || cmp -s "$S" "$T/answer-mutant"; then
  echo "FAIL: mutant not generated" >&2
  exit 1
fi
SCN=modal ORCA_BIN="$T/orca" "$T/answer-mutant" term_x >"$T/out" 2>&1 || true
[ "$(grep -c -- '--retry-request req-123' "$LOG")" -eq 0 ] && ok "failability: mutant without the retry never re-sends, so the retry check would fail" || fail "failability: mutant still sent --retry-request"

[ $FAILED -eq 0 ] && echo "test-codex-hooks-review-answer: OK" || { echo "test-codex-hooks-review-answer: FAILED"; exit 1; }
