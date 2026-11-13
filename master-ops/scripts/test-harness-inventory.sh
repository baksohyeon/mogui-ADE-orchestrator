#!/usr/bin/env bash
# scripts/harness-inventory: ranks ledger-declared harness parts by estimated
# token cost, with a --check gate for parts missing a ledger row or a row
# missing a required field. macOS bash 3.2 safe.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/harness-inventory"
TEMPLATE_LEDGER="docs/evals/evidence.json"
INSTANCE_LEDGER="docs/evals/evidence.instance.json"
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/guard.sh", "kind": "hook", "loads": "every use", "status": "safety"},
  {"key": "skills/measured/SKILL.md", "kind": "skill", "loads": "every use", "status": "helps"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on a safety row with no reason and a helps row with no sources" "$out"
expect_contains "$out" "scripts/hooks/guard.sh" "the safety row is named" "$out"
expect_contains "$out" "skills/measured/SKILL.md" "the helps row is named" "$out"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
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
scratch="$(mktemp -d)"
missing_root="$scratch/missing"
out=$("$SCRIPT" --root "$missing_root" 2>&1); rc=$?
expect 2 "$rc" "missing --root exits 2" "$out"
rm -rf "$scratch"

# Case 9: a malformed ledger (parts is not a list) exits 2 and names the
# ledger path (checked by suffix: the full $scratch path can differ after
# symlink resolution on macOS).
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
printf '{"measured_at": "2026-01-01", "parts": "nope"}\n' >"$scratch/$TEMPLATE_LEDGER"
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 2 "$rc" "a parts value that is not a list exits 2" "$out"
expect_contains "$out" "$TEMPLATE_LEDGER" "the error names the ledger path" "$out"
rm -rf "$scratch"

# Case 10: --check exits 1 on an untested row whose plan is not grandfathered
# and has measure_by but no owner (the mirror image of Case 5).
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/unowned/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "first-use review", "measure_by": "2026-12-11"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on an untested row missing owner" "$out"
expect_contains "$out" "skills/unowned/SKILL.md" "the offending row key is named" "$out"
expect_contains "$out" "needs owner" "the missing field is named" "$out"
rm -rf "$scratch"

# Case 11: a hook or dispatch row with no measured_tokens prints `exec`
# instead of a disk-size estimate, and ranks after every sized row.
scratch="$(mktemp -d)"
mkdir -p "$scratch/skills/foo" "$scratch/docs/evals"
printf 'x\n' >"$scratch/skills/foo/SKILL.md"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/foo/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"},
  {"key": "scripts/dispatch", "kind": "dispatch", "loads": "every dispatch", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "a ledger with an unsized dispatch row still exits 0" "$out"
foo_row=$(printf '%s\n' "$out" | grep "skills/foo/SKILL.md")
dispatch_row=$(printf '%s\n' "$out" | grep "scripts/dispatch")
expect_contains "$foo_row" "| 1 |" "the sized skill row ranks first" "$out"
expect_contains "$dispatch_row" "| 2 |" "the dispatch row ranks after the sized row" "$out"
expect_contains "$dispatch_row" "exec" "the dispatch row prints exec, not a byte-size estimate" "$out"
rm -rf "$scratch"

# Case 12: a duplicate ledger key is rejected at load (exit 2), not silently
# resolved to whichever row happened to load last.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/dup/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"},
  {"key": "skills/dup/SKILL.md", "kind": "skill", "loads": "every use", "status": "safety", "reason": "x"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 2 "$rc" "a duplicate ledger key exits 2" "$out"
expect_contains "$out" "skills/dup/SKILL.md" "the duplicate key is named" "$out"
rm -rf "$scratch"

# Case 13: a non-numeric measured_tokens is flagged by --check rather than
# silently falling through to absent.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "hook-stdout-foo", "kind": "hook", "loads": "every session", "status": "untested", "plan": "none (grandfathered)", "measured_tokens": "500"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "a non-numeric measured_tokens fails --check" "$out"
expect_contains "$out" "measured_tokens must be numeric" "the reason names measured_tokens" "$out"
rm -rf "$scratch"

# Case 14: a sources entry that is not a string is rejected at load (exit 2),
# instead of raising TypeError when the table tries to join it.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/measured/SKILL.md", "kind": "skill", "loads": "every use", "status": "helps", "sources": [1, "trial-2"]}
]}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 2 "$rc" "a non-string sources entry exits 2" "$out"
rm -rf "$scratch"

# Case 15: an untested row with no plan field at all needs a string plan,
# reported before owner/measure_by are ever considered.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/noplan/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "an untested row with no plan fails --check" "$out"
expect_contains "$out" "needs a string plan" "the reason names the missing plan" "$out"
rm -rf "$scratch"

# Case 16: a measure_by that does not match YYYY-MM-DD fails --check even
# though it is present.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/soon/SKILL.md", "kind": "skill", "loads": "every use", "status": "untested", "plan": "first-use review", "owner": "master", "measure_by": "soon"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "a malformed measure_by fails --check" "$out"
expect_contains "$out" "YYYY-MM-DD" "the reason names the required shape" "$out"
rm -rf "$scratch"

# Case 17: a non-string kind exits 2 with a ledger error, not an uncaught
# TypeError from an unhashable value inside a frozenset lookup.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "skills/weird/SKILL.md", "kind": ["skill"], "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 2 "$rc" "a non-string kind exits 2, not a traceback" "$out"
expect_contains "$out" "kind" "the error names the bad field" "$out"
rm -rf "$scratch"

# Case 18: --check discovers a docs/charter/*.md section and the two
# AGENTS.md card twins on disk with no ledger row.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/charter" "$scratch/docs/evals" "$scratch/workspace-card"
printf '# x\n' >"$scratch/docs/charter/01-example.md"
printf 'x\n' >"$scratch/AGENTS.md"
printf 'x\n' >"$scratch/workspace-card/AGENTS.md"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "--check exits 1 on charter/AGENTS.md coverage gaps" "$out"
expect_contains "$out" "docs/charter/01-example.md" "the charter section is named" "$out"
expect_contains "$out" "card on disk: workspace-card/AGENTS.md" "the workspace-card AGENTS.md twin is named" "$out"
expect_contains "$out" "card on disk: AGENTS.md" "the ops-repo AGENTS.md twin is named, not just matched as a substring of the workspace-card line" "$out"
rm -rf "$scratch"

# Case 19: a pipe character in a plan, reason, or sources value is escaped
# in the rendered table, instead of opening an extra column.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/pipey.sh", "kind": "hook", "loads": "every use", "status": "safety", "reason": "a|b"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "a pipe in a cell value still exits 0" "$out"
expect_contains "$out" 'a\|b' "the pipe is escaped in the rendered cell" "$out"
rm -rf "$scratch"

# Case 20: a newline inside a plan, reason, or sources value is flattened
# to a space before pipes are escaped, so an embedded newline cannot split
# the rendered table row across physical lines.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
python3 -c "
import json
json.dump({'measured_at': '2026-01-01', 'parts': [
    {'key': 'scripts/hooks/newliney.sh', 'kind': 'hook', 'loads': 'every use', 'status': 'safety', 'reason': 'a\nb'}
]}, open('$scratch/$TEMPLATE_LEDGER', 'w'))
"
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "a newline in a cell value still exits 0" "$out"
row_count=$(printf '%s\n' "$out" | grep -c "newliney.sh")
expect 1 "$row_count" "the row with an embedded newline stays on one physical line" "$out"
expect_contains "$out" "a b" "the newline is flattened to a space" "$out"
rm -rf "$scratch"

# Case 21: an install-owned hook with a local ledger row passes --check, and
# normal output names the ledger that supplied the row.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts/hooks" "$scratch/docs/evals"
printf '#!/bin/sh\n' >"$scratch/scripts/hooks/instance-hook.sh"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
cat >"$scratch/$INSTANCE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/instance-hook.sh", "kind": "hook", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 0 "$rc" "an install-owned hook with a local row passes --check" "$out"
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "a local-ledger table run exits 0" "$out"
expect_contains "$out" "$INSTANCE_LEDGER" "table output names the local ledger" "$out"
json_out=$("$SCRIPT" --root "$scratch" --json 2>&1); rc=$?
expect 0 "$rc" "a local-ledger JSON run exits 0" "$json_out"
expect_contains "$json_out" "\"ledger\": \"$INSTANCE_LEDGER\"" "JSON output names the local ledger" "$json_out"
rm -rf "$scratch"

# Case 22: an install-owned hook with no local row remains a --check failure.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts/hooks" "$scratch/docs/evals"
printf '#!/bin/sh\n' >"$scratch/scripts/hooks/instance-hook.sh"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 1 "$rc" "an install-owned hook with no row fails --check" "$out"
expect_contains "$out" "no ledger row for registered hook on disk" "the missing local row is reported" "$out"
rm -rf "$scratch"

# Case 23: a path declared in both ledgers fails with both ledger names.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/duplicate.sh", "kind": "hook", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
cat >"$scratch/$INSTANCE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": [
  {"key": "scripts/hooks/duplicate.sh", "kind": "hook", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 2 "$rc" "a duplicate path across ledgers fails" "$out"
expect_contains "$out" "scripts/hooks/duplicate.sh" "the duplicate path is named" "$out"
expect_contains "$out" "$TEMPLATE_LEDGER" "the duplicate error names the template ledger" "$out"
expect_contains "$out" "$INSTANCE_LEDGER" "the duplicate error names the local ledger" "$out"
rm -rf "$scratch"

# Case 24: malformed local JSON fails and names the local ledger.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
printf '{not-json\n' >"$scratch/$INSTANCE_LEDGER"
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 2 "$rc" "malformed local JSON fails" "$out"
expect_contains "$out" "$INSTANCE_LEDGER" "the malformed local ledger is named" "$out"
rm -rf "$scratch"

# Case 25: an absent local ledger is an empty overlay and still passes.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
expect 0 "$rc" "an absent local ledger passes --check" "$out"
rm -rf "$scratch"

# Case 26: non-finite measured_tokens values fail while either ledger loads.
for nonfinite in Infinity NaN; do
  scratch="$(mktemp -d)"
  mkdir -p "$scratch/docs/evals"
  cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
  cat >"$scratch/$INSTANCE_LEDGER" <<JSON
{"measured_at": "2026-01-01", "parts": [
  {"key": "hook-stdout-nonfinite", "kind": "hook", "loads": "every session", "status": "untested", "plan": "none (grandfathered)", "measured_tokens": $nonfinite}
]}
JSON
  out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
  expect 2 "$rc" "$nonfinite measured_tokens fails while loading" "$out"
  expect_contains "$out" "non-finite measured_tokens" "$nonfinite is named as non-finite" "$out"
  rm -rf "$scratch"
done

# Case 27: disk-sized keys cannot escape the install root, while an exec row
# retains declared-name semantics even when its key is absolute.
scratch="$(mktemp -d)"
mkdir -p "$scratch/docs/evals"
cat >"$scratch/$TEMPLATE_LEDGER" <<'JSON'
{"measured_at": "2026-01-01", "parts": []}
JSON
for bad_key in "../outside.md" "$scratch/outside.md"; do
  cat >"$scratch/$INSTANCE_LEDGER" <<JSON
{"measured_at": "2026-01-01", "parts": [
  {"key": "$bad_key", "kind": "skill", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
  out=$("$SCRIPT" --root "$scratch" --check 2>&1); rc=$?
  expect 2 "$rc" "disk-sized key outside root fails" "$out"
  expect_contains "$out" "path outside root" "the disk-sized path boundary is named" "$out"
done
cat >"$scratch/$INSTANCE_LEDGER" <<JSON
{"measured_at": "2026-01-01", "parts": [
  {"key": "$scratch/declared-hook-name", "kind": "hook", "loads": "every use", "status": "untested", "plan": "none (grandfathered)"}
]}
JSON
out=$("$SCRIPT" --root "$scratch" 2>&1); rc=$?
expect 0 "$rc" "an absolute exec key retains declared-name semantics" "$out"
rm -rf "$scratch"

[ "$F" -eq 0 ] && exit 0 || exit 1
