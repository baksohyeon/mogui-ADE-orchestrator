#!/usr/bin/env bash
# scripts/harness-inventory: ranks ledger-declared harness parts by estimated
# token cost, with a --check gate for parts missing a ledger row or a row
# missing a required field. macOS bash 3.2 safe.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/harness-inventory"
F=0

expect() {
  want="$1" got="$2" label="$3" out="$4"
  [ "$got" = "$want" ] && echo "  ok:   $label" || { echo "  FAIL: $label want=$want got=$got: $out"; F=1; }
}

contains() {
  case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac
}

expect_contains() {
  haystack="$1" needle="$2" label="$3"
  if contains "$haystack" "$needle"; then
    echo "  ok:   $label"
  else
    echo "  FAIL: $label: missing '$needle' in: $haystack"
    F=1
  fi
}

# Case 1: ranking order, the `*` mark on a measured_tokens row, and `absent`
# for a ledger row whose key does not exist under root.
scratch="$(mktemp -d)"
mkdir -p "$scratch/skills/foo" "$scratch/docs/evals"
printf 'short skill body, well under five hundred tokens of ascii text.\n' >"$scratch/skills/foo/SKILL.md"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{
  "measured_at": "2026-01-01",
  "parts": [
    {"key": "skills/foo/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"},
    {"key": "hook-stdout-foo", "kind": "hook", "loads": "every session", "status": "untested", "plan": "none (grandfathered)", "measured_tokens": 500, "measured_on": "2026-01-01"},
    {"key": "skills/missing/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
  ]
}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "default table run exits 0" "$out"
expect_contains "$out" "estimate, about" "the estimate caveat line is printed" "$out"
first_row=$(printf '%s\n' "$out" | grep "hook-stdout-foo")
expect_contains "$first_row" "| 1 |" "the measured_tokens row ranks first (500 > estimate)" "$out"
expect_contains "$first_row" "500*" "the measured_tokens row is marked with *" "$out"
foo_row=$(printf '%s\n' "$out" | grep "skills/foo/SKILL.md")
expect_contains "$foo_row" "| 2 |" "the estimated skill row ranks second" "$out"
if contains "$foo_row" "*"; then
  echo "  FAIL: an estimated (non-measured_tokens) row must not be marked with *: $out"
  F=1
else
  echo "  ok:   the estimated row carries no * mark"
fi
missing_row=$(printf '%s\n' "$out" | grep "skills/missing/SKILL.md")
expect_contains "$missing_row" "| 3 |" "the absent row ranks last" "$out"
expect_contains "$missing_row" "absent" "a ledger key with no file on disk prints absent" "$out"
rm -rf "$scratch"

# Case 2: --json prints the same ranked rows as JSON.
scratch="$(mktemp -d)"
mkdir -p "$scratch/skills/foo" "$scratch/docs/evals"
printf 'x\n' >"$scratch/skills/foo/SKILL.md"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/foo/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --json 2>&1); rc=$?
expect 0 "$rc" "--json exits 0" "$out"
expect_contains "$out" '"key": "skills/foo/SKILL.md"' "--json names the part key" "$out"
rm -rf "$scratch"

# Case 3: --check exits 1 and names a skill file on disk with no ledger row.
scratch="$(mktemp -d)"
mkdir -p "$scratch/skills/foo" "$scratch/skills/bar" "$scratch/docs/evals"
printf 'x\n' >"$scratch/skills/foo/SKILL.md"
printf 'x\n' >"$scratch/skills/bar/SKILL.md"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/foo/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on a skill with no ledger row" "$out"
expect_contains "$out" "skills/bar/SKILL.md" "the offending skill path is named" "$out"
rm -rf "$scratch"

# Case 4: --check exits 1 and names a registered hook on disk with no ledger
# row.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts/hooks" "$scratch/docs/evals"
printf '#!/bin/sh\n' >"$scratch/scripts/hooks/example-warn.sh"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on a hook script with no ledger row" "$out"
expect_contains "$out" "scripts/hooks/example-warn.sh" "the offending hook path is named" "$out"
rm -rf "$scratch"

# Case 5: --check exits 1 on an untested row whose plan is not grandfathered
# but is missing measure_by (owner present).
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/unmeasured/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "first-use review", "owner": "master"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on an untested row missing measure_by" "$out"
expect_contains "$out" "skills/unmeasured/SKILL.md" "the offending row key is named" "$out"
expect_contains "$out" "measure_by" "the missing field is named" "$out"
rm -rf "$scratch"

# Case 6: --check exits 1 on a safety row with no reason, and on a helps row
# with no sources; exits 0 once both are fixed.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/guard.sh", "kind": "hook", "loads": "every use", "status": "safety"},
  {"key": "skills/measured/SKILL.md", "kind": "skill", "loads": "every use", "status": "helps"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on a safety row with no reason and a helps row with no sources" "$out"
expect_contains "$out" "scripts/hooks/guard.sh" "the safety row is named" "$out"
expect_contains "$out" "skills/measured/SKILL.md" "the helps row is named" "$out"
cat >"$scratch/docs/evals/evidence.json" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/guard.sh", "kind": "hook", "loads": "every use", "status": "safety", "reason": "stops an irreversible write"},
  {"key": "skills/measured/SKILL.md", "kind": "skill", "loads": "every use", "status": "helps", "sources": ["trial-1"]}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 0 "$rc" "--check exits 0 once reason and sources are present" "$out"
rm -rf "$scratch"

# Case 7: against the repository itself, with no --root/--ledger override,
# the seeded template ledger passes --check clean (exit 0).
out=$("$SCRIPT" --check 2>&1); rc=$?
expect 0 "$rc" "--check exits 0 on the seeded template ledger against the repository itself" "$out"

# Case 8: a non-directory --root is a usage error (exit 2), not a silent
# empty report.
out=$("$SCRIPT" --root "/nonexistent-$$-dir" 2>&1); rc=$?
expect 2 "$rc" "missing --root exits 2" "$out"

# Case 9: a malformed ledger (parts is not a list) exits 2 and names the path.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
printf '{"measured_at": "2026-01-01", "parts": "nope"}\n' >"$scratch/docs/evals/evidence.json"
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 2 "$rc" "a parts value that is not a list exits 2" "$out"
rm -rf "$scratch"

[ "$F" -eq 0 ] && exit 0 || exit 1
