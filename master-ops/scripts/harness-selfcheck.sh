#!/bin/bash
# Harness self-check: measure reachability of skills, hooks, and tracker.
# This check catches components present on disk but unwired or unreachable
# from the host discovery paths (section 8 of the charter: silence is not pass).
set -e

WORKSPACE_ROOT="{{WORKSPACE_ROOT}}"
OPS_REPO="{{OPS_REPO}}"
# Anchor every repo-relative path on this script's own location, not on the
# invoking cwd. The boot card runs some commands from the workspace root and
# this one used to demand the ops repo, so no single directory satisfied the
# card end to end and a successor following it in order hit a false failure.
# The seat verdict still comes from ORCA_WORKSPACE_ID, never from $PWD.
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS_FILE="$WORKSPACE_ROOT/.claude/settings.json"
SKILLS_DISCOVERY_PATH="$WORKSPACE_ROOT/.claude/skills"
HOOKS_REPO_DIR="$OPS_DIR/scripts/hooks"
TEMPLATE_CHECK="$OPS_DIR/scripts/template-check"
exit_code=0

# --- Orca version/install check ---
# `orca --version` plus its binary's last-modified time, with a note when the
# version changed since the previous run of this script, a cheap drift
# signal for the orchestration JSON shape this seat's readers (dispatch,
# worker-wait) depend on (docs/runbooks/orca-json.md): orca 1.4.246 changed
# those keys with no deprecation notice, and every prior reader failed silent.
ORCA_BIN="$(command -v orca 2>/dev/null || true)"
if [ -n "$ORCA_BIN" ]; then
  orca_version=$(orca --version 2>/dev/null || echo "undeterminable")
  orca_mtime=$(python3 -c "
import datetime, os, sys
print(datetime.datetime.fromtimestamp(os.path.getmtime(sys.argv[1])).isoformat(timespec='seconds'))
" "$ORCA_BIN" 2>/dev/null || echo "undeterminable")
  orca_version_state="$HOME/.mogui/orca-version.txt"
  orca_line="Orca: $orca_version (last install $orca_mtime)"
  if [ -f "$orca_version_state" ]; then
    orca_prev_version=$(cat "$orca_version_state" 2>/dev/null || true)
    if [ -n "$orca_prev_version" ] && [ "$orca_prev_version" != "$orca_version" ]; then
      orca_line="$orca_line, changed since $orca_prev_version"
    fi
  fi
  # Best-effort: an unwritable $HOME must not trip `set -e` and abort this
  # script before it reports the remaining checks below.
  if mkdir -p "$HOME/.mogui" 2>/dev/null; then
    printf '%s\n' "$orca_version" > "$orca_version_state" 2>/dev/null || true
  fi
  echo "$orca_line"
else
  echo "Orca: undeterminable (orca binary not found on PATH)"
  exit_code=1
fi

# --- Seat's template-adoption check ---
# Ported from the seat's harness-selfcheck.sh (owner direction 2026-09-23): a
# generated operations repository stamps the template version it was created
# from into MANIFEST.json, then records adoption progress in a ledger under
# docs/observability/. This template ships its own MANIFEST.json but no
# ledger, so a default run here takes the "ledger missing" branch; both paths
# stay overridable so a test fixture can stand in for either.
TEMPLATE_MANIFEST_FILE="${TEMPLATE_MANIFEST_FILE:-$OPS_DIR/MANIFEST.json}"
TEMPLATE_ADOPTION_LEDGER="${TEMPLATE_ADOPTION_LEDGER:-$OPS_DIR/docs/observability/template-adoption-2026-08-08.md}"

# A function, not inline code, so a test can exercise it directly (like
# tracker_candidate_from_line below) instead of running the whole script and
# hitting whatever the later Skills/Hooks/Card checks do in that environment.
# Return status doubles as this probe's exit-code contribution.
template_adoption_probe() {
  if [ ! -f "$TEMPLATE_MANIFEST_FILE" ]; then
    echo "Template: absent (MANIFEST.json missing)"
    return 1
  fi
  local probe
  # The `|| probe=""` guard matters under `set -e`: without it, a python3
  # failure (malformed MANIFEST.json) fails the assignment itself and aborts
  # the whole script with no output instead of falling through to the
  # "undecided" case below.
  probe=$(python3 - "$TEMPLATE_MANIFEST_FILE" << 'EOFTEMPLATE' 2>/dev/null
import json, sys

manifest_path = sys.argv[1]
manifest = json.load(open(manifest_path, encoding="utf-8"))
manifest_version = manifest.get("template_version")
files = manifest.get("files")
if not isinstance(manifest_version, str) or not manifest_version.strip():
    print("ERROR|MANIFEST.json template_version missing")
elif not isinstance(files, list):
    print("ERROR|MANIFEST.json files list missing")
else:
    print(f"OK|{manifest_version.strip()}")
EOFTEMPLATE
  ) || probe=""
  case "$probe" in
    OK\|*)
      local stamped_version="${probe#OK|}"
      if [ -f "$TEMPLATE_ADOPTION_LEDGER" ]; then
        echo "Template: $stamped_version stamped, adoption incomplete (see $TEMPLATE_ADOPTION_LEDGER)"
        return 0
      else
        echo "Template: $stamped_version stamped, adoption ledger missing"
        return 1
      fi
      ;;
    ERROR\|*)
      echo "Template: undecided (${probe#ERROR|})"
      return 1
      ;;
    *)
      echo "Template: undecided (could not read TEMPLATE-VERSION or MANIFEST.json)"
      return 1
      ;;
  esac
}

template_adoption_probe || exit_code=1

# --- Seat check ---
# A master that is seated in the wrong place passes every other check in this
# script, and passed all three placement-evidence checks in the succession
# runbook too: pane, cwd, and transcript agree with each other and all three
# agree on the wrong seat. Only a comparison against the recorded seat catches
# it. Basis: 2026-08-04, Generation 2 booted into the ops-repo worktree instead
# of the workspace pane and no check noticed. Owner did.
#
# ORCA_WORKSPACE_ID is the signal, not $PWD: this script must be run from the
# ops repo, so the invoking cwd is the same for a correctly and incorrectly
# seated master. The workspace id survives cd.
#
# What this gates is ambiguity, not identity. Measured 2026-08-04, second
# recurrence:
#   - Folder workspaces are absent from the worktree resolver. `worktree show`
#     and `terminal create --worktree` answer selector_not_found for path:,
#     id:folder:, and name: alike, so a spawner cannot address the seat and
#     starts the successor in a global floating terminal instead.
#   - Orca then adopts that terminal into a folder workspace for its cwd by
#     minting a NEW folderWorkspace record rather than reusing the existing one
#     for that path. Three clones of the seat exist so far, one per generation:
#     c8f1342f, 1155b1cd, e4c14228, identical folderPath on all three.
#
# So neither the terminal handle nor the workspace id is stable: this session
# booted as term_6cb851c7 in `global-floating-terminal` and became
# term_cc362494 in folder:e4c14228 without restarting. Gating on id equality
# would fail every correctly seated successor. The invariant that does hold is
# that exactly one live folder workspace should own the seat path; while clones
# exist, "which mogui am I in" has no answer and the next succession can land
# in a stale one. Duplicates block; an id that merely changed is reported.
ROLE_STATE_PATH="${ROLE_STATE_PATH:-$OPS_DIR/docs/runbooks/role-state.md}"
ORCA_DATA_PATH="${ORCA_DATA_PATH:-$HOME/Library/Application Support/orca/profiles/local-default/orca-data.json}"

