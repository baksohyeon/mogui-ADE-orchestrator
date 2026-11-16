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

SELFCHECK_BIN="${SELFCHECK_BIN:-./scripts/harness-selfcheck.sh}"

# harness-selfcheck.sh is instance-owned (template_common.INSTANCE_OWNED_EXACT):
# a rendered template-only copy never has one, so there is nothing to measure
# at the default path. An explicit override that is still missing is a typo
# or a stale binary, not that case, and fails loudly instead of skipping.
if [ ! -f "$SELFCHECK_BIN" ]; then
  if [ "$SELFCHECK_BIN" != "./scripts/harness-selfcheck.sh" ]; then
    echo "FAIL: SELFCHECK_BIN=$SELFCHECK_BIN not found" >&2
    exit 1
  fi
  echo "SKIP: $SELFCHECK_BIN not found (instance-owned, not part of a template-only checkout)"
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

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

# $1 = space-separated list of providers ctx reports as indexed.
write_stub_ctx() {
  local providers_json
  providers_json=$(python3 -c "import json, sys; print(json.dumps(sys.argv[1].split()))" "$1")
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
exit 1
EOF
  chmod +x "$BIN_DIR/ctx"
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
  printf 'all sources available\n' > "$CTX_SOURCES_FILE"
  printf '{"mcpServers": {"ctx": {}, "code-review-graph": {}}}\n' > "$CLAUDE_MCP_CONFIG"
  printf '{}\n' > "$CLAUDE_USER_SETTINGS"
  printf '' > "$CODEX_MCP_CONFIG"
  rm -rf "$WORKSPACE_ROOT/.claude" "$WORKSPACE_ROOT/.mcp.json"
  mkdir -p "$WORKSPACE_ROOT/.claude"
  rm -rf "$REPO_A"
  mkdir -p "$REPO_A/.code-review-graph"
  touch "$REPO_A/.code-review-graph/graph.db"
  printf '{"repos": [{"path": "%s", "alias": "repo-a"}]}\n' "$REPO_A" > "$CRG_REGISTRY"
}

run_infra() {
  PATH="$BIN_DIR:$SAFE_PATH" HOME="$TMP" \
    WORKSPACE_ROOT="$WORKSPACE_ROOT" OPS_DIR="$OPS_DIR" \
    CLAUDE_MCP_CONFIG="$CLAUDE_MCP_CONFIG" CLAUDE_USER_SETTINGS="$CLAUDE_USER_SETTINGS" \
    CODEX_MCP_CONFIG="$CODEX_MCP_CONFIG" \
    CODE_REVIEW_GRAPH_REGISTRY="$CRG_REGISTRY" \
    CODE_REVIEW_GRAPH_STALE_DAYS="${CODE_REVIEW_GRAPH_STALE_DAYS:-7}" \
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

# (c) A graph updated 30 days ago warns with the day count.
reset_fixture
old_ts=$(python3 -c "import time; print(int(time.time() - 30 * 86400))")
touch -t "$(python3 -c "import datetime; print(datetime.datetime.fromtimestamp($old_ts).strftime('%Y%m%d%H%M'))")" "$REPO_A/.code-review-graph/graph.db"
check "(c) a 30-day-old graph is named with its day count" "Infra: code-review-graph WARN stale: repo-a (30d)" "" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")

# (d) A tool absent from PATH warns, never crashes.
reset_fixture
rm -f "$BIN_DIR/code-review-graph"
check "(d) absent from PATH warns without crashing" "Infra: code-review-graph WARN absent from PATH" "" 0
exit_codes+=("$(run_infra >/dev/null 2>&1; echo $?)")

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

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
