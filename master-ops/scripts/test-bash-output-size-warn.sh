#!/usr/bin/env bash
# Small result: silent. Large stdout: one line naming the size. Malformed input: silent, exit 0.
set -u
H="$(cd "$(dirname "$0")" && pwd)/hooks/bash-output-size-warn.sh"; F=0
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"ok","stderr":""}}' | "$H"); [ -z "$o" ] && echo "  ok:   small result silent" || { echo "  FAIL: small result spoke: $o"; F=1; }
big=$(python3 -c "print('x'*7000)")
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$H"); case "$o" in *"7000 chars"*) echo "  ok:   large result named its size";; *) echo "  FAIL: large result: '$o'"; F=1;; esac
o=$(printf 'not json' | "$H"); rc=$?; [ $rc -eq 0 ] && [ -z "$o" ] && echo "  ok:   malformed input silent, exit 0" || { echo "  FAIL: malformed: rc=$rc '$o'"; F=1; }
o=$(printf '{"tool_response":{"stdout":"%s"}}' "$(python3 -c "print('y'*300)")" | MOGUI_BASH_OUTPUT_WARN_CHARS=100 "$H"); case "$o" in *"300 chars"*) echo "  ok:   threshold env honoured";; *) echo "  FAIL: env threshold: '$o'"; F=1;; esac
# Failability: a copy of the hook whose size comparison is disabled must fail the large-result check.
T=$(mktemp -d); sed 's/if n > thresh:/if False:/' "$H" > "$T/hook.sh"; chmod +x "$T/hook.sh"
o=$(printf '{"tool_name":"Bash","tool_response":{"stdout":"%s","stderr":""}}' "$big" | "$T/hook.sh"); [ -z "$o" ] && echo "  ok:   failability: disabled comparison stays silent, so the large-result check would fail" || { echo "  FAIL: failability: mutant still warned: $o"; F=1; }
rm -rf "$T"
[ $F -eq 0 ] && echo "test-bash-output-size-warn: OK" || { echo "test-bash-output-size-warn: FAILED"; exit 1; }
