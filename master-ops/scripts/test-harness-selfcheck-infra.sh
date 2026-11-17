#!/bin/bash
# Regression test for the ctx/code-review-graph `Infra:` checks in
# harness-selfcheck.sh (#317 stage 1: warn when required infra is missing,
# unreachable, or stale; never touch the script's exit code).
#
# Exercises the Infra block directly, the way test-seat-check.sh and
# test-template-currency-line.sh exercise their own probes: a bare template
# checkout has no real WORKSPACE_ROOT, so running the whole self-check would
# abort at an earlier check (Skills, Hooks, Tracker) before ever reaching
# this one. The block is extracted with the exact same sed range the
# harness-selfcheck.md doc edit names, and run under `set -e` (the real
# script's own top line, not included in the extracted range) so an
# unguarded errexit-abort here fails loudly instead of passing by accident.
set -u

cd "$(dirname "$0")/.."

SELFCHECK_DEFAULT="./scripts/harness-selfcheck.sh"
SELFCHECK_BIN="${SELFCHECK_BIN:-$SELFCHECK_DEFAULT}"

# harness-selfcheck.sh is instance-owned (template_common.INSTANCE_OWNED_EXACT):
# a rendered template-only copy never has one, so there is nothing to measure
# at the default path. An explicit override that is still missing is a typo
# or a stale binary, not that case, and fails loudly instead of skipping.
if [ ! -f "$SELFCHECK_BIN" ]; then
  if [ "$SELFCHECK_BIN" != "$SELFCHECK_DEFAULT" ]; then
    echo "FAIL: SELFCHECK_BIN=$SELFCHECK_BIN not found" >&2
    exit 1
  fi
  echo "SKIP: $SELFCHECK_BIN not found (instance-owned, not part of a template-only checkout)"
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "${TMP:?}"' EXIT

pass=0
fail=0

INFRA_BLOCK="$TMP/infra-block.sh"
{
  echo 'set -e'
  sed -n '/^# --- Infra: required-tool checks/,/^# --- Template currency check ---$/p' "$SELFCHECK_BIN" | sed '$d'
} > "$INFRA_BLOCK"

if [ ! -s "$INFRA_BLOCK" ] || ! grep -q '^ctx_warn=""$' "$INFRA_BLOCK"; then
  echo "FAIL: no Infra: block found in $SELFCHECK_BIN (pre-#317 state, e.g. origin/main)"
  echo "----"
  echo "passed: 0  failed: 1"
  exit 1
fi

BIN_DIR="$TMP/bin"
mkdir -p "$BIN_DIR"

# Strip any real shim directory (mise, asdf, ...) out of the inherited PATH:
# a case that removes the code-review-graph stub to test "absent from PATH"
# must not fall through to a real shim for the same name on this host, which
# can print a different error, or even trigger a real tool install.
SAFE_PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '/shims\(/\|$\)' | tr '\n' ':')
SAFE_PATH="${SAFE_PATH%:}"

WORKSPACE_ROOT="$TMP/workspace"
OPS_DIR="$TMP/ops"
mkdir -p "$WORKSPACE_ROOT" "$OPS_DIR"

CLAUDE_MCP_CONFIG="$TMP/claude.json"
CLAUDE_USER_SETTINGS="$TMP/user-settings.json"
CODEX_MCP_CONFIG="$TMP/codex-config.toml"
CRG_REGISTRY="$TMP/registry.json"
CRG_MCP_CONFIG="$TMP/mcp-servers.json"
REPO_A="$TMP/repo-a"
CTX_SOURCES_FILE="$TMP/ctx-sources.txt"

# $1 = orca stub's claude-session count, $2 = its codex-session count.
write_stub_orca() {
  local claude_n="$1" codex_n="$2"
  cat > "$BIN_DIR/orca" <<EOF
#!/bin/bash
printf '%s\n' '{"ok": true, "result": {"sessionsByAgent": {"claude": $claude_n, "codex": $codex_n}}}'
EOF
  chmod +x "$BIN_DIR/orca"
}

