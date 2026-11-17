#!/bin/bash
# Regression check for scripts/install-mcp-config (#317 stage 2, "Required-infra
# MCP wiring" subsection of onboarding/08-settings-and-skills.md; extracted from
# an inline python3 snippet that doc used to carry, #328 follow-up). Runs the
# real script against fixtures instead of re-implementing or re-extracting the
# merge here.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
script=${1:-$here/install-mcp-config}
pinned=${2:-$here/../templates/mcp-servers.json}

[ -x "$script" ] || { echo "FAIL: $script is missing or not executable" >&2; exit 1; }

work="${TMPDIR:-/tmp}/mogui-install-mcp-config-test.$$"
mkdir -p "$work"
trap 'rm -rf "${work:?}"' EXIT

install_into() {  # workspace-root
  "$script" "$1" "$pinned"
}

# Case: no existing .mcp.json — the merge creates one with the pinned entry,
# and that entry is actually pinned (a package spec with no "@version" is
# a regression this test must catch, not just whatever the template holds).
ws="$work/fresh"
mkdir -p "$ws"
out=$(install_into "$ws" 2>&1)
status=$?
if [ "$status" -ne 0 ] || [ ! -f "$ws/.mcp.json" ]; then
  echo "FAIL: merge into a workspace with no .mcp.json should create it" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! python3 -c "
import json, sys
dest_doc = json.load(open(sys.argv[1]))
pinned_doc = json.load(open(sys.argv[2]))
want = pinned_doc['mcpServers']['code-review-graph']
sys.exit(0 if dest_doc['mcpServers']['code-review-graph'] == want and '@' in want['args'][0] else 1)
" "$ws/.mcp.json" "$pinned"; then
  echo "FAIL: fresh merge did not write a pinned (name@version) code-review-graph entry" >&2
  cat "$ws/.mcp.json" >&2
  exit 1
fi
echo "ok   : no existing .mcp.json creates one with the pinned code-review-graph entry"

# Case: a second run on an already-merged workspace changes nothing
# (acceptance check: idempotent, byte-identical).
before=$(cat "$ws/.mcp.json")
out=$(install_into "$ws" 2>&1)
status=$?
after=$(cat "$ws/.mcp.json")
if [ "$status" -ne 0 ] || [ "$before" != "$after" ]; then
  echo "FAIL: a second run over an already-merged .mcp.json should be a byte-identical no-op" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : a second run over an already-merged .mcp.json is a byte-identical no-op"

# Case: an existing file with another server keeps that server.
ws="$work/other-server"
mkdir -p "$ws"
cat > "$ws/.mcp.json" <<'JSON'
{
  "mcpServers": {
    "some-other-tool": {
      "type": "stdio",
      "command": "some-other-tool",
      "args": ["serve"]
    }
  }
}
JSON
out=$(install_into "$ws" 2>&1)
status=$?
if [ "$status" -ne 0 ]; then
  echo "FAIL: merge into a file with another server should succeed" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
servers = d['mcpServers']
sys.exit(0 if 'some-other-tool' in servers and 'code-review-graph' in servers else 1)
" "$ws/.mcp.json"; then
  echo "FAIL: merge should keep the pre-existing server entry alongside the pinned one" >&2
  cat "$ws/.mcp.json" >&2
  exit 1
fi
echo "ok   : an existing .mcp.json with another server keeps that entry and adds code-review-graph"

# Case: the other server survives a second run too, and nothing changes.
before=$(cat "$ws/.mcp.json")
install_into "$ws" >/dev/null
after=$(cat "$ws/.mcp.json")
if [ "$before" != "$after" ]; then
  echo "FAIL: a second run should not touch a workspace whose other server is already merged" >&2
  exit 1
fi
echo "ok   : the other server survives a second run and the file does not change"

# Case: a stale code-review-graph entry gets replaced with the pinned one.
ws="$work/stale"
mkdir -p "$ws"
cat > "$ws/.mcp.json" <<'JSON'
{
  "mcpServers": {
    "code-review-graph": {
      "type": "stdio",
      "command": "uvx",
      "args": ["code-review-graph@0.0.1", "serve", "--repo", "/some/old/path"]
    }
  }
}
JSON
out=$(install_into "$ws" 2>&1)
status=$?
if [ "$status" -ne 0 ]; then
  echo "FAIL: merge over a stale entry should succeed" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! python3 -c "
