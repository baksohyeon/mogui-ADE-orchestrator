#!/usr/bin/env bash
# Small result: silent. Large stdout: one line naming the size. Malformed input: silent, exit 0.
set -u
H="$(cd "$(dirname "$0")" && pwd)/hooks/bash-output-size-warn.sh"; F=0
export HOME="$(mktemp -d)"  # the hook appends a fire-log line under ~/.mogui; keep that out of the real home
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"ok","stderr":""}}' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   small result silent, exit 0" || { echo "  FAIL: small result: rc=$rc '$o'"; F=1; }
big=$(python3 -c "print('x'*7000)")
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$H" 2>&1); rc=$?; case "$o" in *"7000 chars"*) [ $rc -eq 0 ] && [ "$(printf '%s' "$o" | wc -l | tr -d ' ')" -le 1 ] && echo "  ok:   large result named its size, one line, exit 0" || { echo "  FAIL: large result rc=$rc or extra lines: '$o'"; F=1; };; *) echo "  FAIL: large result: '$o'"; F=1;; esac
o=$(printf 'not json' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   malformed input silent, exit 0" || { echo "  FAIL: malformed: rc=$rc '$o'"; F=1; }
o=$(printf '[1,2,3]' | "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   non-object JSON silent, exit 0" || { echo "  FAIL: non-object JSON: rc=$rc '$o'"; F=1; }
o=$(printf '{"tool_response":{"stdout":"%s"}}' "$(python3 -c "print('y'*300)")" | MOGUI_BASH_OUTPUT_WARN_CHARS=100 "$H" 2>&1); rc=$?; case "$o" in *"300 chars"*) [ $rc -eq 0 ] && echo "  ok:   threshold env honoured, exit 0" || { echo "  FAIL: env threshold rc=$rc"; F=1; };; *) echo "  FAIL: env threshold: '$o'"; F=1;; esac
o=$(printf '{"tool_response":{"stdout":"%s"}}' "$big" | MOGUI_BASH_OUTPUT_WARN_CHARS=abc "$H" 2>&1); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   invalid threshold stays silent, exit 0" || { echo "  FAIL: invalid threshold: rc=$rc '$o'"; F=1; }
# Failability: a copy of the hook whose size comparison is disabled must fail the large-result check.
T=$(mktemp -d); sed 's/if n > thresh:/if False:/' "$H" > "$T/hook.sh"; chmod +x "$T/hook.sh"
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$T/hook.sh"); [ -z "$o" ] && echo "  ok:   failability: disabled comparison stays silent, so the large-result check would fail" || { echo "  FAIL: failability: mutant still warned: $o"; F=1; }
# Failability: a copy without the guard must speak (a traceback) on an invalid threshold.
python3 - "$H" > "$T/hook2.sh" <<'PY'
import sys
s = open(sys.argv[1]).read()
guarded = "try:\n    thresh = int(sys.argv[1])\nexcept (TypeError, ValueError):\n    sys.exit(0)\n"
assert s.count(guarded) == 1, "conversion guard not found exactly once"
sys.stdout.write(s.replace(guarded, "thresh = int(sys.argv[1])\n"))
PY
chmod +x "$T/hook2.sh"
o=$(printf '{"tool_response":{"stdout":"x"}}' | MOGUI_BASH_OUTPUT_WARN_CHARS=abc "$T/hook2.sh" 2>&1); [ -n "$o" ] && echo "  ok:   failability: unguarded conversion is not silent, so the invalid-threshold check would fail" || { echo "  FAIL: failability: unguarded mutant was silent"; F=1; }
rm -rf "$T"
[ $F -eq 0 ] && echo "test-bash-output-size-warn: OK" || { echo "test-bash-output-size-warn: FAILED"; exit 1; }