# $1 = space-separated list of providers ctx reports as indexed. $2 =
# optional `ctx upgrade status --format json` body (#328 follow-up;
# default: up to date at 2.4.1), for the ctx-upgrade cases below.
write_stub_ctx() {
  local providers_json upgrade_json
  providers_json=$(python3 -c "import json, sys; print(json.dumps(sys.argv[1].split()))" "$1")
  upgrade_json=${2:-'{"current_version": "2.4.1", "state": {"status": "up_to_date", "latest_version": "2.4.1"}}'}
  cat > "$BIN_DIR/ctx" <<EOF
#!/bin/bash
if [ "\$1" = "status" ]; then
  printf '%s\n' '{"daemon": {"jobs": {"core_refresh": {"progress": {"providers": $providers_json}}}}}'
  exit 0
fi
if [ "\$1" = "sources" ]; then
  cat "$CTX_SOURCES_FILE"
  exit 0
fi
if [ "\$1" = "upgrade" ] && [ "\$2" = "status" ]; then
  printf '%s\n' '$upgrade_json'
  exit 0
fi
exit 1
EOF
  chmod +x "$BIN_DIR/ctx"
}

# $1 = launcher command name, $2 = pinned package spec (args[0]). Round 2
# (#317): harness-selfcheck.sh now reads both from this file instead of
# hardcoding "code-review-graph" as the probe target, so the fixture must
# supply them the same way templates/mcp-servers.json does.
write_mcp_servers_config() {
  printf '{"mcpServers": {"code-review-graph": {"command": "%s", "args": ["%s", "serve"]}}}\n' "$1" "$2" > "$CRG_MCP_CONFIG"
}

# $1 = "ok" (runs cleanly) or "shim-fail" (mimics the real mise-shim error).
write_stub_crg() {
  if [ "$1" = "ok" ]; then
    cat > "$BIN_DIR/code-review-graph" <<'EOF'
#!/bin/bash
echo "code-review-graph 2.4.0"
EOF
  else
    cat > "$BIN_DIR/code-review-graph" <<'EOF'
#!/bin/bash
echo "mise ERROR No version is set for shim: code-review-graph"
exit 1
EOF
  fi
  chmod +x "$BIN_DIR/code-review-graph"
}

reset_fixture() {
  rm -f "$BIN_DIR/orca" "$BIN_DIR/ctx" "$BIN_DIR/code-review-graph"
  write_stub_orca 10 5
  write_stub_ctx "claude codex"
  write_stub_crg ok
  write_mcp_servers_config code-review-graph code-review-graph@2.4.0
  printf 'all sources available\n' > "$CTX_SOURCES_FILE"
  printf '{"mcpServers": {"ctx": {}, "code-review-graph": {}}}\n' > "$CLAUDE_MCP_CONFIG"
  printf '{}\n' > "$CLAUDE_USER_SETTINGS"
  printf '' > "$CODEX_MCP_CONFIG"
  rm -rf "${WORKSPACE_ROOT:?}/.claude" "${WORKSPACE_ROOT:?}/.mcp.json"
  mkdir -p "$WORKSPACE_ROOT/.claude"
  rm -rf "${REPO_A:?}"
  mkdir -p "$REPO_A/.code-review-graph"
  touch "$REPO_A/.code-review-graph/graph.db"
  printf '{"repos": [{"path": "%s", "alias": "repo-a"}]}\n' "$REPO_A" > "$CRG_REGISTRY"
}

# #328 follow-up: the Infra block now judges MCP registration against this
# seat's own host (MASTER_HOST_RUNTIME), resolved from MOGUI_MASTER_HOST_RUNTIME
# or master_host_runtime in $OPS_DIR/config/instance-runtime.json. Every
# existing fixture here builds its "reachable" case through CLAUDE_MCP_CONFIG,
# so default to a Claude-hosted seat; individual cases below override one or
# both to exercise a Codex-hosted seat and an unmeasurable one.
run_infra() {
  PATH="$BIN_DIR:$SAFE_PATH" HOME="$TMP" \
    WORKSPACE_ROOT="$WORKSPACE_ROOT" OPS_DIR="$OPS_DIR" \
    CLAUDE_MCP_CONFIG="$CLAUDE_MCP_CONFIG" CLAUDE_USER_SETTINGS="$CLAUDE_USER_SETTINGS" \
    CODEX_MCP_CONFIG="$CODEX_MCP_CONFIG" \
    CODE_REVIEW_GRAPH_REGISTRY="$CRG_REGISTRY" \
    CODE_REVIEW_GRAPH_STALE_DAYS="${CODE_REVIEW_GRAPH_STALE_DAYS:-7}" \
    INFRA_TIMEOUT_SECONDS="${INFRA_TIMEOUT_SECONDS:-10}" \
    MCP_SERVERS_CONFIG="$CRG_MCP_CONFIG" \
    MOGUI_MASTER_HOST_RUNTIME="${MOGUI_MASTER_HOST_RUNTIME-claude}" \
    bash "$INFRA_BLOCK"
}

