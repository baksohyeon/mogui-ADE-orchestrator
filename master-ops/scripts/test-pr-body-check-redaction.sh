#!/usr/bin/env bash
# Coverage for scripts/pr-body-check's redaction glob guard: a glob segment
# like codex-accounts/*/home/sessions must pass, a real leak must still fail
# — including one that follows an unrelated asterisk elsewhere on the line,
# one that precedes a glob segment in the same token, and one that is joined
# to a glob path by a comma inside one whitespace token. The guard judges
# each pattern match on its own, never the whole token.
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

# Fixture paths are assembled at runtime so this file itself never carries a
# literal home path the redaction gate would flag.
GLOB_PATH="codex-accounts/*/home/sessions"
USERS_LEAK="/Users/""realuser/notes"
HOME_LEAK="/home/""realuser/leak-here"
REAL_THEN_GLOB="/Users/""realuser4/*/notes"
COMMA_JOINED="codex-accounts/*/home/sessions,/Users/""realuser5"

# 1. A glob segment must not be flagged as a leak.
body_with "Because $GLOB_PATH is a glob, not a leak." >"$T/glob.md"
out="$(run_check "$T/glob.md")"; rc=$?
if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -q "Redaction violations detected"; then
  ok "glob segment passes clean"
else
  fail "glob segment wrongly flagged (exit=$rc)"; echo "       got: $out"
fi

# 2. A real leak must still be flagged.
body_with "Testing $USERS_LEAK shows up." >"$T/leak.md"
out="$(run_check "$T/leak.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path\]"; then
  ok "real /Users leak is flagged"
else
  fail "real /Users leak not flagged (exit=$rc)"; echo "       got: $out"
fi

# 3. A real leak preceded by an unrelated asterisk elsewhere on the line must
#    still be flagged — the guard excuses a glob segment, not "any line with
#    a star in it".
body_with "Note: *warning* $HOME_LEAK needs redaction." >"$T/leak-after-star.md"
out="$(run_check "$T/leak-after-star.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path_linux\]"; then
  ok "real /home leak after an unrelated asterisk is still flagged"
else
  fail "real /home leak after an unrelated asterisk was excused (exit=$rc)"; echo "       got: $out"
fi

# 4. A real leak immediately followed by a glob segment in the same token
#    must still be flagged — the glob comes after the genuine leak, not
#    before it.
body_with "See $REAL_THEN_GLOB for details." >"$T/real-then-glob.md"
out="$(run_check "$T/real-then-glob.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path\]"; then
  ok "real path before a glob segment in the same token is still flagged"
else
  fail "real path before a glob segment in the same token was excused (exit=$rc)"; echo "       got: $out"
fi

# 5. A glob path and a real leak joined by a comma inside one
#    whitespace-delimited token must still flag the real leak, even though
#    a naive per-token guard would excuse the whole token.
body_with "Paths: $COMMA_JOINED are relevant." >"$T/comma-joined.md"
out="$(run_check "$T/comma-joined.md")"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "\[home_path\]"; then
  ok "comma-joined real leak is still flagged"
else
  fail "comma-joined real leak was excused (exit=$rc)"; echo "       got: $out"
fi

# Failability: a mutant that disables the glob guard entirely must flag the
# glob-only fixture, proving case 1 above actually exercises the guard.
MUT="$T/pr-body-check.mutant"
sed -E 's/if glob_segment_re\.search\(candidate\[: match\.start\(\) \+ 1\]\):/if False:  # mutant: glob guard removed/' "$CHECK" >"$MUT"
chmod +x "$MUT"
mut_out="$(bash "$MUT" 999 --repo test/test --body-file "$T/glob.md" --template-file "$T/template.md" 2>&1)"
if printf '%s' "$mut_out" | grep -q "Redaction violations detected"; then
  ok "failability: mutant without the guard flags the glob fixture"
else
  fail "failability: mutant still passed the glob fixture clean"; echo "       got: $mut_out"
fi

# Failability: a mutant that judges the whole candidate instead of only the
# text before the match must wrongly excuse fixture 4 (proves the fix judges
# per match, not per token).
MUT2="$T/pr-body-check.mutant2"
sed -E 's/glob_segment_re\.search\(candidate\[: match\.start\(\) \+ 1\]\)/glob_segment_re.search(candidate)/' "$CHECK" >"$MUT2"
chmod +x "$MUT2"
mut_out2="$(bash "$MUT2" 999 --repo test/test --body-file "$T/real-then-glob.md" --template-file "$T/template.md" 2>&1)"
if ! printf '%s' "$mut_out2" | grep -q "Redaction violations detected"; then
  ok "failability: whole-candidate mutant excuses the real-then-glob fixture"
else
  fail "failability: whole-candidate mutant still flagged the real-then-glob fixture"; echo "       got: $mut_out2"
fi

# Failability: a mutant that drops the comma split must wrongly excuse
# fixture 5 (proves the fix splits candidates on commas, not just whitespace).
MUT3="$T/pr-body-check.mutant3"
sed -E 's/candidates = \[c for piece in line\.split\(\) for c in piece\.split\(","\) if c\]/candidates = line.split()/' "$CHECK" >"$MUT3"
chmod +x "$MUT3"
mut_out3="$(bash "$MUT3" 999 --repo test/test --body-file "$T/comma-joined.md" --template-file "$T/template.md" 2>&1)"
if ! printf '%s' "$mut_out3" | grep -q "Redaction violations detected"; then
  ok "failability: no-comma-split mutant excuses the comma-joined fixture"
else
  fail "failability: no-comma-split mutant still flagged the comma-joined fixture"; echo "       got: $mut_out3"
fi

echo "----"
[ "$F" -eq 0 ] && echo "pass" || echo "fail"
exit "$F"
