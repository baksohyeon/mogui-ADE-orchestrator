#!/bin/bash
# Regression test for the BLOCK:/INFO: warning grading and the exit-code
# escalation it drives in harness-selfcheck.sh (#336 item 2: a boot card
# that "stops on non-zero" must not read a required-infra warning as a
# pass).
#
# Runs the real script end to end against a minimal rendered fixture,
# unlike test-harness-selfcheck-infra.sh and test-seat-check.sh, which
# exercise one extracted block or function in isolation: the grading's
# effect on the exit code is computed at the very bottom of the whole
# script, after every other check has already run, so an isolated block
# cannot show it. OPS_DIR is not overridable by env -- the real script
# derives it from its own file location (`dirname "${BASH_SOURCE[0]}"`) --
# so the fixture places a rendered copy of the script under
# $OPS_DIR/scripts/, the same way a real install would.
set -u

cd "$(dirname "$0")/.."

SELFCHECK_DEFAULT="./scripts/harness-selfcheck.sh"
# Overridable, like test-harness-selfcheck-infra.sh and test-seat-check.sh,
# so the same fixture can exercise a different build of the script (for
# example, to show that a case here fails against the pre-#336-item-2 code).
SELFCHECK_SRC="${SELFCHECK_BIN:-$SELFCHECK_DEFAULT}"

# harness-selfcheck.sh is instance-owned (template_common.INSTANCE_OWNED_EXACT):
# a rendered template-only copy never has one, so there is nothing to measure
# at the default path. An explicit override that is still missing is a typo
# or a stale binary, not that case, and fails loudly instead of skipping.
if [ ! -f "$SELFCHECK_SRC" ]; then
  if [ "$SELFCHECK_SRC" != "$SELFCHECK_DEFAULT" ]; then
    echo "FAIL: SELFCHECK_BIN=$SELFCHECK_SRC not found" >&2
    exit 1
  fi
  echo "SKIP: $SELFCHECK_SRC not found (instance-owned, not part of a template-only checkout)"
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "${TMP:?}"' EXIT

pass=0
fail=0

OPS_DIR="$TMP/ops"
WORKSPACE_ROOT="$TMP/workspace"
BIN_DIR="$TMP/bin"
mkdir -p "$OPS_DIR/scripts" "$OPS_DIR/workspace-card" "$OPS_DIR/.beads" \
  "$OPS_DIR/docs/observability" "$OPS_DIR/docs/runbooks" \
  "$WORKSPACE_ROOT/.claude" "$BIN_DIR" "$TMP/home"

# Strip any real shim directory (mise, asdf, ...) out of the inherited PATH,
# the same guard test-harness-selfcheck-infra.sh uses: a case that removes a
# stub to test "absent from PATH" must not fall through to a real shim for
# the same name on this host.
SAFE_PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '/shims\(/\|$\)' | tr '\n' ':')
SAFE_PATH="${SAFE_PATH%:}"

sed -e "s#{{WORKSPACE_ROOT}}#$WORKSPACE_ROOT#" -e "s#{{OPS_REPO}}#$OPS_DIR#" \
  "$SELFCHECK_SRC" > "$OPS_DIR/scripts/harness-selfcheck.sh"
chmod +x "$OPS_DIR/scripts/harness-selfcheck.sh"

# A trivial, always-passing template-check stand-in: this test is about the
# Infra: grading, not template currency, which has its own coverage in
# test-template-currency-line.sh.
cat > "$OPS_DIR/scripts/template-check" <<'EOF'
#!/bin/bash
echo '{"installed_version": "v0-fixture", "manifest_status": "ok", "absent_required": [], "retired": [], "unknown_present": [], "report_set": "installed-manifest", "retirements_status": "ok"}'
EOF
chmod +x "$OPS_DIR/scripts/template-check"

printf '{"template_version": "v0-fixture", "files": ["a"]}\n' > "$OPS_DIR/MANIFEST.json"
echo "# Adoption ledger" > "$OPS_DIR/docs/observability/template-adoption-2026-08-08.md"