# $1 = case name, $2 = substring expected present, $3 = substring expected
# absent (pass "" to skip), $4 = expected rc of run_infra itself.
check() {
  local name="$1" want="$2" unwant="$3" want_rc="$4" out rc
  out=$(run_infra)
  rc=$?
  if ! printf '%s' "$out" | grep -qF "$want"; then
    echo "FAIL - $name (missing: $want)"
    printf '%s\n' "$out" | sed 's/^/       | /'
    fail=$((fail + 1))
    return
  fi
  if [ -n "$unwant" ] && printf '%s' "$out" | grep -qF "$unwant"; then
    echo "FAIL - $name (unexpected: $unwant)"
    printf '%s\n' "$out" | sed 's/^/       | /'
    fail=$((fail + 1))
    return
  fi
  if [ "$rc" -ne "$want_rc" ]; then
    echo "FAIL - $name (rc=$rc want=$want_rc)"
    fail=$((fail + 1))
    return
  fi
  echo "ok   - $name"
  pass=$((pass + 1))
}

exit_codes=()

# (a) All present, registered, covering, fresh: no WARN anywhere.
reset_fixture
check "(a) all good: ctx line present, no WARN" "Infra: ctx OK" "WARN" 0
check "(a) all good: code-review-graph line present, no WARN" "Infra: code-review-graph OK" "WARN" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")

# (b) ctx's indexed providers lack claude while Orca reports claude sessions.
reset_fixture
write_stub_ctx "codex"
printf '! Claude Code history location could not be selected safely\nthe selected history path uses a symlink component; use a trusted real path with --path\n\nHint: Resolve the issue and retry\n' > "$CTX_SOURCES_FILE"
check "(b) ctx missing claude coverage is named" "Infra: ctx WARN does not cover: claude" "" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")

# Round 2, Important #1: orca search --index-status --json parsing fine but
# carrying no result.sessionsByAgent must read as undecided, never as a
# vacuous OK -- round 1's sessions_by_agent() returned {} for this shape,
# which the coverage loop treats the same as "measured, nothing to report".
reset_fixture
cat > "$BIN_DIR/orca" <<'EOF'
#!/bin/bash
printf '%s\n' '{"ok": true}'
EOF
chmod +x "$BIN_DIR/orca"
check "orca status missing result.sessionsByAgent is undecided, never OK" \
  "Infra: ctx WARN undecided (orca search --index-status --json has no result.sessionsByAgent)" "Infra: ctx OK" 0

# Round 2, Important #1: ctx reporting zero indexed providers warns on its
# own, even when Orca has no claude/codex sessions to compare against --
# an index that covers nothing is never a clean pass.
reset_fixture
write_stub_ctx ""
check "ctx with zero indexed providers warns, never OK" \
  "Infra: ctx WARN ctx has indexed no providers" "Infra: ctx OK" 0

# #328 follow-up (from the #317 seat postmortem): ctx-upgrade warns on a
# reported State error, even when the main ctx check above is otherwise
# clean.
reset_fixture
write_stub_ctx "claude codex" '{"current_version": "1.3.2", "state": {"status": "error", "latest_version": "2.2.1"}}'
check "ctx-upgrade warns on a reported State error" \
  "Infra: ctx-upgrade WARN ctx upgrade status reports State error" "ctx-upgrade OK" 0

# ctx-upgrade warns when the installed version is numerically behind the
# latest version ctx last recorded, comparing as dotted integers (not
# strings, where "2.10.0" would sort before "2.9.0").
reset_fixture
write_stub_ctx "claude codex" '{"current_version": "2.9.0", "state": {"status": "up_to_date", "latest_version": "2.10.0"}}'
check "ctx-upgrade warns when behind the latest recorded version" \
  "Infra: ctx-upgrade WARN ctx 2.9.0 is behind 2.10.0" "ctx-upgrade OK" 0

# ctx-upgrade is OK when current and latest match.
reset_fixture
write_stub_ctx "claude codex" '{"current_version": "2.4.1", "state": {"status": "up_to_date", "latest_version": "2.4.1"}}'
check "ctx-upgrade OK when current matches the latest recorded version" "Infra: ctx-upgrade OK" "ctx-upgrade WARN" 0

