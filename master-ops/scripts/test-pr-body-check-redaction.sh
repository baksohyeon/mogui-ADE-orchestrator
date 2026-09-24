#!/usr/bin/env bash
# Coverage for scripts/pr-body-check's redaction glob guard `(?<!\*)`: a glob
# segment like codex-accounts/*/home/sessions must pass, a real leak must
# still fail — including one that follows an unrelated asterisk elsewhere on
# the line, which a naive "line contains *" guard would wrongly excuse.
set -u

S="$(cd "$(dirname "$0")" && pwd)"
CHECK="$S/pr-body-check"
F=0

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

cat >"$T/template.md" <<'EOF'
## Problem


## Why this approach


## What this changes


## Expected effect

EOF

body_with() {
  cat <<EOF
## Problem
Fixture.

## Why this approach
$1

## What this changes
Nothing else.

## Expected effect
Fixture.
EOF
}

ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }

run_check() {
  local body_file="$1"
  bash "$CHECK" 999 --repo test/test --body-file "$body_file" --template-file "$T/template.md" 2>&1
}

# 1. A glob segment must not be flagged as a leak.
body_with "Because codex-accounts/*/home/sessions is a glob, not a leak." >"$T/glob.md"
out="$(run_check "$T/glob.md")"; rc=$?
if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -q "Redaction violations detected"; then
  ok "glob segment passes clean"
else
  fail "glob segment wrongly flagged (exit=$rc)"; echo "       got: $out"
fi

# 2. A real leak must still be flagged.
body_with "Testing /Users/realuser/notes shows up." >"$T/leak.md"
out="$(run_check "$T/leak.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path\]"; then
  ok "real /Users leak is flagged"
else
  fail "real /Users leak not flagged (exit=$rc)"; echo "       got: $out"
fi

# 3. A real leak preceded by an unrelated asterisk elsewhere on the line must
#    still be flagged — the guard excuses a glob segment, not "any line with
#    a star in it".
body_with "Note: *warning* /home/realuser/leak-here needs redaction." >"$T/leak-after-star.md"
out="$(run_check "$T/leak-after-star.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path_linux\]"; then
  ok "real /home leak after an unrelated asterisk is still flagged"
else
  fail "real /home leak after an unrelated asterisk was excused (exit=$rc)"; echo "       got: $out"
fi

# Failability: a mutant that drops the (?<!\*) guard must flag the glob
# fixture, proving case 1 above actually exercises the guard.
MUT="$T/pr-body-check.mutant"
sed -E 's/\(\?<!\\\*\)//g' "$CHECK" >"$MUT"
chmod +x "$MUT"
mut_out="$(bash "$MUT" 999 --repo test/test --body-file "$T/glob.md" --template-file "$T/template.md" 2>&1)"
if printf '%s' "$mut_out" | grep -q "Redaction violations detected"; then
  ok "failability: mutant without the guard flags the glob fixture"
else
  fail "failability: mutant still passed the glob fixture clean"; echo "       got: $mut_out"
fi

echo "----"
[ "$F" -eq 0 ] && echo "pass" || echo "fail"
exit "$F"
