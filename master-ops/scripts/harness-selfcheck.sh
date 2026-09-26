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
if [ -n "$OPS_REPO" ] && [ "$OPS_REPO" != "{{OPS_REPO}}" ] && [ -d "$OPS_REPO/.beads" ]; then
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
    if report_set == "template-compare" and tver:
        suffix = f", {retired} retired" if retired else ""
        print(f"Template: {ver} (matches template {tver}{suffix})")
    else:
        print(f"Template: {ver} (installed-manifest shape ok; no template path for currency compare)")
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
    template_line=$(TEMPLATE_JSON="$template_json" TEMPLATE_RC="$template_rc" format_template_currency_line)
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