# ctx-upgrade warns, naming the bound, on a timeout -- independent of the
# main ctx check's own timeout handling.
reset_fixture
cat > "$BIN_DIR/ctx" <<'EOF'
#!/bin/bash
if [ "$1" = "status" ]; then
  printf '%s\n' '{"daemon": {"jobs": {"core_refresh": {"progress": {"providers": ["claude", "codex"]}}}}}'
  exit 0
fi
if [ "$1" = "sources" ]; then
  exit 0
fi
if [ "$1" = "upgrade" ] && [ "$2" = "status" ]; then
  sleep 5
fi
exit 1
EOF
chmod +x "$BIN_DIR/ctx"
INFRA_TIMEOUT_SECONDS=1
check "ctx-upgrade warns naming the bound on a timeout" "Infra: ctx-upgrade WARN timed out after 1s" "ctx-upgrade OK" 0
unset INFRA_TIMEOUT_SECONDS

# ctx-upgrade warns, never crashes, on unparseable output.
reset_fixture
cat > "$BIN_DIR/ctx" <<'EOF'
#!/bin/bash
if [ "$1" = "status" ]; then
  printf '%s\n' '{"daemon": {"jobs": {"core_refresh": {"progress": {"providers": ["claude", "codex"]}}}}}'
  exit 0
fi
if [ "$1" = "sources" ]; then
  exit 0
fi
if [ "$1" = "upgrade" ] && [ "$2" = "status" ]; then
  printf 'not json\n'
  exit 0
fi
exit 1
EOF
chmod +x "$BIN_DIR/ctx"
check "ctx-upgrade warns naming the parse failure, never crashes" \
  "Infra: ctx-upgrade WARN could not parse ctx upgrade status" "ctx-upgrade OK" 0

# ctx-upgrade warns when ctx itself is absent from PATH, the same as the
# main ctx check. A real ctx install elsewhere on this host's own PATH
# (outside $BIN_DIR) would otherwise be found instead of "absent", the same
# gap (d) below guards against for code-review-graph.
reset_fixture
rm -f "$BIN_DIR/ctx"
ORIGINAL_SAFE_PATH="$SAFE_PATH"
real_ctx=$(PATH="$SAFE_PATH" command -v ctx 2>/dev/null) || true
if [ -n "$real_ctx" ]; then
  real_ctx_dir=$(dirname "$real_ctx")
  SAFE_PATH=$(printf '%s' "$SAFE_PATH" | tr ':' '\n' | grep -vF "$real_ctx_dir" | tr '\n' ':')
  SAFE_PATH="${SAFE_PATH%:}"
fi
check "ctx-upgrade warns when ctx is absent from PATH" "Infra: ctx-upgrade WARN absent from PATH" "ctx-upgrade OK" 0
SAFE_PATH="$ORIGINAL_SAFE_PATH"

# (c) A graph updated 30 days ago warns with the day count.
reset_fixture
old_ts=$(python3 -c "import time; print(int(time.time() - 30 * 86400))")
touch -t "$(python3 -c "import datetime; print(datetime.datetime.fromtimestamp($old_ts).strftime('%Y%m%d%H%M'))")" "$REPO_A/.code-review-graph/graph.db"
check "(c) a 30-day-old graph is named with its day count" "Infra: code-review-graph WARN stale: repo-a (30d)" "" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")

# A malformed registry entry (not an object) is named, not silently
# skipped: {"repos":[null]} must not iterate to zero findings and pass.
reset_fixture
printf '{"repos": [null]}\n' > "$CRG_REGISTRY"
check "a non-dict registry entry is named, not silently skipped" "Infra: code-review-graph WARN missing path: invalid registry entry" "" 0

# Round 2, Important #2: an empty registry (repos absent or an empty list)
# warns that nothing is registered, rather than iterating zero times and
# reading as a clean pass with nothing checked.
reset_fixture
printf '{"repos": []}\n' > "$CRG_REGISTRY"
check "an empty code-review-graph registry warns, never OK" \
  "Infra: code-review-graph WARN no repository registered" "Infra: code-review-graph OK" 0

