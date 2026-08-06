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
# Basename of the ops repository path — used only for tracker resolution strings.
OPS_BASENAME="$(basename "$OPS_REPO")"
if [ "$OPS_BASENAME" = "{{OPS_REPO}}" ] || [ -z "$OPS_BASENAME" ]; then
  OPS_BASENAME="$(basename "$OPS_DIR")"
fi
SETTINGS_FILE="$WORKSPACE_ROOT/.claude/settings.json"
SKILLS_DISCOVERY_PATH="$WORKSPACE_ROOT/.claude/skills"
HOOKS_REPO_DIR="$OPS_DIR/scripts/hooks"
TEMPLATE_CHECK="$OPS_DIR/scripts/template-check"

exit_code=0

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
    ((skill_reachable++))
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

for cmd in $wired_hooks; do
  # Extract the script path (usually word containing .sh extension)
  script_path=$(echo "$cmd" | tr ' ' '\n' | grep -E '\.sh$' | head -1)

  if [ -n "$script_path" ]; then
    if [ -f "$script_path" ] && [ -x "$script_path" ]; then
      ((hook_wired++))
    else
      hook_missing="$hook_missing $(basename "$script_path")"
      exit_code=1
    fi
  fi
done

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

# --- Tracker check ---
# Reuse the logic from scripts/hooks/tracker-check.sh
cd "$WORKSPACE_ROOT" || exit 2
tracker_out=$(bd where 2>&1)
case "$tracker_out" in
  *"$OPS_BASENAME"/.beads*) echo "Tracker: resolves to $OPS_BASENAME/.beads" ;;
  *)
    echo "Tracker: does not resolve to ops repo"
    exit_code=1
    ;;
esac

if [ -n "$BEADS_DIR" ] && [ "$BEADS_DIR" != "$OPS_REPO/.beads" ] && [ "$BEADS_DIR" != "$OPS_DIR/.beads" ]; then
  if ! echo "$BEADS_DIR" | grep -Fq -- "$OPS_BASENAME/.beads"; then
    echo "Tracker: BEADS_DIR points outside ops repo: $BEADS_DIR"
    exit_code=1
  fi
fi

# --- Template currency check ---
# Attachment point for Upgrade mode: runs at every master boot so nobody has to
# remember to compare the install to the template. Report-only here; apply is
# owned by onboarding/upgrade.md and scripts/template-apply.
if [ -x "$TEMPLATE_CHECK" ]; then
  template_json=$("$TEMPLATE_CHECK" --ops "$OPS_DIR" --json 2>/dev/null) || template_rc=$?
  template_rc=${template_rc:-0}
  if [ -z "$template_json" ]; then
    echo "Template: undecided (template-check produced no report)"
    exit_code=1
  else
    template_line=$(
      TEMPLATE_JSON="$template_json" TEMPLATE_RC="$template_rc" python3 - <<'EOF'
import json, os
data = json.loads(os.environ["TEMPLATE_JSON"])
rc = int(os.environ["TEMPLATE_RC"])
ver = data.get("installed_version") or "undeterminable"
absent = len(data.get("absent_required") or [])
unknown = len(data.get("unknown_present") or [])
status = data.get("manifest_status") or "?"
if rc == 0 and status == "ok" and absent == 0:
    print(f"Template: {ver} (manifest ok, shape matches)")
elif status == "absent":
    print(f"Template: no MANIFEST.json (run Upgrade mode; absent shape signals a pre-manifest install)")
else:
    print(f"Template: {ver} (manifest={status}, absent={absent}, unknown={unknown}) — run Upgrade mode")
EOF
    )
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
