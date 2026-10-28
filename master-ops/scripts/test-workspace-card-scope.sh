#!/usr/bin/env bash
# Regression test for issue #207: the workspace card pair must open with the
# scope sentence (who the card addresses), not a bare "You are the ops
# master" claim that a dispatched worker or another workspace's session
# would read as its own role.
set -u

cd "$(dirname "$0")/.."

CLAUDE_CARD="workspace-card/CLAUDE.md"
AGENTS_CARD="workspace-card/AGENTS.md"

SCOPE_SENTENCE="This card applies to the owner-appointed master of this workspace and to the workers that master dispatches."

pass=0
fail=0

first_paragraph_line() {
  # The first non-blank line after the H1 title.
  awk 'NR==1 {next} NF==0 {next} {print; exit}' "$1"
}

for card in "$CLAUDE_CARD" "$AGENTS_CARD"; do
  if grep -qF "$SCOPE_SENTENCE" "$card"; then
    echo "ok   - $card contains the scope sentence verbatim"
    pass=$((pass + 1))
  else
    echo "FAIL - $card is missing the scope sentence verbatim"
    fail=$((fail + 1))
  fi

  opener="$(first_paragraph_line "$card")"
  case "$opener" in
    "You are the ops master"*)
      echo "FAIL - $card still opens with the bare master claim: $opener"
      fail=$((fail + 1))
      ;;
    *)
      echo "ok   - $card does not open with the bare master claim"
      pass=$((pass + 1))
      ;;
  esac
done

if diff -q "$CLAUDE_CARD" "$AGENTS_CARD" >/dev/null; then
  echo "ok   - $CLAUDE_CARD and $AGENTS_CARD are identical"
  pass=$((pass + 1))
else
  echo "FAIL - $CLAUDE_CARD and $AGENTS_CARD differ"
  fail=$((fail + 1))
fi

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