read_seat_field() {
  grep -m1 "^Master seat ($1):" "$ROLE_STATE_PATH" 2>/dev/null | sed 's/.*`\(.*\)`.*/\1/'
}

seat_fail() {
  echo "Seat: $1"
  exit_code=1
}

recorded_seat=$(read_seat_field 'absolute path')
recorded_ws=$(read_seat_field 'workspace id')

if [ -z "$recorded_seat" ]; then
  seat_fail "undecided (role-state.md records no seat path)"
elif [ -z "$ORCA_WORKSPACE_ID" ]; then
  # Never a soft pass: an unmeasurable seat is the same risk as a wrong one.
  seat_fail "undecided (ORCA_WORKSPACE_ID unset; not an Orca-managed session)"
else
  seat_probe=$(ORCA_DATA_PATH="$ORCA_DATA_PATH" python3 - "$ORCA_WORKSPACE_ID" "$recorded_seat" << 'EOFSEAT' 2>/dev/null
import json, os, sys

wsid, recorded = sys.argv[1], sys.argv[2]
path = ""
if wsid.startswith("folder:"):
    # Folder workspaces live in a registry the worktree resolver never consults,
    # so the path has to come from the profile store.
    wid = wsid.split("folder:", 1)[1]
    store = json.load(open(os.environ["ORCA_DATA_PATH"]))
    workspaces = [w for w in store.get("folderWorkspaces", []) if not w.get("isArchived")]
    for fw in workspaces:
        if fw.get("id") == wid:
            path = fw.get("folderPath", "")
            break
    clones = ["folder:" + w["id"] for w in workspaces
              if w.get("folderPath") == recorded and w.get("id") != wid]
elif "::" in wsid:
    path, clones = wsid.split("::", 1)[1], []
else:
    clones = []
print(path)
print(",".join(clones))
EOFSEAT
  )
  actual_seat=$(printf '%s\n' "$seat_probe" | sed -n 1p)
  seat_clones=$(printf '%s\n' "$seat_probe" | sed -n 2p)

  if [ -z "$actual_seat" ]; then
    seat_fail "undecided (could not resolve $ORCA_WORKSPACE_ID to a path)"
  elif [ "$actual_seat" != "$recorded_seat" ]; then
    seat_fail "MISSEATED — sitting at $actual_seat, recorded seat is $recorded_seat"
  elif [ -n "$seat_clones" ]; then
    seat_fail "AMBIGUOUS — $actual_seat is owned by more than one live workspace: $ORCA_WORKSPACE_ID plus $seat_clones. Archive the extras in Orca; until then a successor can be seated in a stale one and every path check will still pass."
  else
    echo "Seat: $actual_seat ($ORCA_WORKSPACE_ID, sole workspace for the recorded path)"
    if [ "$ORCA_WORKSPACE_ID" != "$recorded_ws" ]; then
      # Expected across a succession, not a misseat: the id rotates when the
      # pane is adopted. The record still has to be corrected.
      echo "Seat: NOTICE — workspace id changed since it was recorded ($recorded_ws -> $ORCA_WORKSPACE_ID); update 'Master seat (workspace id)' in $ROLE_STATE_PATH"
    fi
  fi
fi