# Round 2, Important #2: a non-finite or non-positive
# CODE_REVIEW_GRAPH_STALE_DAYS is rejected with a WARN naming the variable,
# and the default of 7 is used for the rest of the check regardless.
reset_fixture
for bad_value in nan inf 0 -1; do
  CODE_REVIEW_GRAPH_STALE_DAYS="$bad_value"
  check "invalid CODE_REVIEW_GRAPH_STALE_DAYS=$bad_value warns and names the variable" \
    "Infra: code-review-graph WARN CODE_REVIEW_GRAPH_STALE_DAYS='$bad_value' must be a positive, finite number; using default 7" "" 0
done
unset CODE_REVIEW_GRAPH_STALE_DAYS

# (d) A tool absent from PATH warns, never crashes. A real install
# elsewhere on this host's own PATH (outside $BIN_DIR) would otherwise find
# that instead of "absent"; SAFE_PATH only strips shim directories, so strip
# the real binary's own directory too, if one resolves.
reset_fixture
rm -f "$BIN_DIR/code-review-graph"
ORIGINAL_SAFE_PATH="$SAFE_PATH"
real_crg=$(PATH="$SAFE_PATH" command -v code-review-graph 2>/dev/null) || true
if [ -n "$real_crg" ]; then
  real_crg_dir=$(dirname "$real_crg")
  SAFE_PATH=$(printf '%s' "$SAFE_PATH" | tr ':' '\n' | grep -vF "$real_crg_dir" | tr '\n' ':')
  SAFE_PATH="${SAFE_PATH%:}"
fi
check "(d) absent from PATH warns without crashing" "Infra: code-review-graph WARN launcher 'code-review-graph' absent from PATH" "" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")
SAFE_PATH="$ORIGINAL_SAFE_PATH"

# (e) The exit code is the same across (a) through (d) above.
all_same=1
for code in "${exit_codes[@]}"; do
  [ "$code" = "${exit_codes[0]}" ] || all_same=0
done
if [ "$all_same" -eq 1 ]; then
  echo "ok   - (e) exit code is the same across (a)-(d): ${exit_codes[*]}"
  pass=$((pass + 1))
else
  echo "FAIL - (e) exit code differs across (a)-(d): ${exit_codes[*]}"
  fail=$((fail + 1))
fi

# infra_with_timeout falls back correctly when neither `timeout` nor
# `gtimeout` is on PATH: measured on GitHub Actions' macos-latest runner,
# which has neither, so every `Infra:` line reported "command not found"
# instead of running any check at all. `sleep` and `date` are the only two
# externals the fallback or this assertion needs; everything else it uses
# (kill, wait, command) is a bash builtin, resolved with no PATH lookup.
TIMEOUT_FN="$TMP/timeout-fn.sh"
sed -n '/^infra_with_timeout()/,/^}/p' "$SELFCHECK_BIN" > "$TIMEOUT_FN"
NO_TIMEOUT_BIN="$TMP/no-timeout-bin"
mkdir -p "$NO_TIMEOUT_BIN"
ln -sf "$(command -v sleep)" "$NO_TIMEOUT_BIN/sleep"
ln -sf "$(command -v date)" "$NO_TIMEOUT_BIN/date"
# `PATH=X bash ...` resolves `bash` itself through the overridden PATH, not
# the caller's, so the restricted PATH needs bash's own absolute path too.
BASH_BIN="$(command -v bash)"

