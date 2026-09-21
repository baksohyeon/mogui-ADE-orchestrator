#!/usr/bin/env bash
# Verdict coverage for hooks that previously had no dedicated tests.
set -u

S="$(cd "$(dirname "$0")" && pwd)"
TRIM="$S/hooks/bash-output-trim-warn.sh"
INBOX="$S/hooks/orch-inbox-warn.sh"
ROLE="$S/hooks/role-state-inject.sh"
BARE_CD="$S/hooks/bash-bare-cd-warn.sh"
POLL="$S/hooks/bash-poll-warn.sh"
F=0

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
LOG="$T/fire.jsonl"

ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }
last_verdict() {
  python3 - "$LOG" <<'PY'
import json, sys
lines = [ln.strip() for ln in open(sys.argv[1], encoding="utf-8") if ln.strip()]
print(json.loads(lines[-1]).get("verdict", ""))
PY
}
assert_verdict() {
  expected="$1"; label="$2"; got="$(last_verdict 2>/dev/null || true)"
  [ "$got" = "$expected" ] && ok "$label verdict=$expected" || fail "$label verdict expected=$expected got=${got:-<none>}"
}

# bash-output-trim-warn: pass/warn/skip
out=$(printf '{"tool_input":{"command":"git log | head -1"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$TRIM" 2>&1)
[ -z "$out" ] && ok "trim-warn pass path stays silent" || fail "trim-warn pass path printed: $out"
assert_verdict pass "trim-warn pass path"
out=$(printf '{"tool_input":{"command":"git diff"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$TRIM" 2>&1)
printf '%s' "$out" | grep -q '\[trim-warn\]' && ok "trim-warn warn path prints warning" || fail "trim-warn warn path missing warning"
assert_verdict warn "trim-warn warn path"
out=$(printf 'not json' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$TRIM" 2>&1)
[ -z "$out" ] && ok "trim-warn skip path stays silent" || fail "trim-warn skip path printed: $out"
assert_verdict skip "trim-warn skip path"

# orch-inbox-warn: pass/warn/skip using a fake orca.
mkdir -p "$T/bin"
cat > "$T/bin/orca" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2 $3" = "orchestration check --peek" ]; then
  printf '%s\n' "$FAKE_ORCA_JSON"
  exit 0
fi
exit 1
EOF
chmod +x "$T/bin/orca"
FAKE_ORCA_JSON='{"result":{"messages":[]}}' PATH="$T/bin:$PATH" MOGUI_HOOK_FIRE_LOG="$LOG" bash "$INBOX" >/dev/null 2>&1
assert_verdict pass "orch-inbox pass path"
FAKE_ORCA_JSON='{"result":{"messages":[{"type":"worker_done","subject":"needs-review"}]}}' PATH="$T/bin:$PATH" MOGUI_HOOK_FIRE_LOG="$LOG" bash "$INBOX" >"$T/inbox.out" 2>&1
grep -q '\[orch-inbox\] unacked=1' "$T/inbox.out" && ok "orch-inbox warn path prints warning" || fail "orch-inbox warn path missing warning output"
assert_verdict warn "orch-inbox warn path"
cat > "$T/bin/orca-fail" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T/bin/orca-fail"
ln -sf "$T/bin/orca-fail" "$T/bin/orca"
PATH="$T/bin:$PATH" MOGUI_HOOK_FIRE_LOG="$LOG" bash "$INBOX" >/dev/null 2>&1
assert_verdict skip "orch-inbox skip path"

# role-state-inject: pass on readable role-state; warn via unreadable-path mutant.
ROLE_STATE="$S/../docs/runbooks/role-state.md"
python3 - "$ROLE" "$ROLE_STATE" > "$T/role.pass.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
for line in s.splitlines(True):
    if line.startswith("RS="):
        sys.stdout.write(f"RS={sys.argv[2]}\n")
    else:
        sys.stdout.write(line)
PY
chmod +x "$T/role.pass.sh"
MOGUI_HOOK_FIRE_LOG="$LOG" bash "$T/role.pass.sh" >/dev/null 2>&1
assert_verdict pass "role-state pass path"
python3 - "$T/role.pass.sh" > "$T/role.warn.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
out = []
for line in s.splitlines(True):
    if line.startswith("RS="):
        out.append("RS=/nonexistent/role-state.md\n")
    else:
        out.append(line)
sys.stdout.write("".join(out))
PY
chmod +x "$T/role.warn.sh"
MOGUI_HOOK_FIRE_LOG="$LOG" bash "$T/role.warn.sh" >"$T/role.out" 2>&1
grep -q '\[role-state\] WARNING:' "$T/role.out" && ok "role-state warn path prints warning" || fail "role-state warn path missing warning output"
assert_verdict warn "role-state warn path"

# bash-bare-cd-warn: pass/warn/skip
out=$(printf '{"tool_input":{"command":"git status"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$BARE_CD" 2>&1)
[ -z "$out" ] && ok "bare-cd pass path stays silent" || fail "bare-cd pass path printed: $out"
assert_verdict pass "bare-cd pass path"
out=$(printf '{"tool_input":{"command":"cd /tmp"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$BARE_CD" 2>&1)
printf '%s' "$out" | grep -q '\[bash-bare-cd-warn\]' && ok "bare-cd warn path prints warning" || fail "bare-cd warn path missing warning"
assert_verdict warn "bare-cd warn path"
out=$(printf 'not json' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$BARE_CD" 2>&1)
[ -z "$out" ] && ok "bare-cd skip path stays silent" || fail "bare-cd skip path printed: $out"
assert_verdict skip "bare-cd skip path"

# bash-poll-warn: pass/warn/skip
out=$(printf '{"tool_input":{"command":"git status"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$POLL" 2>&1)
[ -z "$out" ] && ok "poll-warn pass path stays silent" || fail "poll-warn pass path printed: $out"
assert_verdict pass "poll-warn pass path"
out=$(printf '{"tool_input":{"command":"while true; do sleep 5; orca orchestration check --terminal t --json; done"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$POLL" 2>&1)
printf '%s' "$out" | grep -q '\[bash-poll-warn\]' && ok "poll-warn warn path prints warning" || fail "poll-warn warn path missing warning"
assert_verdict warn "poll-warn warn path"
out=$(printf 'not json' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$POLL" 2>&1)
[ -z "$out" ] && ok "poll-warn skip path stays silent" || fail "poll-warn skip path printed: $out"
assert_verdict skip "poll-warn skip path"

# Failability: a trim-warn mutant that downgrades warn to pass should break verdict expectations.
python3 - "$TRIM" > "$T/trim.mut.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
sys.stdout.write(s.replace('VERDICT="warn"', 'VERDICT="pass"', 1))
PY
chmod +x "$T/trim.mut.sh"
printf '{"tool_input":{"command":"git diff"}}' | MOGUI_HOOK_FIRE_LOG="$LOG" bash "$T/trim.mut.sh" >/dev/null 2>&1
got="$(last_verdict 2>/dev/null || true)"
[ "$got" = "pass" ] && ok "failability: trim mutant flips warn->pass so warn assertion would fail" || fail "failability: trim mutant did not change verdict as expected"

[ "$F" -eq 0 ] && echo "test-hook-verdict: OK" || { echo "test-hook-verdict: FAILED"; exit 1; }
