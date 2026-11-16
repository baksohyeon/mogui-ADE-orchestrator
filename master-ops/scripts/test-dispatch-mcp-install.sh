#!/bin/bash
# Regression check for the master-side .mcp.json merge (#317 stage 2,
# "Required-infra MCP wiring" subsection of onboarding/08-settings-and-skills.md).
# That doc is the one place this command is written; this test extracts the
# exact python3 snippet between the <!-- crg-mcp-merge:start/end --> markers
# and runs it against fixtures, rather than re-implementing the merge here
# and risking the two drifting apart.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
doc=${1:-$here/../onboarding/08-settings-and-skills.md}
pinned=${2:-$here/../templates/mcp-servers.json}

mcp_merge_test() (
  set +e
  set -u
  local doc="$1" pinned="$2" work snippet out status

  # Extract only the python source between the "python3 -c '" opener and the
  # closing "' <args>" line — not that invocation's own (templated) argv —
  # so the test can supply its own fixture paths as argv instead.
  snippet=$(awk -v open_fence="$(printf '$ python3 -c %s' "'")" -v close_fence="$(printf '%s "{{WORKSPACE_ROOT}}' "'")" '
    index($0, "<!-- crg-mcp-merge:start -->"){f=1; next}
    index($0, "<!-- crg-mcp-merge:end -->"){exit}
    f && !p && $0 == open_fence {p=1; next}
    f && p && index($0, close_fence) == 1 {p=0; next}
    f && p {print}
  ' "$doc")

  [ -n "$snippet" ] || { echo "FAIL: could not extract the crg-mcp-merge python source from $doc" >&2; return 1; }
  printf '%s\n' "$snippet" | grep -qF 'json.dump' || {
    echo "FAIL: extracted snippet does not look like the merge command" >&2
    printf '%s\n' "$snippet" >&2
    return 1
  }

  work="${TMPDIR:-/tmp}/mogui-dispatch-mcp-install-test.$$"
  mkdir -p "$work"
  trap 'rm -rf "$work"' EXIT
  printf '%s\n' "$snippet" > "$work/merge.py"

  run_merge() {
    local dest="$1"
    python3 "$work/merge.py" "$dest" "$pinned"
  }

  # Case: no existing .mcp.json — the merge creates one with the pinned entry.
  dest="$work/fresh.mcp.json"
  run_merge "$dest" >/dev/null 2>&1
  status=$?
  if [ "$status" -ne 0 ] || [ ! -f "$dest" ]; then
    echo "FAIL: merge into a missing file should create it" >&2
    return 1
  fi
  if ! python3 -c "
import json, sys
dest_doc = json.load(open(sys.argv[1]))
pinned_doc = json.load(open(sys.argv[2]))
sys.exit(0 if dest_doc['mcpServers']['code-review-graph'] == pinned_doc['mcpServers']['code-review-graph'] else 1)
" "$dest" "$pinned"; then
    echo "FAIL: fresh merge did not write the pinned code-review-graph entry" >&2
    cat "$dest" >&2
    return 1
  fi
  echo "ok   : no existing .mcp.json creates one with the pinned code-review-graph entry"

  # Case: an existing file with another server keeps that server.
  dest="$work/other-server.mcp.json"
  cat > "$dest" <<'JSON'
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
  run_merge "$dest" >/dev/null 2>&1
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: merge into a file with another server should succeed" >&2
    return 1
  fi
  if ! python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
servers = d['mcpServers']
sys.exit(0 if 'some-other-tool' in servers and 'code-review-graph' in servers else 1)
" "$dest"; then
    echo "FAIL: merge should keep the pre-existing server entry alongside the pinned one" >&2
    cat "$dest" >&2
    return 1
  fi
  echo "ok   : an existing .mcp.json with another server keeps that entry and adds code-review-graph"

  # Case: a stale code-review-graph entry gets replaced with the pinned one.
  dest="$work/stale.mcp.json"
  cat > "$dest" <<'JSON'
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
  run_merge "$dest" >/dev/null 2>&1
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL: merge over a stale entry should succeed" >&2
    return 1
  fi
  if ! python3 -c "
import json, sys
dest_doc = json.load(open(sys.argv[1]))
pinned_doc = json.load(open(sys.argv[2]))
got = dest_doc['mcpServers']['code-review-graph']
want = pinned_doc['mcpServers']['code-review-graph']
sys.exit(0 if got == want else 1)
" "$dest" "$pinned"; then
    echo "FAIL: a stale code-review-graph entry should be replaced with the pinned one, not merged field-by-field" >&2
    cat "$dest" >&2
    return 1
  fi
  echo "ok   : a stale code-review-graph entry is replaced with the pinned version, not merged field-by-field"

  # Case: malformed existing JSON is refused, not clobbered.
  dest="$work/malformed.mcp.json"
  printf '{ "mcpServers": ' > "$dest"
  before=$(cat "$dest")
  out=$(run_merge "$dest" 2>&1)
  status=$?
  after=$(cat "$dest")
  if [ "$status" -eq 0 ]; then
    echo "FAIL: merge over malformed JSON should refuse (non-zero exit), not silently succeed" >&2
    return 1
  fi
  if [ "$before" != "$after" ]; then
    echo "FAIL: merge over malformed JSON clobbered the original file instead of leaving it untouched" >&2
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF 'refusing to merge'; then
    echo "FAIL: malformed-JSON refusal should name the reason ('refusing to merge'), got: $out" >&2
    return 1
  fi
  echo "ok   : malformed existing JSON is refused with a named reason and left unclobbered"
)
mcp_merge_test "$doc" "$pinned" || exit 1

echo "dispatch mcp-install regression test passed"
