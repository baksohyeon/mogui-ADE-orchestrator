#!/usr/bin/env bash
# The banner must name only hooks that a settings command references, and name the rest as NOT WIRED.
set -u
T="$(cd "$(dirname "$0")" && pwd)/hooks/tracker-check.sh"; TMP=$(mktemp -d); F=0
mkdir -p "$TMP/hooks"; for n in a-guard.sh b-warn.sh tracker-check.sh; do : > "$TMP/hooks/$n"; done
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash /x/hooks/a-guard.sh"}]}]}}' > "$TMP/settings.json"
out=$(MOGUI_SETTINGS_FILE="$TMP/settings.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$T" 2>/dev/null | grep '^\[protections\]')
case "$out" in *"wired: a-guard"*) echo "  ok:   wired hook named active";; *) echo "  FAIL: '$out'"; F=1;; esac
case "$out" in *"NOT WIRED: b-warn"*) echo "  ok:   shipped-but-unwired hook named NOT WIRED";; *) echo "  FAIL: unwired not named: '$out'"; F=1;; esac
wired_part=${out%%|*}; case "$wired_part" in *"b-warn"*) echo "  FAIL: unwired hook listed as wired: '$out'"; F=1;; *) echo "  ok:   unwired hook absent from the wired list";; esac
# A hook whose name appears in settings only inside a comment-like value, not as an invoked path, must stay NOT WIRED.
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash /x/hooks/a-guard.sh"},{"command":"echo see-also-b-warn.sh-disabled"}]}]}}' > "$TMP/settings2.json"
out2=$(MOGUI_SETTINGS_FILE="$TMP/settings2.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$T" 2>/dev/null | grep '^\[protections\]')
case "${out2%%|*}" in *"b-warn"*) echo "  FAIL: mentioned-but-not-invoked hook counted as wired: '$out2'"; F=1;; *) echo "  ok:   mentioned-but-not-invoked hook stays NOT WIRED";; esac
# Failability: a copy of the hook that reads no settings must call the wired hook NOT WIRED.
sed 's/^wired_blob=\$(python3 -c/wired_blob=""; _ignored=\$(python3 -c/' "$T" > "$TMP/mutant.sh"
mout=$(MOGUI_SETTINGS_FILE="$TMP/settings.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$TMP/mutant.sh" 2>/dev/null | grep '^\[protections\]')
case "$mout" in *"NOT WIRED:"*"a-guard"*) echo "  ok:   failability: a hook that reads no settings misreports a-guard, so the wired check would fail";; *) echo "  FAIL: failability: mutant still called a-guard wired: '$mout'"; F=1;; esac
rm -rf "$TMP"; [ $F -eq 0 ] && echo "test-tracker-check-banner: OK" || { echo "test-tracker-check-banner: FAILED"; exit 1; }