echo "fixture card" > "$OPS_DIR/workspace-card/CLAUDE.md"
cp "$OPS_DIR/workspace-card/CLAUDE.md" "$OPS_DIR/workspace-card/AGENTS.md"
cp "$OPS_DIR/workspace-card/CLAUDE.md" "$OPS_DIR/CLAUDE.md"
cp "$OPS_DIR/workspace-card/CLAUDE.md" "$OPS_DIR/AGENTS.md"
cp "$OPS_DIR/workspace-card/CLAUDE.md" "$WORKSPACE_ROOT/CLAUDE.md"
cp "$OPS_DIR/workspace-card/CLAUDE.md" "$WORKSPACE_ROOT/AGENTS.md"

printf '{}\n' > "$WORKSPACE_ROOT/.claude/settings.json"

# "repo::path" form (harness-selfcheck.sh's seat probe), so the fixture
# needs no orca-data.json -- that shape of workspace id resolves to its own
# path with no clones to check, which test-seat-check.sh covers separately.
SEAT_WS="fixture::$WORKSPACE_ROOT"
{
  echo "# Role State"
  echo ""
  echo "Master seat (absolute path): \`$WORKSPACE_ROOT\`"
  echo "Master seat (workspace id): \`$SEAT_WS\`"
} > "$OPS_DIR/docs/runbooks/role-state.md"

cat > "$BIN_DIR/bd" <<EOF
#!/bin/bash
echo "$OPS_DIR/.beads"
EOF
chmod +x "$BIN_DIR/bd"

cat > "$BIN_DIR/orca" <<'EOF'
#!/bin/bash
if [ "$1" = "--version" ]; then
  echo "1.0.0-fixture"
  exit 0
fi
if [ "$1" = "search" ]; then
  printf '%s\n' '{"ok": true, "result": {"sessionsByAgent": {"claude": 1, "codex": 0}}}'
  exit 0
fi
exit 1
EOF
chmod +x "$BIN_DIR/orca"

CLAUDE_MCP_CONFIG="$TMP/claude.json"
CLAUDE_USER_SETTINGS="$TMP/user-settings.json"
CODEX_MCP_CONFIG="$TMP/codex-config.toml"
CRG_MCP_CONFIG="$TMP/mcp-servers.json"
CRG_REGISTRY="$TMP/registry.json"
REPO_A="$TMP/repo-a"
CTX_SOURCES_FILE="$TMP/ctx-sources.txt"
printf '{}\n' > "$CLAUDE_USER_SETTINGS"

# $1 = space-separated providers ctx reports as indexed, $2 = optional
# `ctx upgrade status --format json` body (default: up to date at 2.4.1).
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
if [ "\$1" = "upgrade" ] && [ "\$2" = "status" ] && [ "\$3" = "--format" ] && [ "\$4" = "json" ]; then
  printf '%s\n' '$upgrade_json'
  exit 0
fi
exit 1
EOF
  chmod +x "$BIN_DIR/ctx"
}

write_stub_crg() {
  cat > "$BIN_DIR/code-review-graph" <<'EOF'
#!/bin/bash
echo "code-review-graph 2.4.0"
EOF
  chmod +x "$BIN_DIR/code-review-graph"
}

reset_fixture() {
  rm -f "$BIN_DIR/ctx" "$BIN_DIR/code-review-graph"
  write_stub_ctx "claude codex"
  write_stub_crg
  printf 'all sources available\n' > "$CTX_SOURCES_FILE"
  printf '{"mcpServers": {"ctx": {}, "code-review-graph": {}}}\n' > "$CLAUDE_MCP_CONFIG"
  printf '' > "$CODEX_MCP_CONFIG"
  printf '{"mcpServers": {"code-review-graph": {"command": "code-review-graph", "args": ["code-review-graph@2.4.0", "serve"]}}}\n' > "$CRG_MCP_CONFIG"
  rm -rf "${REPO_A:?}"
  mkdir -p "$REPO_A/.code-review-graph"
  touch "$REPO_A/.code-review-graph/graph.db"
  printf '{"repos": [{"path": "%s", "alias": "repo-a"}]}\n' "$REPO_A" > "$CRG_REGISTRY"
}

