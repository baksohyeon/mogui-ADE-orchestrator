#!/bin/bash
# Static test: verify dispatch wrapper has the codex git index unlock fix
# Card: mgm-up2w

set -eu

DISPATCH="${DISPATCH:-$(dirname "$0")/dispatch}"

check_dispatch() {
  local dispatch="$1" guard_block status_line terminal_line

  [ -f "$dispatch" ] || return 1

  # Test 1: the linked-worktree guard must use this exact .git path.
  grep -Fq '[ -e "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 2: the directory-only guard is wrong for linked worktrees.
  ! grep -Fq '[ -d "$wt_path/.git" ]' "$dispatch" || return 1

  # Test 3: locate an uncommented status command inside the exact guard block.
  guard_block=$(awk '
    index($0, "[ -e \"$wt_path/.git\" ]") { inside=1 }
    inside { print }
    inside && /^[[:space:]]*fi[[:space:]]*$/ { exit }
  ' "$dispatch")
  printf '%s\n' "$guard_block" | grep -Eq '^[[:space:]]*if git -C "\$wt_path" status --porcelain([[:space:]]|$)' || return 1

  # Test 4: the preflight must run before the Codex terminal is created.
  status_line=$(grep -nE '^[[:space:]]*if git -C "\$wt_path" status --porcelain' "$dispatch" | cut -d: -f1 | head -1)
  terminal_line=$(grep -nF 'orca terminal create --worktree' "$dispatch" | cut -d: -f1 | head -1)
  [ "$status_line" -lt "$terminal_line" ] || return 1
}

if [ "${MUTANT_EXPECTED:-0}" = 1 ]; then
  check_dispatch "$DISPATCH"
  exit $?
fi

check_dispatch "$DISPATCH" || {
  echo "✗ dispatch git index preflight checks failed: $DISPATCH" >&2
  exit 1
}
echo "✓ dispatch uses the exact linked-worktree guard, an uncommented status command, and pre-launch ordering"

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-git-index.$$"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT
mutant="$work/dispatch-mutant"
sed '/^[[:space:]]*if git -C "\$wt_path" status --porcelain/d' "$DISPATCH" > "$mutant"

if MUTANT_EXPECTED=1 DISPATCH="$mutant" "$0"; then
  echo "✗ mutant run unexpectedly passed: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")" >&2
  exit 1
else
  echo "✓ mutant run failed as expected: MUTANT_EXPECTED=1 DISPATCH=$(printf '%q' "$mutant") $(printf '%q' "$0")"
fi

echo "✓ All static checks passed"
