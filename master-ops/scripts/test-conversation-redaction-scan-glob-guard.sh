#!/usr/bin/env bash
# Coverage for conversation-redaction-scan's scan_text glob guard: a glob
# segment must pass, a real leak must still fail — including one that
# precedes a glob segment in the same candidate, and one joined to a glob
# path by a comma inside one whitespace token. scan_text runs under the
# script's own `set -euo pipefail`, so a candidate that matches no pattern
# must not abort the scan (the regression this file guards against).
set -u

S="$(cd "$(dirname "$0")" && pwd)"
SCAN="$S/conversation-redaction-scan"
F=0
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }

# Build a standalone harness from a (possibly mutated) copy of the script:
# the same PATTERNS declaration plus the extracted scan_text function,
# executed under set -euo pipefail exactly like the real script.
build_harness() {
  local src="$1" out="$2"
  {
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'declare -a PATTERNS=(\n  "home_path:/Users/[A-Za-z0-9._-]+"\n  "home_path_linux:/home/[A-Za-z0-9._-]+"\n)\n'
    sed -n '/^scan_text()/,/^}/p' "$src"
    printf 'scan_text "$@"\n'
  } >"$out"
  chmod +x "$out"
}

HARNESS="$T/harness.sh"
build_harness "$SCAN" "$HARNESS"

run() { "$HARNESS" surf 1 auth loc "$1"; }

# Fixture paths are assembled at runtime so this file itself never carries a
# literal home path the redaction gate would flag.
GLOB_PATH="codex-accounts/*/home/sessions"
REAL_THEN_GLOB="/Users/""realuser6/*/notes"
COMMA_JOINED="codex-accounts/*/home/sessions,/Users/""realuser7"
PLAIN_LEAK="/Users/""realuser8/notes"
NO_MATCH="just some ordinary line with no leak in it"

out="$(run "$GLOB_PATH")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
  ok "glob segment passes clean"
else
  fail "glob segment wrongly flagged (rc=$rc)"; echo "       got: $out"
fi

out="$(run "$REAL_THEN_GLOB")"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "home_path$"; then
  ok "real path before a glob segment in the same candidate is still flagged"
else
  fail "real path before a glob segment was excused (rc=$rc)"; echo "       got: $out"
fi

out="$(run "$COMMA_JOINED")"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "home_path$"; then
  ok "comma-joined real leak is still flagged"
else
  fail "comma-joined real leak was excused (rc=$rc)"; echo "       got: $out"
fi

out="$(run "$PLAIN_LEAK")"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "home_path$"; then
  ok "plain real leak is flagged"
else
  fail "plain real leak not flagged (rc=$rc)"; echo "       got: $out"
fi

# Regression: an ordinary candidate matching neither pattern (the common
# case for real scanned text) must not abort scan_text under set -e.
out="$(run "$NO_MATCH")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
  ok "line with no leak does not abort the scan"
else
  fail "line with no leak aborted or misfired (rc=$rc)"; echo "       got: $out"
fi

# Failability: a mutant that disables the glob guard entirely must flag the
# glob-only fixture, proving the guard is exercised.
MUT1="$T/scan.mutant1"
python3 -c "
import sys
src = open(sys.argv[1]).read()
old = '''grep -qE '(\\\\*/|/\\\\*/)' '''.strip()
assert old in src, 'guard pattern not found for mutant1'
open(sys.argv[2], 'w').write(src.replace(old, \"grep -qE 'NEVER_MATCHES_ANYTHING_XYZ'\"))
" "$SCAN" "$MUT1"
HARNESS1="$T/harness1.sh"
build_harness "$MUT1" "$HARNESS1"
mut_out="$("$HARNESS1" surf 1 auth loc "$GLOB_PATH")"
if [ -n "$mut_out" ]; then
  ok "failability: mutant without the guard flags the glob fixture"
else
  fail "failability: mutant still passed the glob fixture clean"
fi

# Failability: restoring the original unguarded `match=$(... | head -1)`
# capture must abort the scan on an ordinary non-matching candidate under
# set -euo pipefail — the exact regression this fix addresses.
MUT2="$T/scan.mutant2"
sed -E "s/if ! match=\"\\\$\\(printf '%s' \"\\\$candidate\" \\| grep -oE \"\\\$pattern_re\" \\| sed -n '1p'\\)\"; then/match=\"\$(printf '%s' \"\$candidate\" | grep -oE \"\$pattern_re\" | head -1)\"; if false; then/" "$SCAN" >"$MUT2"
HARNESS2="$T/harness2.sh"
build_harness "$MUT2" "$HARNESS2"
if ! "$HARNESS2" surf 1 auth loc "$NO_MATCH" >/tmp/mut2.$$ 2>&1; then
  ok "failability: unguarded capture aborts the scan on a non-matching candidate"
else
  fail "failability: unguarded capture no longer aborts (mutant not exercising the fix)"; cat /tmp/mut2.$$
fi
rm -f /tmp/mut2.$$

echo "----"
[ "$F" -eq 0 ] && echo "pass" || echo "fail"
exit "$F"