# The real script reads several of its own knobs from the environment when
# present (BEADS_DIR, ROLE_STATE_PATH, ORCA_DATA_PATH, TEMPLATE_MANIFEST_FILE,
# TEMPLATE_ADOPTION_LEDGER, INFRA_TIMEOUT_SECONDS, CODE_REVIEW_GRAPH_STALE_DAYS,
# MOGUI_INSTANCE_RUNTIME_CONFIG/INSTANCE_RUNTIME_CONFIG). Left set in the
# calling shell, any one of them would redirect a check outside this fixture
# and fail every case for a reason that has nothing to do with the grading
# this test exists to cover -- unset them all so only the overrides below,
# and the files this fixture wrote under $OPS_DIR/$WORKSPACE_ROOT, apply.
run_selfcheck() {
  env -u BEADS_DIR -u ROLE_STATE_PATH -u ORCA_DATA_PATH \
    -u TEMPLATE_MANIFEST_FILE -u TEMPLATE_ADOPTION_LEDGER \
    -u INFRA_TIMEOUT_SECONDS -u CODE_REVIEW_GRAPH_STALE_DAYS \
    -u MOGUI_INSTANCE_RUNTIME_CONFIG -u INSTANCE_RUNTIME_CONFIG \
    PATH="$BIN_DIR:$SAFE_PATH" HOME="$TMP/home" \
    MOGUI_MASTER_HOST_RUNTIME=claude \
    CLAUDE_MCP_CONFIG="$CLAUDE_MCP_CONFIG" CLAUDE_USER_SETTINGS="$CLAUDE_USER_SETTINGS" \
    CODEX_MCP_CONFIG="$CODEX_MCP_CONFIG" \
    CODE_REVIEW_GRAPH_REGISTRY="$CRG_REGISTRY" MCP_SERVERS_CONFIG="$CRG_MCP_CONFIG" \
    ORCA_WORKSPACE_ID="${1:-$SEAT_WS}" \
    bash "$OPS_DIR/scripts/harness-selfcheck.sh"
}

