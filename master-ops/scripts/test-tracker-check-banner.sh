#!/usr/bin/env bash
# The banner must name only hooks that a settings command references, and name the rest as NOT WIRED.
set -u
T="$(cd "$(dirname "$0")" && pwd)/hooks/tracker-check.sh"; TMP=$(mktemp -d); F=0
LOG="$TMP/fire.jsonl"
REAL_LOG="$HOME/.mogui/hook-fire-log.jsonl"
real_before=$(wc -l < "$REAL_LOG" 2>/dev/null || echo 0)
mkdir -p "$TMP/hooks"; for n in a-guard.sh b-warn.sh tracker-check.sh; do : > "$TMP/hooks/$n"; done
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash /x/hooks/a-guard.sh"}]}]}}' > "$TMP/settings.json"
out=$(env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" MOGUI_SETTINGS_FILE="$TMP/settings.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$T" 2>/dev/null | grep '^\[protections\]')
case "$out" in *"wired: a-guard"*) echo "  ok:   wired hook named active";; *) echo "  FAIL: '$out'"; F=1;; esac
case "$out" in *"NOT WIRED: b-warn"*) echo "  ok:   shipped-but-unwired hook named NOT WIRED";; *) echo "  FAIL: unwired not named: '$out'"; F=1;; esac
wired_part=${out%%|*}; case "$wired_part" in *"b-warn"*) echo "  FAIL: unwired hook listed as wired: '$out'"; F=1;; *) echo "  ok:   unwired hook absent from the wired list";; esac
# A hook whose name appears in settings only inside a comment-like value, not as an invoked path, must stay NOT WIRED.
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash /x/hooks/a-guard.sh"},{"command":"echo see-also-b-warn.sh-disabled"}]}]}}' > "$TMP/settings2.json"
out2=$(env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" MOGUI_SETTINGS_FILE="$TMP/settings2.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$T" 2>/dev/null | grep '^\[protections\]')
case "${out2%%|*}" in *"b-warn"*) echo "  FAIL: mentioned-but-not-invoked hook counted as wired: '$out2'"; F=1;; *) echo "  ok:   mentioned-but-not-invoked hook stays NOT WIRED";; esac
# Failability: a copy of the hook that reads no settings must call the wired hook NOT WIRED.
sed 's/^wired_blob=\$(python3 -c/wired_blob=""; _ignored=\$(python3 -c/' "$T" > "$TMP/mutant.sh"
if [ ! -f "$TMP/mutant.sh" ] || cmp -s "$T" "$TMP/mutant.sh"; then
  echo "FAIL: mutant not generated" >&2
  exit 1
fi
mout=$(env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" MOGUI_SETTINGS_FILE="$TMP/settings.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$TMP/mutant.sh" 2>/dev/null | grep '^\[protections\]')
case "$mout" in *"NOT WIRED:"*"a-guard"*) echo "  ok:   failability: a hook that reads no settings misreports a-guard, so the wired check would fail";; *) echo "  FAIL: failability: mutant still called a-guard wired: '$mout'"; F=1;; esac
last_verdict() {
  python3 - "$LOG" <<'PY'
import json, sys
lines = [ln.strip() for ln in open(sys.argv[1], encoding="utf-8") if ln.strip()]
print(json.loads(lines[-1]).get("verdict", ""))
PY
}
# Verdict warn: unwired hooks emit NOT WIRED.
env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" MOGUI_SETTINGS_FILE="$TMP/settings.json" MOGUI_HOOKS_DIR="$TMP/hooks" WORKSPACE_ROOT="$TMP" bash "$T" >/dev/null 2>&1
v=$(last_verdict 2>/dev/null || true); [ "$v" = "warn" ] && echo "  ok:   verdict unwired hooks -> warn" || { echo "  FAIL: verdict for unwired hooks expected warn got ${v:-<none>}"; F=1; }
# Verdict pass: clean wiring and tracker resolution.
mkdir -p "$TMP/pass-root/{{OPS_REPO}}/.beads" "$TMP/pass-hooks" "$TMP/pass-bin"
printf '#!/usr/bin/env bash\necho "%s"\n' "$TMP/pass-root/{{OPS_REPO}}/.beads" > "$TMP/pass-bin/bd"; chmod +x "$TMP/pass-bin/bd"
: > "$TMP/pass-hooks/only-pass.sh"
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash /x/hooks/only-pass.sh"}]}]}}' > "$TMP/pass-settings.json"
env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" MOGUI_SETTINGS_FILE="$TMP/pass-settings.json" MOGUI_HOOKS_DIR="$TMP/pass-hooks" WORKSPACE_ROOT="$TMP/pass-root" PATH="$TMP/pass-bin:$PATH" bash "$T" >/dev/null 2>&1
v=$(last_verdict 2>/dev/null || true); [ "$v" = "pass" ] && echo "  ok:   verdict clean wiring -> pass" || { echo "  FAIL: verdict for clean wiring expected pass got ${v:-<none>}"; F=1; }
# Verdict skip: workspace root cannot be entered.
env -u BEADS_DIR MOGUI_HOOK_FIRE_LOG="$LOG" WORKSPACE_ROOT="$TMP/missing-root" bash "$T" >/dev/null 2>&1
v=$(last_verdict 2>/dev/null || true); [ "$v" = "skip" ] && echo "  ok:   verdict missing workspace -> skip" || { echo "  FAIL: verdict for missing workspace expected skip got ${v:-<none>}"; F=1; }
real_after=$(wc -l < "$REAL_LOG" 2>/dev/null || echo 0)
[ "$real_before" = "$real_after" ] && echo "  ok:   real hook fire log unchanged" || { echo "  FAIL: real hook fire log changed before=$real_before after=$real_after"; F=1; }
rm -rf "$TMP"; [ $F -eq 0 ] && echo "test-tracker-check-banner: OK" || { echo "test-tracker-check-banner: FAILED"; exit 1; }