fast_out=$(PATH="$NO_TIMEOUT_BIN" "$BASH_BIN" -c '
  source "$1"
  start=$(date +%s)
  infra_with_timeout 5 echo hello
  rc=$?
  end=$(date +%s)
  echo "rc=$rc elapsed=$((end - start))"
' _ "$TIMEOUT_FN" 2>/dev/null)
fast_rc=$(printf '%s' "$fast_out" | sed -n 's/.*rc=\([0-9-]*\) .*/\1/p')
fast_elapsed=$(printf '%s' "$fast_out" | sed -n 's/.*elapsed=\([0-9]*\).*/\1/p')
# Asserts the output AND that it returned promptly: a watchdog that keeps
# the caller's pipe open after the command finishes (the bug an orphaned,
# un-redirected `sleep` causes) would still eventually print the right
# text, just after blocking for the full 5s bound instead of returning fast.
if printf '%s' "$fast_out" | grep -qF "hello" && [ "$fast_rc" = "0" ] && [ -n "$fast_elapsed" ] && [ "$fast_elapsed" -le 2 ]; then
  echo "ok   - infra_with_timeout fallback runs a quick command without blocking for the bound ($fast_out)"
  pass=$((pass + 1))
else
  echo "FAIL - infra_with_timeout fallback runs a quick command without blocking for the bound (got: $fast_out)"
  fail=$((fail + 1))
fi

slow_out=$(PATH="$NO_TIMEOUT_BIN" "$BASH_BIN" -c '
  source "$1"
  start=$(date +%s)
  infra_with_timeout 1 sleep 5
  rc=$?
  end=$(date +%s)
  echo "rc=$rc elapsed=$((end - start))"
' _ "$TIMEOUT_FN" 2>/dev/null)
slow_rc=$(printf '%s' "$slow_out" | sed -n 's/.*rc=\([0-9-]*\) .*/\1/p')
slow_elapsed=$(printf '%s' "$slow_out" | sed -n 's/.*elapsed=\([0-9]*\).*/\1/p')
if [ -n "$slow_rc" ] && [ "$slow_rc" -ne 0 ] && [ -n "$slow_elapsed" ] && [ "$slow_elapsed" -le 3 ]; then
  echo "ok   - infra_with_timeout fallback bounds a slow command ($slow_out)"
  pass=$((pass + 1))
else
  echo "FAIL - infra_with_timeout fallback bounds a slow command (got: $slow_out)"
  fail=$((fail + 1))
fi

# Coordinator addendum (2026-11-16): a server listed in .mcp.json but
# disabled via disabledMcpjsonServers (in any settings file the session
# reads) is a WARN naming that settings file -- it must not read as
# "reachable" just because .mcp.json names it.
reset_fixture
printf '{"mcpServers": {}}\n' > "$CLAUDE_MCP_CONFIG"
printf '{"mcpServers": {"code-review-graph": {}}}\n' > "$WORKSPACE_ROOT/.mcp.json"
printf '{"enableAllProjectMcpServers": true}\n' > "$CLAUDE_USER_SETTINGS"
mkdir -p "$WORKSPACE_ROOT/.claude"
printf '{"disabledMcpjsonServers": ["code-review-graph"]}\n' > "$WORKSPACE_ROOT/.claude/settings.local.json"
check "disabledMcpjsonServers names the settings file" "Infra: code-review-graph WARN runs, but disabled via" "" 0
if printf '%s' "$(run_infra)" | grep -qF "settings.local.json"; then
  echo "ok   - disabled-server WARN names the settings file"
  pass=$((pass + 1))
else
  echo "FAIL - disabled-server WARN does not name the settings file"
  fail=$((fail + 1))
fi
rm -f "$WORKSPACE_ROOT/.mcp.json"

# Round 2, Minor: a Claude local-scope server, registered per-project
# under projects[<path>].mcpServers in the same file top-level mcpServers
# lives in, counts as reachable the same way a user-scope entry does.
reset_fixture
printf '{"mcpServers": {}, "projects": {"%s": {"mcpServers": {"ctx": {}}}}}\n' "$WORKSPACE_ROOT" > "$CLAUDE_MCP_CONFIG"
check "a Claude local-scope project entry is reachable" "Infra: ctx OK" "ctx WARN" 0

# Round 2, coordinator review: a non-dict, non-empty `projects` value
# (`[] or {}` already falls back to {} on its own, same as a missing key,
# so this needs a truthy non-dict to reach the unguarded `.get()` this
# fixes) must not abort the lookup before it reaches the project-scope
# .mcp.json check that follows: a crash there and a found-and-approved
# .mcp.json entry are not distinguishable by output alone unless something
# downstream of the crash point would otherwise be found.
reset_fixture
printf '{"mcpServers": {}, "projects": ["not-a-mapping"]}\n' > "$CLAUDE_MCP_CONFIG"
printf '{"mcpServers": {"ctx": {}}}\n' > "$WORKSPACE_ROOT/.mcp.json"
printf '{"enableAllProjectMcpServers": true}\n' > "$CLAUDE_USER_SETTINGS"
check "a non-object projects value does not block the .mcp.json lookup after it" "Infra: ctx OK" "ctx WARN" 0
rm -f "$WORKSPACE_ROOT/.mcp.json"

# A commented-out Codex table header is not a registration: TOML treats
# `# [mcp_servers.ctx]` as a comment, so a substring match that ignores the
# leading `#` would read this host as having ctx reachable when it does not.
reset_fixture
printf '{"mcpServers": {}}\n' > "$CLAUDE_MCP_CONFIG"
printf '# [mcp_servers.ctx]\ncommand = "uvx"\n' > "$CODEX_MCP_CONFIG"
check "a commented-out Codex table header is not a registration" "Infra: ctx WARN runs, but not registered" "" 0

# #328 follow-up (owner direction): registration is judged for the host
# actually running the check, not either host. A Claude-hosted seat (the
# fixture default) with only an active Codex registration for the tool is
# still a gap here -- the exact false OK the owner measured on a real
# Claude-hosted seat whose only registration was Codex's -- and the WARN
# names which host it measured.
reset_fixture
printf '{"mcpServers": {"ctx": {}}}\n' > "$CLAUDE_MCP_CONFIG"
printf '{"mcpServers": {"code-review-graph": {}}}\n' > "$WORKSPACE_ROOT/.mcp.json"
mkdir -p "$WORKSPACE_ROOT/.claude"
printf '{"disabledMcpjsonServers": ["code-review-graph"]}\n' > "$WORKSPACE_ROOT/.claude/settings.local.json"
printf '[mcp_servers.code-review-graph]\ncommand = "uvx"\n' > "$CODEX_MCP_CONFIG"
check "a Claude-hosted seat does not accept a Codex-only registration" \
  "Infra: code-review-graph WARN runs, but registered for codex, not claude" "code-review-graph OK" 0
rm -f "$WORKSPACE_ROOT/.mcp.json"

# Symmetric case: a Codex-hosted seat does not accept a Claude-only
# registration either.
reset_fixture
MOGUI_MASTER_HOST_RUNTIME=codex
printf '{"mcpServers": {"ctx": {}}}\n' > "$CLAUDE_MCP_CONFIG"
printf '' > "$CODEX_MCP_CONFIG"
check "a Codex-hosted seat does not accept a Claude-only registration" \
  "Infra: ctx WARN runs, but registered for claude, not codex" "ctx OK" 0
MOGUI_MASTER_HOST_RUNTIME=claude

# Symmetric case: a Codex-hosted seat with its own active registration is OK.
reset_fixture
MOGUI_MASTER_HOST_RUNTIME=codex
printf '{"mcpServers": {}}\n' > "$CLAUDE_MCP_CONFIG"
printf '[mcp_servers.ctx]\ncommand = "uvx"\n' > "$CODEX_MCP_CONFIG"
check "a Codex-hosted seat with its own registration is OK" "Infra: ctx OK" "ctx WARN" 0
MOGUI_MASTER_HOST_RUNTIME=claude

# An unmeasurable host (no MOGUI_MASTER_HOST_RUNTIME, no instance-runtime.json
# master_host_runtime) never reads as OK, even when one host's registration
# is actually reachable: this check cannot confirm it is this session's own
# host, so it names the gap rather than guessing.
reset_fixture
MOGUI_MASTER_HOST_RUNTIME=""
check "an unmeasurable host warns naming itself, never OK" \
  "Infra: ctx WARN runs, but registered for claude, but this session's own host is unmeasurable" "ctx OK" 0
MOGUI_MASTER_HOST_RUNTIME=claude

# Round 2, Important #3: a Codex table with `enabled = false` is not
# reachable, even though the table header itself matches.
reset_fixture
printf '{"mcpServers": {"ctx": {}}}\n' > "$CLAUDE_MCP_CONFIG"
printf '[mcp_servers.code-review-graph]\nenabled = false\ncommand = "uvx"\n' > "$CODEX_MCP_CONFIG"
check "a Codex entry with enabled = false is not reachable" \
  "Infra: code-review-graph WARN runs, but not registered" "code-review-graph OK" 0

# Round 2, Important #3: the quoted table header form is accepted the same
# as the bare one. Run this one as a Codex-hosted seat (#328): it is
# specifically exercising codex_mcp_reachable's TOML parsing, and a
# Codex-only registration is no longer an OK on the fixture's default
# Claude-hosted seat.
reset_fixture
MOGUI_MASTER_HOST_RUNTIME=codex
printf '{"mcpServers": {"ctx": {}}}\n' > "$CLAUDE_MCP_CONFIG"
printf '[mcp_servers."code-review-graph"]\ncommand = "uvx"\n' > "$CODEX_MCP_CONFIG"
check "a quoted Codex table header is accepted" "Infra: code-review-graph OK" "code-review-graph WARN" 0
MOGUI_MASTER_HOST_RUNTIME=claude

# Round 2, Minor: a timeout kill (124 from a real `timeout`/`gtimeout`, or
# 137/143 from the plain-bash fallback's SIGKILL/SIGTERM) reports the bound
# it hit, not the generic empty-output fallback text.
reset_fixture
cat > "$BIN_DIR/code-review-graph" <<'EOF'
#!/bin/bash
sleep 5
EOF
chmod +x "$BIN_DIR/code-review-graph"
INFRA_TIMEOUT_SECONDS=1
check "a timeout kill reports the bound it hit" "Infra: code-review-graph WARN timed out after 1s" "" 0
unset INFRA_TIMEOUT_SECONDS

# PR #326 round 2, Important #1: the probe reads its launcher from
# MCP_SERVERS_CONFIG rather than a hardcoded "code-review-graph" -- proven
# here with a launcher under a name the real stub never uses, so a
# regression back to the hardcoded probe would miss this binary entirely
# and fail closed as "absent from PATH", not pass by coincidence.
reset_fixture
rm -f "$BIN_DIR/code-review-graph"
# Isolate from a real host-wide code-review-graph the same way case (d)
# does: without this, reverting to the hardcoded probe would still find
# that real binary on SAFE_PATH and print OK, masking the regression.
ORIGINAL_SAFE_PATH="$SAFE_PATH"
real_crg=$(PATH="$SAFE_PATH" command -v code-review-graph 2>/dev/null) || true
if [ -n "$real_crg" ]; then
  real_crg_dir=$(dirname "$real_crg")
  SAFE_PATH=$(printf '%s' "$SAFE_PATH" | tr ':' '\n' | grep -vF "$real_crg_dir" | tr '\n' ':')
  SAFE_PATH="${SAFE_PATH%:}"
fi
cat > "$BIN_DIR/crg-pinned-launcher" <<'EOF'
#!/bin/bash
echo "code-review-graph 2.4.0"
EOF
chmod +x "$BIN_DIR/crg-pinned-launcher"
write_mcp_servers_config crg-pinned-launcher code-review-graph@2.4.0
check "the probe runs the launcher named in MCP_SERVERS_CONFIG, not a hardcoded name" \
  "Infra: code-review-graph OK" "code-review-graph WARN" 0
SAFE_PATH="$ORIGINAL_SAFE_PATH"

# PR #326 round 2, Important #1: a missing MCP_SERVERS_CONFIG warns naming
# the read failure instead of crashing or falling through to a bare
# `code-review-graph` on PATH.
reset_fixture
CRG_MCP_CONFIG_SAVED="$CRG_MCP_CONFIG"
CRG_MCP_CONFIG="$TMP/no-such-mcp-servers.json"
check "a missing MCP_SERVERS_CONFIG warns naming the read failure" \
  "Infra: code-review-graph WARN could not read $CRG_MCP_CONFIG" "" 0
CRG_MCP_CONFIG="$CRG_MCP_CONFIG_SAVED"

# PR #326 round 2, Important #1: an MCP_SERVERS_CONFIG that exists but
# carries no code-review-graph entry (or one with no command/args) warns
# naming that gap, rather than probing nothing and reading as a clean pass.
reset_fixture
printf '{"mcpServers": {}}\n' > "$CRG_MCP_CONFIG"
check "an MCP_SERVERS_CONFIG with no code-review-graph entry warns naming the file" \
  "Infra: code-review-graph WARN no code-review-graph entry in $CRG_MCP_CONFIG" "" 0

# PR #326 round 2 follow-up: a non-object mcpServers must not crash the
# parser with an uncaught Python traceback -- it must warn by name.
reset_fixture
printf '{"mcpServers": ["not-a-mapping"]}\n' > "$CRG_MCP_CONFIG"
check "a non-object mcpServers warns naming the file, never crashes" \
  "Infra: code-review-graph WARN mcpServers in $CRG_MCP_CONFIG is not an object" "" 0

# PR #326 round 2 follow-up: a string-valued args field makes args[0] a
# single character in Python, not a missing value -- must warn by name
# instead of silently probing that one-character "spec".
reset_fixture
printf '{"mcpServers": {"code-review-graph": {"command": "code-review-graph", "args": "serve"}}}\n' > "$CRG_MCP_CONFIG"
check "a string-valued args field warns naming the entry, never probes a one-character spec" \
  "Infra: code-review-graph WARN code-review-graph entry in $CRG_MCP_CONFIG has no valid command/args" "" 0

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
