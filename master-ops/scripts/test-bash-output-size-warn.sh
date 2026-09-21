#!/usr/bin/env bash
# Small result: silent. Large stdout: one line naming the size. Malformed input: silent, exit 0.
set -u
H="$(cd "$(dirname "$0")" && pwd)/hooks/bash-output-size-warn.sh"; F=0
SCRATCH_HOME="$(mktemp -d)"; export HOME="$SCRATCH_HOME"; trap 'rm -rf "$SCRATCH_HOME"' EXIT  # the hook appends a fire-log line under ~/.mogui; keep that out of the real home and remove it after
SCRATCH_FIRE_LOG="$SCRATCH_HOME/scratch-hook-fire.jsonl"
export MOGUI_HOOK_FIRE_LOG="$SCRATCH_FIRE_LOG"
last_verdict() {
  python3 - "$MOGUI_HOOK_FIRE_LOG" <<'PY'
import json, sys
lines = [ln.strip() for ln in open(sys.argv[1], encoding="utf-8") if ln.strip()]
entry = json.loads(lines[-1])
print(entry.get("verdict", ""))
PY
}
expect_verdict() {
  expected="$1"; label="$2"; got="$(last_verdict 2>/dev/null || true)"
  [ "$got" = "$expected" ] && echo "  ok:   $label verdict=$expected" || { echo "  FAIL: $label verdict expected=$expected got=${got:-<none>}"; F=1; }
}
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"ok","stderr":""}}' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   small result silent, exit 0" || { echo "  FAIL: small result: rc=$rc '$o'"; F=1; }
expect_verdict pass "small result"
big=$(python3 -c "print('x'*7000)")
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$H" 2>&1); rc=$?; case "$o" in *"7000 chars"*) [ $rc -eq 0 ] && [ "$(printf '%s' "$o" | wc -l | tr -d ' ')" -le 1 ] && echo "  ok:   large result named its size, one line, exit 0" || { echo "  FAIL: large result rc=$rc or extra lines: '$o'"; F=1; };; *) echo "  FAIL: large result: '$o'"; F=1;; esac
expect_verdict warn "large result"
o=$(printf 'not json' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   malformed input silent, exit 0" || { echo "  FAIL: malformed: rc=$rc '$o'"; F=1; }
expect_verdict skip "malformed input"
o=$(printf '[1,2,3]' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   non-object JSON silent, exit 0" || { echo "  FAIL: non-object JSON: rc=$rc '$o'"; F=1; }
o=$(printf '{"tool_response":{"stdout":"%s"}}' "$(python3 -c "print('y'*300)")" | MOGUI_BASH_OUTPUT_WARN_CHARS=100 "$H" 2>&1); rc=$?; case "$o" in *"300 chars"*) [ $rc -eq 0 ] && echo "  ok:   threshold env honoured, exit 0" || { echo "  FAIL: env threshold rc=$rc"; F=1; };; *) echo "  FAIL: env threshold: '$o'"; F=1;; esac
o=$(printf '{"tool_response":{"stdout":"%s"}}' "$big" | MOGUI_BASH_OUTPUT_WARN_CHARS=abc "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   invalid threshold stays silent, exit 0" || { echo "  FAIL: invalid threshold: rc=$rc '$o'"; F=1; }
expect_verdict skip "invalid threshold"
# Failability: a copy of the hook whose size comparison is disabled must fail the large-result check.
T=$(mktemp -d); sed 's/if n > thresh:/if False:/' "$H" > "$T/hook.sh"; chmod +x "$T/hook.sh"
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$T/hook.sh"); [ -z "$o" ] && echo "  ok:   failability: disabled comparison stays silent, so the large-result check would fail" || { echo "  FAIL: failability: mutant still warned: $o"; F=1; }
# Failability: a copy that forces warn to pass must be caught by the verdict assertion.
python3 - "$H" > "$T/hook3.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
sys.stdout.write(s.replace('VERDICT="warn"', 'VERDICT="pass"', 1))
PY
chmod +x "$T/hook3.sh"
printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$T/hook3.sh" >/dev/null 2>&1
got="$(last_verdict 2>/dev/null || true)"
[ "$got" = "pass" ] && echo "  ok:   failability: verdict mutant produces pass instead of warn, so verdict assertion would fail" || { echo "  FAIL: failability: verdict mutant did not alter verdict as expected"; F=1; }
# Failability: a copy with a broken shell guard should violate the skip verdict.
python3 - "$H" > "$T/hook2.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
guarded = 'if ! [ "$THRESH" -eq "$THRESH" ] 2>/dev/null; then\n  VERDICT="skip"\n  exit 0\nfi\n'
assert s.count(guarded) == 1, "shell threshold guard not found exactly once"
mutant = 'if ! [ "$THRESH" -eq "$THRESH" ] 2>/dev/null; then\n  VERDICT="pass"\n  exit 0\nfi\n'
sys.stdout.write(s.replace(guarded, mutant))
PY
chmod +x "$T/hook2.sh"
o=$(printf '{"tool_response":{"stdout":"x"}}' | MOGUI_BASH_OUTPUT_WARN_CHARS=abc "$T/hook2.sh" 2>&1)
[ -z "$o" ] && [ "$(last_verdict 2>/dev/null || true)" = "pass" ] && echo "  ok:   failability: broken invalid-threshold guard flips skip->pass, so skip assertion would fail" || { echo "  FAIL: failability: broken guard did not alter invalid-threshold verdict"; F=1; }
rm -rf "$T"
[ $F -eq 0 ] && echo "test-bash-output-size-warn: OK" || { echo "test-bash-output-size-warn: FAILED"; exit 1; }
