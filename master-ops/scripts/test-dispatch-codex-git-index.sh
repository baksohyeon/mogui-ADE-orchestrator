#!/bin/bash
# Static test: verify dispatch wrapper has the codex git index unlock fix
# Card: mgm-up2w

set -eu

DISPATCH="${DISPATCH:-$(dirname "$0")/dispatch}"

if [ ! -f "$DISPATCH" ]; then
  echo "✗ dispatch file not found: $DISPATCH"
  exit 1
fi

# Test 1: Guard must be [ -e ], not [ -d ]
if grep -q '\[ -e "$wt_path/.git" \]' "$DISPATCH"; then
  echo "✓ Test 1: dispatch contains [ -e .git ] guard (correct for linked worktrees)"
else
  echo "✗ Test 1 FAILED: dispatch missing [ -e .git ] guard"
  exit 1
fi

# Test 2: Must NOT have the broken [ -d ] guard
if grep -q '\[ -d "$wt_path/.git" \]' "$DISPATCH"; then
  echo "✗ Test 2 FAILED: dispatch still contains broken [ -d .git ] guard"
  exit 1
else
  echo "✓ Test 2: dispatch does not contain [ -d .git ] (good)"
fi

# Test 3: Must call git status inside the guard
if grep -A 2 '\[ -e "$wt_path/.git" \]' "$DISPATCH" | grep -q 'git -C "$wt_path" status --porcelain'; then
  echo "✓ Test 3: dispatch calls git status inside the guard"
else
  echo "✗ Test 3 FAILED: dispatch missing git status call in guard block"
  exit 1
fi

echo "✓ All static checks passed"
exit 0
