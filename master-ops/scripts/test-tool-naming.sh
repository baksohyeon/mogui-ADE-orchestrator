#!/bin/bash
# Lint for the "name the tool, do not describe it" rule, applied to the ctx MCP
# tools.
#
# Why this exists: commit 916fdff fixed three runbook sites that described
# master-succeed instead of naming it, and three successions were hand-typed as
# a result. On 2026-08-05 the same defect was found in skills/blame-agent, which
# wrote the ctx tools as `ctx.search` and `ctx.sql`. Those strings are not
# callable. A reader who copies them gets InputValidationError, and a reader who
# does not notice concludes the tool is unavailable.
#
# The callable names are `mcp__ctx__<verb>`. Anything of the form `ctx.<verb>`
# is a description wearing a tool's clothes.
#
# Exit: 0 clean, 1 findings exist, 2 usage or self-test failure.
set -u

cd "$(dirname "$0")/.."

VERBS='search|sql|show_event|show_session|status|sources'
# `ctx.` immediately followed by a tool verb. `~/.ctx/config.toml` does not
# match, because `ctx/` is not `ctx.`, and neither does prose like "the ctx
# index".
BAD_FORM="ctx\.($VERBS)\b"

# Search the surfaces a master or worker actually reads. The scan skips this
# file, which necessarily contains the pattern it hunts for.
SCAN_DIRS="docs skills"

self_test() {
  # A lint nobody has watched fail is not a lint. Feed it a case it must
  # object to, per MASTER-OPERATIONS section 7.
  local tmp rc
  tmp=$(mktemp -d) || return 2
  printf 'Measure coverage with ctx.sql before citing.\n' >"$tmp/bad.md"
  printf 'Measure coverage with mcp__ctx__sql before citing.\n' >"$tmp/good.md"

  if ! grep -rEl "$BAD_FORM" "$tmp/bad.md" >/dev/null 2>&1; then
    echo "self-test FAILED: the pattern did not catch a known-bad line" >&2
    rm -rf "$tmp"; return 2
  fi
  if grep -rEl "$BAD_FORM" "$tmp/good.md" >/dev/null 2>&1; then
    echo "self-test FAILED: the pattern flagged a correct callable name" >&2
    rm -rf "$tmp"; return 2
  fi
  rm -rf "$tmp"
  echo "self-test: pattern rejects ctx.sql and accepts mcp__ctx__sql"
  return 0
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

if [ $# -gt 0 ]; then
  echo "usage: $0 [--self-test]" >&2
  exit 2
fi

self_test || exit 2

findings=$(grep -rnE "$BAD_FORM" $SCAN_DIRS 2>/dev/null \
  | grep -v '^scripts/test-tool-naming\.sh:' || true)

if [ -n "$findings" ]; then
  echo "Tool naming: FINDINGS — non-callable ctx tool forms below."
  echo "Replace each with its mcp__ctx__<verb> name. See docs/runbooks/ctx-query-doctrine.md."
  printf '%s\n' "$findings"
  exit 1
fi

echo "Tool naming: no non-callable ctx tool forms in $SCAN_DIRS"
exit 0
