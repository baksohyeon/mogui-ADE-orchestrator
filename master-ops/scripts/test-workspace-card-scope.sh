#!/usr/bin/env bash
# Regression test for issue #207: the workspace card pair's first sentence
# after the title must be the scope sentence (who the card addresses). The
# old opener, "You are the ops master of this workspace.", let a dispatched
# worker or another workspace's session read it as its own role.
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
    "$SCOPE_SENTENCE"*)
      echo "ok   - $card opens with the scope sentence"
      pass=$((pass + 1))
      ;;
    *)
      echo "FAIL - $card does not open with the scope sentence: $opener"
      fail=$((fail + 1))
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