# --- Skills check ---
skill_dirs=$(find "$OPS_DIR/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sed "s|$OPS_DIR/skills/||" | sort)
skill_reachable=0
skill_unreachable=""

for skill_name in $skill_dirs; do
  discovery_path="$SKILLS_DISCOVERY_PATH/$skill_name"

  # Check if skill exists at discovery path and has SKILL.md entry file.
  # The wiring may be a symlink or directory (host-dependent); test for reachability.
  if [ -d "$discovery_path" ] && [ -f "$discovery_path/SKILL.md" ]; then
    skill_reachable=$((skill_reachable + 1))
  else
    skill_unreachable="$skill_unreachable $skill_name"
    exit_code=1
  fi
done

if [ -n "$skill_unreachable" ]; then
  echo "Skills: $skill_reachable reachable, unreachable:$skill_unreachable"
else
  echo "Skills: $skill_reachable reachable"
fi

# --- Hooks check ---
# Extract all hook commands from settings, check they exist and are executable.
# Fail fast if settings is unreadable.
wired_hooks=$(python3 << EOFPYTHON
import json
import sys

try:
  with open('$SETTINGS_FILE') as f:
    settings = json.load(f)
  hooks_dict = settings.get("hooks", {})
  for event, event_hooks in hooks_dict.items():
    for entry in event_hooks:
      for hook in entry.get("hooks", []):
        if hook.get("type") == "command":
          cmd = hook.get("command", "")
          if cmd:
            print(cmd)
except Exception as e:
  sys.exit(1)
EOFPYTHON
) || {
  echo "Hooks: undecided (settings unreadable)"
  exit 2
}

hook_wired=0
hook_missing=""

# Read one complete command at a time. Word-splitting the settings text makes
# an installed path containing a space look like several commands, and it also
# leaves quotes attached to the path. shlex is the same shell-token boundary
# the host uses for these command entries.
while IFS= read -r cmd; do
  [ -n "$cmd" ] || continue
  script_path=$(python3 - "$cmd" <<'EOFPATH'
import shlex
import sys

try:
    tokens = shlex.split(sys.argv[1])
except ValueError:
    print(sys.argv[1])
    raise SystemExit(0)
for token in tokens:
    if token.endswith(".sh"):
        print(token)
        break
EOFPATH
  )

  if [ -n "$script_path" ]; then
    if [ -f "$script_path" ] && [ -x "$script_path" ]; then
      hook_wired=$((hook_wired + 1))
    else
      hook_missing="$hook_missing $(basename "$script_path")"
      exit_code=1
    fi
  fi
done <<< "$wired_hooks"

# Check for unwired hooks under scripts/hooks/
unwired_hooks=""
if [ -d "$HOOKS_REPO_DIR" ]; then
  for script in "$HOOKS_REPO_DIR"/*.sh; do
    script_name=$(basename "$script")
    # Check if this script is referenced in any wired hook
    if ! echo "$wired_hooks" | grep -q "$script_name"; then
      unwired_hooks="$unwired_hooks $script_name"
      exit_code=1
    fi
  done
fi

if [ -n "$hook_missing" ] || [ -n "$unwired_hooks" ]; then
  hook_report="$hook_wired wired"
  [ -n "$hook_missing" ] && hook_report="$hook_report, missing:$hook_missing"
  [ -n "$unwired_hooks" ] && hook_report="$hook_report, unwired:$unwired_hooks"
  echo "Hooks: $hook_report"
else
  echo "Hooks: $hook_wired wired"
fi

# --- Workspace card check ---
# The cards at the workspace root are deployed copies; the canonical pair lives in
# this repository. The root is outside every git repo, so a card edited only
# there is versioned nowhere and a stale deployment governs behaviour silently.
# Owner decision 2026-08-05: ops holds the canonical pair, onboarding deploys it.
CARD_CLAUDE_CANONICAL="$OPS_DIR/workspace-card/CLAUDE.md"
CARD_AGENTS_CANONICAL="$OPS_DIR/workspace-card/AGENTS.md"
CARD_CLAUDE_DEPLOYED="$WORKSPACE_ROOT/CLAUDE.md"
CARD_AGENTS_DEPLOYED="$WORKSPACE_ROOT/AGENTS.md"
if [ ! -f "$CARD_CLAUDE_CANONICAL" ] || [ ! -f "$CARD_AGENTS_CANONICAL" ]; then
  echo "Card: canonical pair missing at workspace-card/{CLAUDE.md,AGENTS.md}"
  exit_code=1
elif ! cmp -s "$CARD_CLAUDE_CANONICAL" "$CARD_AGENTS_CANONICAL"; then
  echo "Card: canonical pair DIVERGED — workspace-card/CLAUDE.md and workspace-card/AGENTS.md must be byte-identical"
  exit_code=1
elif [ ! -f "$CARD_CLAUDE_DEPLOYED" ] || [ ! -f "$CARD_AGENTS_DEPLOYED" ]; then
  echo "Card: not deployed to the workspace root — cp workspace-card/{CLAUDE.md,AGENTS.md} to the root"
  exit_code=1
elif cmp -s "$CARD_CLAUDE_CANONICAL" "$CARD_CLAUDE_DEPLOYED" && cmp -s "$CARD_AGENTS_CANONICAL" "$CARD_AGENTS_DEPLOYED"; then
  echo "Card: deployed copy matches canonical"
else
  echo "Card: DRIFT — a root copy differs from workspace-card/{CLAUDE.md,AGENTS.md}; redeploy, or promote the root edit into the canonical pair first"
  exit_code=1
fi

# --- Twin entry-file check ---
# Ported from the seat's harness-selfcheck.sh (owner instruction 2026-08-06,
# stated unconditionally): CLAUDE.md and AGENTS.md are twins. A master hosted
# by codex reads AGENTS.md; a diverged twin boots that master with a different
# card than the one CLAUDE.md carries. Paths through the same CARD_* variables
# the check above already resolved, plus this repository's own entry files —
# a pair the Card: check above never looks at, since it only compares the
# canonical pair against the deployed one.
#
# A function, not inline code, for the same reason as template_adoption_probe
# above: a test can call it directly with CARD_* and OPS_DIR overridden,
# instead of running the whole script.
twins_probe() {
  local fail=0
  if [ ! -f "$CARD_CLAUDE_CANONICAL" ] || [ ! -f "$CARD_AGENTS_CANONICAL" ]; then
    echo "Twins: canonical pair missing at workspace-card/{CLAUDE.md,AGENTS.md} — a codex master would boot with no card"
    fail=1
  elif ! cmp -s "$CARD_CLAUDE_CANONICAL" "$CARD_AGENTS_CANONICAL"; then
    echo "Twins: canonical pair DIVERGED — workspace-card/CLAUDE.md and workspace-card/AGENTS.md must be byte-identical"
    fail=1
  fi
  if [ ! -f "$CARD_AGENTS_DEPLOYED" ]; then
    echo "Twins: AGENTS.md not deployed to the workspace root — cp workspace-card/AGENTS.md to $CARD_AGENTS_DEPLOYED"
    fail=1
  elif [ -f "$CARD_AGENTS_CANONICAL" ] && ! cmp -s "$CARD_AGENTS_CANONICAL" "$CARD_AGENTS_DEPLOYED"; then
    echo "Twins: deployed AGENTS.md differs from canonical; redeploy, or promote the root edit first"
    fail=1
  fi
  if [ -f "$OPS_DIR/CLAUDE.md" ] && [ -f "$OPS_DIR/AGENTS.md" ]; then
    cmp -s "$OPS_DIR/CLAUDE.md" "$OPS_DIR/AGENTS.md" || {
      echo "Twins: this repository's own CLAUDE.md and AGENTS.md diverged"
      fail=1
    }
  else
    echo "Twins: this repository is missing one of its own entry files"
    fail=1
  fi
  if [ "$fail" = 0 ]; then
    echo "Twins: canonical, deployed, and ops entry pairs all byte-identical"
  fi
  return "$fail"
}

twins_probe || exit_code=1

# --- Tracker check ---
# Resolve candidates and compare real paths; substring name matches can accept a
# sibling directory that merely contains the same repository-name fragment.
cd "$WORKSPACE_ROOT" || exit 2
tracker_out=$(bd where 2>&1)
allowed_beads_1=""
allowed_beads_2=""
if [ -d "$OPS_DIR/.beads" ]; then
  allowed_beads_1=$(cd "$OPS_DIR/.beads" 2>/dev/null && pwd -P)
fi
if [ -n "$OPS_REPO" ] && [ "$OPS_REPO" != "{""{OPS_REPO}}" ] && [ -d "$OPS_REPO/.beads" ]; then
  allowed_beads_2=$(cd "$OPS_REPO/.beads" 2>/dev/null && pwd -P)
fi
tracker_ok=0
tracker_candidate_from_line() {
  local tracker_candidate="$1"
  # Preserve a real directory verbatim, including any colon in its path.
  if [ ! -d "$tracker_candidate" ]; then
    case "$tracker_candidate" in
      *:[[:space:]]*) tracker_candidate="${tracker_candidate#*:}" ;;
    esac
  fi
  tracker_candidate="${tracker_candidate#${tracker_candidate%%[![:space:]]*}}"
  tracker_candidate="${tracker_candidate%${tracker_candidate##*[![:space:]]}}"
  printf '%s\n' "$tracker_candidate"
}
# bd where first line is usually the beads path; accept if it realpaths to ops.
tracker_path=$(printf '%s\n' "$tracker_out" | head -1 | tr -d '\r')
if [ -n "$tracker_path" ] && [ -e "$tracker_path" ]; then
  tracker_real=$(cd "$tracker_path" 2>/dev/null && pwd -P || true)
  if [ -n "$tracker_real" ] && { [ "$tracker_real" = "$allowed_beads_1" ] || [ "$tracker_real" = "$allowed_beads_2" ]; }; then
    tracker_ok=1
  fi
fi
if [ "$tracker_ok" -ne 1 ]; then
  while IFS= read -r tracker_line; do
    # Some bd hosts prefix the path with a label. Accept only the path portion
    # and verify its real location; never infer identity from a name fragment.
    tracker_candidate=$(tracker_candidate_from_line "$tracker_line")
    if [ -d "$tracker_candidate" ]; then
      tracker_real=$(cd "$tracker_candidate" 2>/dev/null && pwd -P || true)
      if [ -n "$tracker_real" ] && { [ "$tracker_real" = "$allowed_beads_1" ] || [ "$tracker_real" = "$allowed_beads_2" ]; }; then
        tracker_ok=1
        break
      fi
    fi
  done <<< "$tracker_out"
fi
if [ "$tracker_ok" -eq 1 ]; then
  echo "Tracker: resolves to ops .beads"
else
  echo "Tracker: does not resolve to ops repo"
  exit_code=1
fi

if [ -n "$BEADS_DIR" ]; then
  beads_real=$(cd "$BEADS_DIR" 2>/dev/null && pwd -P || true)
  if [ -z "$beads_real" ] || { [ "$beads_real" != "$allowed_beads_1" ] && [ "$beads_real" != "$allowed_beads_2" ]; }; then
    echo "Tracker: BEADS_DIR points outside ops repo: $BEADS_DIR"
    exit_code=1
  fi
fi

# --- Infra: required-tool checks (ctx, code-review-graph; #317 stage 1) ---
# Four tools are required infra for this workspace (owner direction
# 2026-11-16, #317): Orca and beads already have dedicated checks above
# (Orca:, Tracker:); kept as they are. ctx and code-review-graph get one
# `Infra:` line each here. Unlike every check above, a gap here only warns
# and never touches exit_code: this is stage 1, measure-and-warn only,
# wiring either tool in by default is a later stage.
# $1 = bound in seconds, $@ = the command. Prefers the `timeout`/`gtimeout`
# coreutils binary; macOS ships neither by default (measured on GitHub
# Actions' macos-latest runner: "timeout: command not found"), so this falls
# back to a plain-bash watchdog in that case. The watchdog's own stdio is
# redirected to /dev/null: without that, a watchdog killed after the command
# already finished stays an orphaned `sleep` that still holds the caller's
# command-substitution pipe open, so even a fast command would block the
# caller for the full bound. SIGTERM is escalated to SIGKILL after a 1s grace
# period for a command that ignores or handles the first signal. This only
# reaches the direct child, not a subprocess it forks of its own — a bound
# command that spawns a long-lived grandchild can still hold the pipe open
# past the bound; none of the tools this function calls do that today.
infra_with_timeout() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
    return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
    return $?
  fi
  "$@" &
  local cmd_pid=$!
  (
    sleep "$secs"
    kill -TERM "$cmd_pid" 2>/dev/null
    sleep 1
    kill -KILL "$cmd_pid" 2>/dev/null
  ) </dev/null >/dev/null 2>&1 &
  local watchdog_pid=$!
  wait "$cmd_pid"
  local rc=$?
  kill "$watchdog_pid" 2>/dev/null
  wait "$watchdog_pid" 2>/dev/null
  return "$rc"
}

# $1 = output var name, $2 = exit-code var name, remaining = the command.
# Runs it and sets both variables in the caller, without the usual
# `var=$(cmd)` problem of losing the real exit code to `set -e` (a bare
# failing assignment aborts the script before `$?` can be read) or to a
# negated `if ! var=$(cmd); then` (inside that branch `$?` reflects the
# `if`, not `cmd` -- measured empirically while writing this). The exit
# code travels inside the captured text itself, as a trailing
# "\n<code>" that the final `printf` always succeeds in writing, so the
# substitution's own status is always 0 and the assignment never aborts;
# split back out here.
infra_capture() {
  local __out_var="$1" __rc_var="$2"
  shift 2
  local combined
  combined=$("$@" 2>&1; printf '\n%s' "$?")
  printf -v "$__out_var" '%s' "${combined%$'\n'*}"
  printf -v "$__rc_var" '%s' "${combined##*$'\n'}"
}

INFRA_TIMEOUT_SECONDS="${INFRA_TIMEOUT_SECONDS:-10}"
CODE_REVIEW_GRAPH_STALE_DAYS="${CODE_REVIEW_GRAPH_STALE_DAYS:-7}"
CODE_REVIEW_GRAPH_REGISTRY="${CODE_REVIEW_GRAPH_REGISTRY:-$HOME/.code-review-graph/registry.json}"
MCP_SERVERS_CONFIG="${MCP_SERVERS_CONFIG:-$OPS_DIR/templates/mcp-servers.json}"
CLAUDE_MCP_CONFIG="${CLAUDE_MCP_CONFIG:-${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json}"
CLAUDE_USER_SETTINGS="${CLAUDE_USER_SETTINGS:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json}"
CODEX_MCP_CONFIG="${CODEX_MCP_CONFIG:-${CODEX_HOME:-$HOME/.codex}/config.toml}"

# This seat's own host runtime (#328 follow-up, owner postmortem: an
# `Infra: code-review-graph OK ... registered` line printed on a
# Claude-hosted seat whose Claude config had no such server, because the
# check accepted a Codex-only registration as good enough regardless of
# which host is actually running it). Same resolution order `scripts/dispatch`
# already uses for `MASTER_HOST_RUNTIME` (`MOGUI_MASTER_HOST_RUNTIME` env
# override, then `master_host_runtime` in the instance runtime config), minus
# dispatch's own hardcoded fallback: an unmeasurable host must warn here
# (every check below), never guess one and risk a false OK.
# MOGUI_INSTANCE_RUNTIME_CONFIG matches the override name `scripts/dispatch`
# already reads for this same file; INSTANCE_RUNTIME_CONFIG stays as a
# compatibility alias for a caller that set that instead.
INSTANCE_RUNTIME_CONFIG="${MOGUI_INSTANCE_RUNTIME_CONFIG:-${INSTANCE_RUNTIME_CONFIG:-$OPS_DIR/config/instance-runtime.json}}"
measured_master_host_runtime() {
  [ -f "$INSTANCE_RUNTIME_CONFIG" ] || return 1
  # Path passed as argv, not interpolated into the python source string: a
  # path containing a single quote would otherwise break the script with a
  # syntax error, read here as an unmeasurable host.
  python3 - "$INSTANCE_RUNTIME_CONFIG" <<'EOFHOST' 2>/dev/null
import json, sys
try:
    v = json.load(open(sys.argv[1])).get("master_host_runtime") or ""
except Exception:
    v = ""
print(v)
sys.exit(0 if v else 1)
EOFHOST
}
if [ -n "${MOGUI_MASTER_HOST_RUNTIME:-}" ]; then
  MASTER_HOST_RUNTIME="$MOGUI_MASTER_HOST_RUNTIME"
elif MASTER_HOST_RUNTIME=$(measured_master_host_runtime); then
  :
else
  MASTER_HOST_RUNTIME=""
fi

# $1 = tool name. Returns 0 when Codex's config.toml names it with an
# active entry, 1 otherwise (absent, or present with `enabled = false`).
# Parses with `tomllib` when the running Python is 3.11+; a host still on
# an older Python (this template's own gate notes one such case) falls
# back to a line scan that covers both the bare `[mcp_servers.<tool>]`
# header and the quoted `[mcp_servers."<tool>"]` form, since a bare table
# key cannot contain a `.` as part of the tool name itself without TOML
# requiring the quoted form.
codex_mcp_reachable() {
  local tool="$1"
  [ -f "$CODEX_MCP_CONFIG" ] || return 1
  TOOL="$tool" CONFIG="$CODEX_MCP_CONFIG" python3 << 'EOFCODEX'
import os, re, sys

tool = os.environ["TOOL"]
config_path = os.environ["CONFIG"]

try:
    text = open(config_path, encoding="utf-8").read()
except Exception:
    sys.exit(1)


def via_tomllib():
    try:
        import tomllib
    except ImportError:
        return None
    try:
        data = tomllib.loads(text)
    except Exception:
        return None
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict) or tool not in servers:
        return False
    entry = servers[tool]
    if isinstance(entry, dict) and entry.get("enabled") is False:
        return False
    return True


def via_text_scan():
    quoted = "(?:" + re.escape(tool) + "|\"" + re.escape(tool) + "\"|'" + re.escape(tool) + "')"
    header_re = re.compile(r'^[ \t]*\[mcp_servers\.' + quoted + r'\][ \t]*$')
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not header_re.match(line):
            continue
        for cont in lines[i + 1:]:
            if re.match(r'^[ \t]*\[', cont):
                return True
            if re.match(r'^[ \t]*enabled[ \t]*=[ \t]*false\b', cont):
                return False
        return True
    return False


result = via_tomllib()
if result is None:
    result = via_text_scan()
sys.exit(0 if result else 1)
EOFCODEX
}

# $1 = tool name. Echoes nothing and returns 0 when reachable; echoes one
# reason line and returns 1 when not. Claude: a user-scope or local-scope
# server (the top-level `mcpServers`, or `projects[<path>].mcpServers` for
# WORKSPACE_ROOT/OPS_DIR, both in the file CLAUDE_CONFIG_DIR points an Orca
# profile's Claude CLI at) is always reachable; a project-scope server
# listed in `.mcp.json` additionally needs `enableAllProjectMcpServers` or
# `enabledMcpjsonServers` in some settings file the session reads, and is
# rejected if any settings file (user, project, or project-local) lists it
# in `disabledMcpjsonServers` -- a disabled entry wins regardless of which
# file sets it (coordinator addendum 2026-11-16, peer measurement: a server
# present in .mcp.json was still invisible to Claude master sessions because
# of exactly this). Codex: `codex_mcp_reachable` above.
#
# #328 follow-up (owner direction): registration is judged for the host
# actually running this check, resolved into MASTER_HOST_RUNTIME above.
# `claude`/`codex` each require their OWN registration; a registration on
# the OTHER host is named and still a gap, not a pass -- this check used to
# accept either host's registration regardless of which one is running it,
# which is exactly the false `OK` the owner measured on a Claude-hosted seat
# whose only registration was Codex's. An unmeasurable host (neither the env
# override nor the instance config names one) can never return 0 either:
# it names both sides it did find reachable, if any, so this stays a WARN,
# never a guessed OK.
infra_mcp_status() {
  local tool="$1" status claude_reason="" claude_ok=0
  if status=$(TOOL="$tool" \
    CLAUDE_MCP_CONFIG="$CLAUDE_MCP_CONFIG" \
    CLAUDE_PROJECT_PATHS="$WORKSPACE_ROOT:$OPS_DIR" \
    CLAUDE_PROJECT_MCP_FILES="$WORKSPACE_ROOT/.mcp.json:$OPS_DIR/.mcp.json" \
    CLAUDE_SETTINGS_FILES="$CLAUDE_USER_SETTINGS:$WORKSPACE_ROOT/.claude/settings.json:$WORKSPACE_ROOT/.claude/settings.local.json:$OPS_DIR/.claude/settings.json:$OPS_DIR/.claude/settings.local.json" \
    python3 << 'EOFMCP'
import json, os


def load_json(path):
    if not path:
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


tool = os.environ["TOOL"]

user_cfg = load_json(os.environ.get("CLAUDE_MCP_CONFIG")) or {}
if tool in (user_cfg.get("mcpServers") or {}):
    print("reachable:user-scope")
    raise SystemExit

# Local-scope servers (`claude mcp add -s local`) live under
# projects[<project path>].mcpServers in the same file, keyed by the
# project's own path -- distinct from the top-level mcpServers checked
# above (user scope) and from a project's own .mcp.json (project scope,
# checked below).
projects = user_cfg.get("projects") or {}
if not isinstance(projects, dict):
    projects = {}
for project_path in os.environ.get("CLAUDE_PROJECT_PATHS", "").split(":"):
    if not project_path:
        continue
    project_cfg = projects.get(project_path) or {}
    if tool in (project_cfg.get("mcpServers") or {}):
        print("reachable:local-scope")
        raise SystemExit

project_source = None
for path in os.environ.get("CLAUDE_PROJECT_MCP_FILES", "").split(":"):
    data = load_json(path)
    if data and tool in (data.get("mcpServers") or {}):
        project_source = path
        break

if project_source is None:
    print("absent")
    raise SystemExit

disabled_in = None
enabled_names = set()
enable_all = False
for path in os.environ.get("CLAUDE_SETTINGS_FILES", "").split(":"):
    data = load_json(path)
    if not data:
        continue
    if tool in (data.get("disabledMcpjsonServers") or []) and disabled_in is None:
        disabled_in = path
    enabled_names.update(data.get("enabledMcpjsonServers") or [])
    if "enableAllProjectMcpServers" in data:
        enable_all = bool(data["enableAllProjectMcpServers"])

if disabled_in:
    print(f"disabled:{disabled_in}")
elif enable_all or tool in enabled_names:
    print(f"reachable:project-scope:{project_source}")
else:
    print(f"pending:{project_source}")
EOFMCP
  ); then
    case "$status" in
      reachable:*)
        claude_ok=1
        ;;
      disabled:*)
        claude_reason="disabled via ${status#disabled:}"
        ;;
      pending:*)
        claude_reason="listed in ${status#pending:} but not approved (enableAllProjectMcpServers/enabledMcpjsonServers unset in every settings file read)"
        ;;
    esac
  fi
  local codex_ok=0
  codex_mcp_reachable "$tool" && codex_ok=1
  # Host-neutral: never the claude-specific disabled/pending detail above,
  # which only describes a Claude-side gap and would misdirect an operator
  # on a Codex-hosted (or unmeasured-host) seat whose own gap is different.
  local generic_absent="not registered as an MCP server (checked Claude user config, project .mcp.json, Codex config.toml)"

  case "$MASTER_HOST_RUNTIME" in
    claude)
      [ "$claude_ok" = 1 ] && return 0
      if [ "$codex_ok" = 1 ]; then
        echo "registered for codex, not claude (this session measured its host as claude)"
      else
        echo "${claude_reason:-$generic_absent}"
      fi
      ;;
    codex)
      [ "$codex_ok" = 1 ] && return 0
      if [ "$claude_ok" = 1 ]; then
        echo "registered for claude, not codex (this session measured its host as codex)"
      else
        echo "not registered in Codex config.toml"
      fi
      ;;
    "")
      if [ "$claude_ok" = 1 ] || [ "$codex_ok" = 1 ]; then
        local found=""
        [ "$claude_ok" = 1 ] && found="claude"
        [ "$codex_ok" = 1 ] && found="${found:+$found, }codex"
        echo "registered for $found, but this session's own host is unmeasurable (set MOGUI_MASTER_HOST_RUNTIME or master_host_runtime in $INSTANCE_RUNTIME_CONFIG) so that registration cannot be confirmed as this host's own"
      else
        echo "$generic_absent; this session's host is also unmeasurable (set MOGUI_MASTER_HOST_RUNTIME or master_host_runtime in $INSTANCE_RUNTIME_CONFIG)"
      fi
      ;;
    *)
      # A configured host this check does not model (anything other than
      # claude/codex): never guess which side's registration applies, but
      # do not claim the host is unmeasurable when it plainly is measured.
      if [ "$claude_ok" = 1 ] || [ "$codex_ok" = 1 ]; then
        local found=""
        [ "$claude_ok" = 1 ] && found="claude"
        [ "$codex_ok" = 1 ] && found="${found:+$found, }codex"
        echo "registered for $found, but this check only judges claude/codex registration and this session's host is '$MASTER_HOST_RUNTIME'"
      else
        echo "$generic_absent"
      fi
      ;;
  esac
  return 1
}

# ctx: runs, registered, and indexes every provider Orca reports sessions
# for among claude and codex (owner 2026-11-16: ctx must also cover Orca's
# own agent-session index).
ctx_warn=""
if ! command -v ctx >/dev/null 2>&1; then
  ctx_warn="absent from PATH"
else
  infra_capture ctx_status_json ctx_status_rc infra_with_timeout "$INFRA_TIMEOUT_SECONDS" ctx status --format json
  if [ "$ctx_status_rc" -ne 0 ]; then
    case "$ctx_status_rc" in
      124 | 137 | 143)
        ctx_warn="timed out after ${INFRA_TIMEOUT_SECONDS}s"
        ;;
      *)
        ctx_warn=$(printf '%s\n' "$ctx_status_json" | head -1)
        [ -n "$ctx_warn" ] || ctx_warn="ctx status failed with no output"
        ;;
    esac
  elif ! ctx_mcp_reason=$(infra_mcp_status ctx); then
    ctx_warn="runs, but $ctx_mcp_reason"
  else
    orca_status_json=$(infra_with_timeout "$INFRA_TIMEOUT_SECONDS" orca search --index-status --json 2>&1) || orca_status_json=""
    ctx_sources_text=$(infra_with_timeout "$INFRA_TIMEOUT_SECONDS" ctx sources 2>&1) || true
    ctx_warn=$(CTX_STATUS="$ctx_status_json" ORCA_STATUS="$orca_status_json" CTX_SOURCES="$ctx_sources_text" python3 << 'EOFCTX'
import json, os

def providers_from_status(raw):
    try:
        data = json.loads(raw)
    except Exception:
        return None
    jobs = ((data.get("daemon") or {}).get("jobs")) or {}
    providers = set()
    for job in jobs.values():
        providers.update((job.get("progress") or {}).get("providers") or [])
    return providers

def sessions_by_agent(raw):
    # None distinguishes "could not tell" from "told us there are none":
    # unparseable JSON, a missing `result`, or a `result` with no
    # `sessionsByAgent` key are all an unmeasurable Orca index, not a
    # measured empty one. A present `sessionsByAgent` is trusted even when
    # it is itself `{}` -- that is Orca legitimately reporting no sessions.
    try:
        data = json.loads(raw)
    except Exception:
        return None
    result = data.get("result")
    if not isinstance(result, dict) or "sessionsByAgent" not in result:
        return None
    sessions = result.get("sessionsByAgent")
    return sessions if isinstance(sessions, dict) else None

def reason_for(provider_label, sources_text):
    lines = sources_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("!") and provider_label.lower() in line.lower():
            for cont in lines[i + 1:]:
                cont = cont.strip()
                if not cont:
                    continue
                if cont.startswith(("Hint", "Next")):
                    return ""
                return cont
    return ""

LABELS = {"claude": "Claude Code", "codex": "Codex"}

providers = providers_from_status(os.environ.get("CTX_STATUS", ""))
sessions = sessions_by_agent(os.environ.get("ORCA_STATUS", ""))
sources_text = os.environ.get("CTX_SOURCES", "")

if providers is None:
    print("undecided (could not parse ctx status --format json)")
elif sessions is None:
    print("undecided (orca search --index-status --json has no result.sessionsByAgent)")
elif not providers:
    print("ctx has indexed no providers")
else:
    missing = []
    for provider in ("claude", "codex"):
        if not sessions.get(provider, 0):
            continue
        if provider not in providers:
            reason = reason_for(LABELS.get(provider, provider), sources_text)
            missing.append(provider + (f" ({reason})" if reason else ""))
    if missing:
        print("does not cover: " + ", ".join(missing))
EOFCTX
    ) || ctx_warn="ctx covering-check failed to run"
  fi
fi
if [ -n "$ctx_warn" ]; then
  echo "Infra: ctx WARN $ctx_warn"
else
  echo "Infra: ctx OK runs, registered, covers every provider Orca reports claude/codex sessions for"
fi

# ctx-upgrade: #328 follow-up, from the #317 seat postmortem -- the root
# cause there was an install stuck on an old ctx with `ctx upgrade status` in
# `State error` (a past DNS failure fetching release metadata) while a newer
# release had long since closed the very symptoms the `Infra: ctx` check
# above exists to catch. Reads only `ctx upgrade status --format json`
# (never `ctx upgrade check`, which hits the network and can itself apply an
# upgrade under this host's own auto-upgrade mode -- a side effect a bounded,
# read-only self-check must not have). `state.latest_version` is whatever
# release ctx's own background checker last recorded, so this can lag a
# release that shipped after that last check; it is still the only
# network-free signal available here. Compares current_version against it
# numerically (dotted integers), not as strings, so "2.10.0" reads as newer
# than "2.9.0".
ctx_upgrade_warn=""
if ! command -v ctx >/dev/null 2>&1; then
  ctx_upgrade_warn="absent from PATH"
else
  infra_capture ctx_upgrade_status_json ctx_upgrade_status_rc infra_with_timeout "$INFRA_TIMEOUT_SECONDS" ctx upgrade status --format json
  if [ "$ctx_upgrade_status_rc" -ne 0 ]; then
    case "$ctx_upgrade_status_rc" in
      124 | 137 | 143)
        ctx_upgrade_warn="timed out after ${INFRA_TIMEOUT_SECONDS}s"
        ;;
      *)
        ctx_upgrade_warn=$(printf '%s\n' "$ctx_upgrade_status_json" | head -1)
        [ -n "$ctx_upgrade_warn" ] || ctx_upgrade_warn="ctx upgrade status failed with no output"
        ;;
    esac
  else
    ctx_upgrade_warn=$(CTX_UPGRADE_STATUS="$ctx_upgrade_status_json" python3 << 'EOFCTXUP'
import json, os, sys

try:
    data = json.loads(os.environ["CTX_UPGRADE_STATUS"])
except Exception as exc:
    print(f"could not parse ctx upgrade status --format json output ({exc})")
    raise SystemExit

state = data.get("state") if isinstance(data.get("state"), dict) else {}
status = state.get("status")
current = data.get("current_version") or state.get("current_version")
latest = state.get("latest_version")

if status == "error":
    print(f"ctx upgrade status reports State error (current {current or 'unknown'})")
    raise SystemExit

if not current or not latest:
    print(f"ctx upgrade status has no current_version/latest_version to compare (status={status!r})")
    raise SystemExit

def version_tuple(v):
    parts = []
    for p in str(v).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            return None
    return tuple(parts) if parts else None

current_t, latest_t = version_tuple(current), version_tuple(latest)
if current_t is None or latest_t is None:
    print(f"could not compare ctx versions current={current!r} latest={latest!r}")
elif current_t < latest_t:
    print(f"ctx {current} is behind {latest} (the latest version ctx last recorded; run 'ctx upgrade check')")
EOFCTXUP
) || ctx_upgrade_warn="ctx upgrade state check failed to run"
  fi
fi
if [ -n "$ctx_upgrade_warn" ]; then
  echo "Infra: ctx-upgrade WARN $ctx_upgrade_warn"
else
  echo "Infra: ctx-upgrade OK up to date"
fi

# code-review-graph: runs, registered, and every repo in its multi-repo
# registry (~/.code-review-graph/registry.json) has a graph no older than
# CODE_REVIEW_GRAPH_STALE_DAYS. Reads the registry and each repo's
# .code-review-graph/graph.db mtime directly rather than through the CLI,
# which needs a per-repo cwd to report status, and which the Runs: check
# just above may already have found broken.
#
# "Runs" probes the pinned launcher from MCP_SERVERS_CONFIG
# (templates/mcp-servers.json), not a bare `code-review-graph` on PATH:
# every session now launches it as `uvx code-review-graph@<pin> serve`
# (#317 stage 2), and a host with uvx on PATH but no code-review-graph
# shim installed globally -- the common case, and the one a correctly
# wired install actually runs in -- warned forever here before this fix.
# The entry's args[0] is the pinned package spec (e.g.
# "code-review-graph@2.4.0"); the version probe passes that spec plus
# --version to the same launcher command instead of args' own trailing
# "serve", so it measures the exact binary and pin the worker launches use
# (a master session's own .mcp.json entry is only checked by name, in
# infra_mcp_status below, not probed here).
crg_warn=""
crg_launcher_cmd=""
crg_launcher_spec=""
crg_parse_out=$(python3 - "$MCP_SERVERS_CONFIG" <<'PYEOF'
import json, sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    print(f"MCP_SERVERS_CONFIG_ERROR:could not read {path}: {exc}")
    sys.exit(0)

servers = data.get("mcpServers") if isinstance(data, dict) else None
if not isinstance(servers, dict):
    print(f"MCP_SERVERS_CONFIG_ERROR:mcpServers in {path} is not an object")
    sys.exit(0)

entry = servers.get("code-review-graph")
if not isinstance(entry, dict):
    print(f"MCP_SERVERS_CONFIG_ERROR:no code-review-graph entry in {path}")
    sys.exit(0)

command = entry.get("command")
args = entry.get("args")
if (
    not isinstance(command, str) or not command
    or not isinstance(args, list) or not args
    or not isinstance(args[0], str) or not args[0]
):
    print(f"MCP_SERVERS_CONFIG_ERROR:code-review-graph entry in {path} has no valid command/args")
    sys.exit(0)

print(f"{command}\t{args[0]}")
PYEOF
) || crg_warn="could not parse $MCP_SERVERS_CONFIG"
if [ -z "$crg_warn" ]; then
  case "$crg_parse_out" in
    MCP_SERVERS_CONFIG_ERROR:*) crg_warn="${crg_parse_out#MCP_SERVERS_CONFIG_ERROR:}" ;;
    *) crg_launcher_cmd="${crg_parse_out%%$'\t'*}"; crg_launcher_spec="${crg_parse_out#*$'\t'}" ;;
  esac
fi
if [ -z "$crg_warn" ] && ! command -v "$crg_launcher_cmd" >/dev/null 2>&1; then
  crg_warn="launcher '$crg_launcher_cmd' absent from PATH"
fi
if [ -z "$crg_warn" ]; then
  infra_capture crg_version_out crg_version_rc infra_with_timeout "$INFRA_TIMEOUT_SECONDS" "$crg_launcher_cmd" "$crg_launcher_spec" --version
  if [ "$crg_version_rc" -ne 0 ]; then
    case "$crg_version_rc" in
      124 | 137 | 143)
        # #328 follow-up: this launcher is almost always uvx, and a cold uv
        # cache makes its first run download the package and write that
        # cache -- real filesystem writes a "read-only check" otherwise
        # claims not to make, and real network time that can outrun this
        # bound on a slow link even though the command would have succeeded.
        # Name that as the likely cause rather than a bare "timed out".
        crg_warn="timed out after ${INFRA_TIMEOUT_SECONDS}s (likely cause: a first run of '$crg_launcher_cmd $crg_launcher_spec' downloads the package and populates its cache on a cold host/network; rerun once that cache is warm)"
        ;;
      *)
        crg_warn=$(printf '%s\n' "$crg_version_out" | head -1)
        [ -n "$crg_warn" ] || crg_warn="$crg_launcher_cmd $crg_launcher_spec --version failed with no output"
        ;;
    esac
  elif ! crg_mcp_reason=$(infra_mcp_status code-review-graph); then
    crg_warn="runs, but $crg_mcp_reason"
  elif [ ! -f "$CODE_REVIEW_GRAPH_REGISTRY" ]; then
    crg_warn="runs and registered, but no multi-repo registry at $CODE_REVIEW_GRAPH_REGISTRY"
  else
    crg_warn=$(CODE_REVIEW_GRAPH_REGISTRY="$CODE_REVIEW_GRAPH_REGISTRY" CODE_REVIEW_GRAPH_STALE_DAYS="$CODE_REVIEW_GRAPH_STALE_DAYS" python3 << 'EOFCRG'
import json, math, os, time

def main():
    registry_path = os.environ["CODE_REVIEW_GRAPH_REGISTRY"]
    raw_threshold = os.environ["CODE_REVIEW_GRAPH_STALE_DAYS"]
    threshold_days = 7.0
    parts = []
    try:
        parsed = float(raw_threshold)
    except ValueError:
        parsed = None
    if parsed is None or not math.isfinite(parsed) or parsed <= 0:
        parts.append(
            f"CODE_REVIEW_GRAPH_STALE_DAYS={raw_threshold!r} must be a positive, finite number; using default 7"
        )
    else:
        threshold_days = parsed

    try:
        repos = json.load(open(registry_path)).get("repos") or []
    except Exception as exc:
        parts.append(f"registry unreadable ({exc})")
        print("; ".join(parts))
        return

    if not repos:
        parts.append("no repository registered")
        print("; ".join(parts))
        return

    missing_paths = []
    stale = []
    for repo in repos:
        if not isinstance(repo, dict):
            missing_paths.append("invalid registry entry")
            continue
        path = repo.get("path") or ""
        alias = repo.get("alias") or path or "?"
        if not path or not os.path.isdir(path):
            missing_paths.append(alias)
            continue
        graph_db = os.path.join(path, ".code-review-graph", "graph.db")
        try:
            mtime = os.path.getmtime(graph_db)
        except OSError:
            missing_paths.append(alias)
            continue
        age_days = (time.time() - mtime) / 86400
        if age_days > threshold_days:
            stale.append(f"{alias} ({age_days:.0f}d)")

    if stale:
        parts.append("stale: " + ", ".join(stale))
    if missing_paths:
        parts.append("missing path: " + ", ".join(missing_paths))
    print("; ".join(parts))

try:
    main()
except Exception as exc:
    print(f"registry check failed ({exc})")
EOFCRG
    ) || crg_warn="registry check failed to run"
  fi
fi
if [ -n "$crg_warn" ]; then
  echo "Infra: code-review-graph WARN $crg_warn"
else
  echo "Infra: code-review-graph OK runs, registered, every registered repo's graph fresh (<= ${CODE_REVIEW_GRAPH_STALE_DAYS}d)"
fi

# --- Template currency check ---
# Attachment point for Upgrade mode: runs at every master boot. Apply stays in
# onboarding/upgrade.md and scripts/template-apply. Nonzero from this block is
# intentional boot gating (pre-manifest and shape-broken installs fail open
# awareness), not a silent report line.

# Turns a template-check JSON report + its exit code into the boot-time
# "Template:" line. Isolated as a function (like template_adoption_probe and
# twins_probe above) so a test can feed it a synthetic report instead of
# standing up a real ops install. Uses env: TEMPLATE_JSON, TEMPLATE_RC.
# unknown_present is reported but never turns this line into a failing one —
# installs add files by design; drift the template cares about is a required
# file missing, not a file the install wrote. A retired path (declared in the
# install's own config/template-retirements.json) is likewise not absence.
format_template_currency_line() {
  python3 - <<'EOF'
import json, os
data = json.loads(os.environ["TEMPLATE_JSON"])
rc = int(os.environ["TEMPLATE_RC"])
ver = data.get("installed_version") or "undeterminable"
absent = len(data.get("absent_required") or [])
retired = len(data.get("retired") or [])
unknown = len(data.get("unknown_present") or [])
status = data.get("manifest_status") or "?"
report_set = data.get("report_set") or "?"
tver = data.get("template_version")
retirements_status = data.get("retirements_status") or "ok"
if status == "absent":
    print("Template: no MANIFEST.json (run Upgrade mode; pre-manifest install)")
    raise SystemExit(1)
if retirements_status == "malformed":
    print(f"Template: {ver} (manifest={status}, retirements=malformed) — run Upgrade mode")
    raise SystemExit(1)
if rc == 0 and status == "ok" and absent == 0:
    suffix = f", {retired} retired" if retired else ""
    if report_set == "template-compare" and tver:
        print(f"Template: {ver} (matches template {tver}{suffix})")
    else:
        print(f"Template: {ver} (installed-manifest shape ok; no template path for currency compare{suffix})")
    raise SystemExit(0)
extra = f", template={tver}" if tver else ""
print(f"Template: {ver} (manifest={status}, absent={absent}, retired={retired}, unknown={unknown}{extra}) — run Upgrade mode")
raise SystemExit(1)
EOF
}

if [ -x "$TEMPLATE_CHECK" ]; then
  template_args=(--ops "$OPS_DIR" --json)
  # Prefer template-compare when a live ADE skeleton is measurable.
  # Skeleton dir name built in parts so this installed script stays frame-clean.
  skeleton_dir="master"$'-'"ops"
  if [ -n "${RUNTIME_ROOT:-}" ] && [ -f "$RUNTIME_ROOT/$skeleton_dir/MANIFEST.json" ]; then
    template_args+=(--template "$RUNTIME_ROOT/$skeleton_dir")
  fi
  template_json=$("$TEMPLATE_CHECK" "${template_args[@]}" 2>/dev/null) || template_rc=$?
  template_rc=${template_rc:-0}
  if [ -z "$template_json" ]; then
    echo "Template: undecided (template-check produced no report)"
    exit_code=1
  else
    # format_template_currency_line raises SystemExit(1) on most reporting
    # branches to make its own return code testable (see the mutant tests in
    # test-template-currency-line.sh). Under `set -e`, a bare assignment would
    # abort this whole script before the line below ever prints — the
    # existing template_rc (from the real template-check invocation above)
    # stays the sole arbiter of exit_code, so the substitution's own status is
    # deliberately discarded here.
    template_line=$(TEMPLATE_JSON="$template_json" TEMPLATE_RC="$template_rc" format_template_currency_line) || true
    echo "$template_line"
    if [ "$template_rc" -ne 0 ]; then
      exit_code=1
    fi
  fi
else
  echo "Template: undecided (scripts/template-check missing or not executable)"
  exit_code=1
fi

exit "$exit_code"