import json, sys
dest_doc = json.load(open(sys.argv[1]))
pinned_doc = json.load(open(sys.argv[2]))
got = dest_doc['mcpServers']['code-review-graph']
want = pinned_doc['mcpServers']['code-review-graph']
sys.exit(0 if got == want else 1)
" "$ws/.mcp.json" "$pinned"; then
  echo "FAIL: a stale code-review-graph entry should be replaced with the pinned one, not merged field-by-field" >&2
  cat "$ws/.mcp.json" >&2
  exit 1
fi
echo "ok   : a stale code-review-graph entry is replaced with the pinned version, not merged field-by-field"

# Case: malformed existing JSON is refused, not clobbered.
ws="$work/malformed"
mkdir -p "$ws"
printf '{ "mcpServers": ' > "$ws/.mcp.json"
before=$(cat "$ws/.mcp.json")
out=$(install_into "$ws" 2>&1) && status=0 || status=$?
after=$(cat "$ws/.mcp.json")
if [ "$status" -eq 0 ]; then
  echo "FAIL: merge over malformed JSON should refuse (non-zero exit), not silently succeed" >&2
  exit 1
fi
if [ "$before" != "$after" ]; then
  echo "FAIL: merge over malformed JSON clobbered the original file instead of leaving it untouched" >&2
  exit 1
fi
if ! printf '%s\n' "$out" | grep -qF 'refusing to merge'; then
  echo "FAIL: malformed-JSON refusal should name the reason ('refusing to merge'), got: $out" >&2
  exit 1
fi
echo "ok   : malformed existing JSON is refused with a named reason and left unclobbered"

# Case: a non-object top level (a JSON array, say) is refused, not clobbered.
ws="$work/non-object-top"
mkdir -p "$ws"
printf '[1, 2, 3]' > "$ws/.mcp.json"
before=$(cat "$ws/.mcp.json")
out=$(install_into "$ws" 2>&1) && status=0 || status=$?
after=$(cat "$ws/.mcp.json")
if [ "$status" -eq 0 ] || [ "$before" != "$after" ]; then
  echo "FAIL: a non-object top-level .mcp.json should be refused and left untouched" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! printf '%s\n' "$out" | grep -qF 'refusing to merge'; then
  echo "FAIL: non-object-top-level refusal should name the reason ('refusing to merge'), got: $out" >&2
  exit 1
fi
echo "ok   : a non-object top-level .mcp.json is refused with a named reason and left unclobbered"

# Case: a non-object "mcpServers" key is refused, not clobbered.
ws="$work/non-object-servers"
mkdir -p "$ws"
printf '{"mcpServers": ["not-a-mapping"]}' > "$ws/.mcp.json"
before=$(cat "$ws/.mcp.json")
out=$(install_into "$ws" 2>&1) && status=0 || status=$?
after=$(cat "$ws/.mcp.json")
if [ "$status" -eq 0 ] || [ "$before" != "$after" ]; then
  echo "FAIL: a non-object mcpServers should be refused and left untouched" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
if ! printf '%s\n' "$out" | grep -qF 'refusing to merge'; then
  echo "FAIL: non-object-mcpServers refusal should name the reason ('refusing to merge'), got: $out" >&2
  exit 1
fi
echo "ok   : a non-object mcpServers is refused with a named reason and left unclobbered"

# Case: --print-entry reads the real pinned command and pin without
# re-parsing the JSON in the caller (used by other tests, below).
entry=$("$script" --print-entry code-review-graph "$pinned")
cmd=$(printf '%s\n' "$entry" | sed -n 1p)
spec=$(printf '%s\n' "$entry" | sed -n 2p)
if [ -z "$cmd" ] || ! printf '%s' "$spec" | grep -qF '@'; then
  echo "FAIL: --print-entry should print a command then a pinned (name@version) spec, got: $entry" >&2
  exit 1
fi
echo "ok   : --print-entry prints the pinned code-review-graph command and spec"

echo "install-mcp-config regression test passed"