# $1 = case name, $2 = expected substring, $3 = expected exit code,
# $4 = optional ORCA_WORKSPACE_ID override (default: $SEAT_WS, the recorded one).
check_case() {
  local name="$1" expect="$2" want_rc="$3" wsid="${4:-}" out rc
  out=$(run_selfcheck "$wsid" 2>&1)
  rc=$?
  if printf '%s' "$out" | grep -qF "$expect" && [ "$rc" -eq "$want_rc" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect (exit $want_rc)"
    echo "       actual exit: $rc"
    printf '%s\n' "$out" | sed 's/^/       | /'
    fail=$((fail + 1))
  fi
}

# Baseline: everything clean, no warning at all -- exit 0, no grade tag.
reset_fixture
check_case "clean fixture passes with no grading tag" \
  "Self-check summary: 0 blocking warning(s), 0 informational warning(s)" 0

# A. One blocking Infra warning (code-review-graph's launcher absent from
# PATH) is enough on its own to move the exit code off 0, to the documented
# blocking-warning code -- distinct from both a clean pass (0) and a hard
# failure (1).
reset_fixture
rm -f "$BIN_DIR/code-review-graph"
ORIGINAL_SAFE_PATH="$SAFE_PATH"
real_crg=$(PATH="$SAFE_PATH" command -v code-review-graph 2>/dev/null) || true
if [ -n "$real_crg" ]; then
  real_crg_dir=$(dirname "$real_crg")
  SAFE_PATH=$(printf '%s' "$SAFE_PATH" | tr ':' '\n' | grep -vF "$real_crg_dir" | tr '\n' ':')
  SAFE_PATH="${SAFE_PATH%:}"
fi
check_case "a single blocking Infra warning is tagged BLOCK:" \
  "BLOCK: Infra: code-review-graph WARN launcher 'code-review-graph' absent from PATH" 3
check_case "a single blocking Infra warning escalates the exit code" \
  "Self-check summary: 1 blocking warning(s), 0 informational warning(s)" 3
SAFE_PATH="$ORIGINAL_SAFE_PATH"

# B. An informational-only warning (ctx-upgrade behind latest, ctx and
# code-review-graph otherwise clean) never moves the exit code off 0, and
# the INFO: line still prints.
reset_fixture
write_stub_ctx "claude codex" '{"current_version": "2.9.0", "state": {"status": "up_to_date", "latest_version": "2.10.0"}}'
check_case "an informational-only warning still prints the INFO: line" \
  "INFO: Infra: ctx-upgrade WARN ctx 2.9.0 is behind 2.10.0" 0
check_case "an informational-only warning never escalates the exit code" \
  "Self-check summary: 0 blocking warning(s), 1 informational warning(s)" 0

# C. A probe that produces an empty result (an empty code-review-graph
# registry -- nothing registered to check) is graded blocking, never
# informational: an unmeasurable or empty probe result is never a soft pass.
reset_fixture
printf '{"repos": []}\n' > "$CRG_REGISTRY"
check_case "an empty registry (empty probe result) is graded blocking" \
  "BLOCK: Infra: code-review-graph WARN no repository registered" 3

# D. The main ctx line itself (not just ctx-upgrade or code-review-graph)
# is graded blocking, end to end: ctx absent from PATH is a single blocking
# warning with code-review-graph otherwise clean. ctx-upgrade uses the
# identical `command -v ctx` probe, so it reports the same absence as a
# dependent line, not a second cause (#336 item 2 round 2, Minor 1): one
# missing tool must count once, not twice for the same reason.
reset_fixture
rm -f "$BIN_DIR/ctx"
ORIGINAL_SAFE_PATH="$SAFE_PATH"
real_ctx=$(PATH="$SAFE_PATH" command -v ctx 2>/dev/null) || true
if [ -n "$real_ctx" ]; then
  real_ctx_dir=$(dirname "$real_ctx")
  SAFE_PATH=$(printf '%s' "$SAFE_PATH" | tr ':' '\n' | grep -vF "$real_ctx_dir" | tr '\n' ':')
  SAFE_PATH="${SAFE_PATH%:}"
fi
check_case "the main ctx line is tagged BLOCK:" \
  "BLOCK: Infra: ctx WARN absent from PATH" 3
check_case "the dependent ctx-upgrade line names ctx as the cause, without its own count" \
  "BLOCK: Infra: ctx-upgrade WARN absent from PATH (follows from ctx missing)" 3
check_case "a missing ctx counts once, not twice, for one cause" \
  "Self-check summary: 1 blocking warning(s), 0 informational warning(s)" 3
SAFE_PATH="$ORIGINAL_SAFE_PATH"

# E. A failed (non-timeout) ctx-upgrade probe whose raw first line of output
# happens to contain the substring "is behind" for an unrelated reason is
# still graded blocking: the probe never returned 0, so it never actually
# measured a version to compare, and text content alone must not grant INFO.
reset_fixture
cat > "$BIN_DIR/ctx" <<EOF
#!/bin/bash
if [ "\$1" = "status" ]; then
  printf '%s\n' '{"daemon": {"jobs": {"core_refresh": {"progress": {"providers": ["claude", "codex"]}}}}}'
  exit 0
fi
if [ "\$1" = "sources" ]; then
  cat "$CTX_SOURCES_FILE"
  exit 0
fi
if [ "\$1" = "upgrade" ] && [ "\$2" = "status" ]; then
  echo "scheduled rollout is behind plan, aborting"
  exit 1
fi
exit 1
EOF
chmod +x "$BIN_DIR/ctx"
check_case "a failed probe whose text happens to say 'is behind' is still graded BLOCK:" \
  "BLOCK: Infra: ctx-upgrade WARN scheduled rollout is behind plan, aborting" 3

# F. The Seat: NOTICE line (workspace id rotated, same path, no clone) is
# graded informational end to end: exit stays 0 on the whole script, the
# same proof test-seat-check.sh's own fixture cannot give because its
# lighter setup does not carry the whole run to a clean exit. "other::"
# shares $WORKSPACE_ROOT with the recorded id but differs before "::", so
# it resolves to the same sole, correct seat and only the record is stale.
reset_fixture
check_case "the rotated-workspace-id seat notice is tagged INFO:" \
  "Seat: INFO: NOTICE" 0 "other::$WORKSPACE_ROOT"
check_case "the rotated-workspace-id seat notice never escalates the exit code" \
  "Self-check summary: 0 blocking warning(s), 1 informational warning(s)" 0 "other::$WORKSPACE_ROOT"

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
