#!/usr/bin/env bash
# Hook commands must resolve from a worktree cwd after template rendering.
set -u

SOURCE_OPS="$(cd "$(dirname "$0")/.." && pwd)"
ONBOARDING_SOURCE="$SOURCE_OPS/onboarding/08-settings-and-skills.md"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OPS_ROOT="$TMP/ops"
WORKSPACE_ROOT="$TMP/workspace"
WORKTREE="$WORKSPACE_ROOT/.orca/worktrees/worker"
FIRE_LOG="$TMP/hook-fire.jsonl"
STATE_DIR="$TMP/state"
BIN_DIR="$TMP/bin"
SETTINGS="$WORKSPACE_ROOT/.claude/settings.json"
TRACKER="$OPS_ROOT/scripts/hooks/tracker-check.sh"
RUNTIME_CONFIG="$TMP/instance-runtime.json"

ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; return 1; }
tracker_skip_line() { printf '[tracker] SKIP: %s\n' "$1"; }

mkdir -p "$OPS_ROOT" "$WORKTREE" "$WORKSPACE_ROOT/.claude" "$WORKSPACE_ROOT/docs/runbooks" "$STATE_DIR" "$BIN_DIR"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "%s/.beads"\n' "$OPS_ROOT" > "$BIN_DIR/bd"
chmod +x "$BIN_DIR/bd"
cat > "$BIN_DIR/orca" <<'EOFORCA'
#!/usr/bin/env bash
case "$*" in
  "terminal list"|"terminal list --json")
    [ "$*" = "terminal list --json" ] && printf '{"terminals":[]}\n'
    exit 0
    ;;
  "orchestration check --peek --json")
    printf '{"result":{"messages":[]}}\n'
    exit 0
    ;;
  *)
    exit 1
    ;;
esac
EOFORCA
chmod +x "$BIN_DIR/orca"
cp -R "$SOURCE_OPS/scripts" "$OPS_ROOT/"
WORKSPACE_ROOT="$WORKSPACE_ROOT" RUNTIME_CONFIG="$RUNTIME_CONFIG" python3 <<'PY'
import json
import os

json.dump(
    {"product_repositories": [os.environ["WORKSPACE_ROOT"]]},
    open(os.environ["RUNTIME_CONFIG"], "w", encoding="utf-8"),
)
PY
cat > "$WORKSPACE_ROOT/docs/runbooks/role-state.md" <<'EOFROLE'
Current Role: master
Role Lock: ENABLED
Execution rule: Proposal -> Approval -> Execution.
EOFROLE

# Render only the placeholders used by the installed scripts. The copied tree
# stays in a scratch operations repository, so the test exercises installed
# paths without changing the template checkout.
OPS_ROOT="$OPS_ROOT" WORKSPACE_ROOT="$WORKSPACE_ROOT" python3 <<'PY'
import os
from pathlib import Path

root = Path(os.environ["OPS_ROOT"])
values = {
    "{{OPS_REPO}}": str(root),
    "{{WORKSPACE_ROOT}}": os.environ["WORKSPACE_ROOT"],
    "{{RUNTIME_ROOT}}": str(root),
}
for path in root.rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        continue
    raw = path.read_text(encoding="utf-8")
    for token, value in values.items():
        raw = raw.replace(token, value)
    path.write_text(raw, encoding="utf-8")
PY

ONBOARDING_SOURCE="$ONBOARDING_SOURCE" OPS_ROOT="$OPS_ROOT" python3 - "$SETTINGS" <<'PY'
import json
import os
import re
import shlex
import sys
from pathlib import Path

ops = os.environ["OPS_ROOT"]
onboarding = Path(os.environ["ONBOARDING_SOURCE"])
hooks = []
referenced = set()
if onboarding.is_file():
    event = "SessionStart"
    command_re = re.compile(r'"command":\s*"((?:\\.|[^"\\])*)"')
    event_re = re.compile(r'^\s*"([A-Za-z]+)":\s*\[')
    for line in onboarding.read_text(encoding="utf-8").splitlines():
        event_match = event_re.match(line)
        if event_match:
            event = event_match.group(1)
        command_match = command_re.search(line)
        if not command_match:
            continue
        command = json.loads('"' + command_match.group(1) + '"').replace(
            "{{OPS_REPO}}", ops
        )
        script = next(
            (token for token in shlex.split(command) if token.endswith(".sh")),
            None,
        )
        if script is None or not os.path.isfile(script):
            raise SystemExit(f"onboarding command has no installed script: {command}")
        rel = os.path.relpath(script, ops)
        hooks.append((event, rel, command))
        referenced.add(Path(script).resolve())

    hooks_dir = Path(ops) / "scripts" / "hooks"
    shipped = {path.resolve() for path in hooks_dir.glob("*.sh")}
    # The onboarding fragment wires every shipped hook. Keep this explicit list
    # empty unless 08 documents the exclusion and its reason beside the fragment.
    explicit_exclusions = set()
    excluded = {(Path(ops) / rel).resolve() for rel in explicit_exclusions}
    unaccounted = sorted(
        path.relative_to(Path(ops)).as_posix()
        for path in shipped - referenced - excluded
    )
    if unaccounted:
        raise SystemExit(
            "shipped hooks missing from onboarding or exclusion list: "
            + ", ".join(unaccounted)
        )
else:
    # template-apply intentionally omits this authoring-only onboarding file.
    # Derive the rendered-tree fixture from the installed hook files themselves.
    hooks_dir = Path(ops) / "scripts" / "hooks"
    hooks = [
        ("SessionStart", path.relative_to(Path(ops)).as_posix(), None)
        for path in sorted(hooks_dir.glob("*.sh"))
    ]
    if os.path.isfile(os.path.join(ops, "scripts/compaction-probe.sh")):
        hooks.insert(2, ("SessionStart", "scripts/compaction-probe.sh", None))
settings = {"hooks": {}}
for event, name, command in hooks:
    command = command or f'bash "{ops}/{name}"'
    settings["hooks"].setdefault(event, []).append(
        {"matcher": "", "hooks": [{"type": "command", "command": command}]}
    )
json.dump(settings, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
open(sys.argv[1], "a", encoding="utf-8").write("\n")
PY

write_commands() {
  local settings_path="$1" output_path="$2"
  python3 - "$settings_path" > "$output_path" <<'PY'
import json
import sys

settings = json.load(open(sys.argv[1], encoding="utf-8"))
for entries in (settings.get("hooks") or {}).values():
    for entry in entries:
        for hook in entry.get("hooks", []):
            if hook.get("type") == "command" and hook.get("command"):
                print(hook["command"])
PY
}

run_from_worktree() {
  local settings_path="$1" command_file="$TMP/commands.txt" cmd output rc script_path failed=0
  write_commands "$settings_path" "$command_file"
  while IFS= read -r cmd; do
    [ -n "$cmd" ] || continue
    script_path=$(python3 - "$cmd" <<'PY'
import shlex
import sys

for token in shlex.split(sys.argv[1]):
    if token.endswith(".sh"):
        print(token)
        break
PY
    )
    if [ -z "$script_path" ] || ! (cd "$WORKTREE" && [ -f "$script_path" ]); then
      echo "hook script is not present from worktree cwd: $script_path"
      return 1
    fi
    output=$(cd "$WORKTREE" && printf '%s\n' '{"tool_input":{}}' | \
      MOGUI_HOOK_FIRE_LOG="$FIRE_LOG" WORKSPACE_ROOT="$WORKSPACE_ROOT" \
      MOGUI_STATE_DIR="$STATE_DIR" \
      MOGUI_INSTANCE_RUNTIME_CONFIG="$RUNTIME_CONFIG" \
      MOGUI_EVENT_LOG="$STATE_DIR/event-log.jsonl" \
      PATH="$BIN_DIR:$PATH" \
      bash -c "$cmd" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ] || printf '%s\n' "$output" | grep -Eiq 'No such file|not found'; then
      printf '%s\n' "$output" >&2
      failed=1
    fi
  done < "$command_file"
  return "$failed"
}

if run_from_worktree "$SETTINGS"; then
  ok "installed hook commands resolve from a worktree cwd"
else
  fail "an installed hook command did not resolve from a worktree cwd"
  exit 1
fi

if [ -f "$ONBOARDING_SOURCE" ]; then
  if grep -Fq '"hook":"role-state-inject","event":"SessionStart"' "$FIRE_LOG"; then
    ok "SessionStart role-state hook records its explicit event"
  else
    fail "SessionStart role-state hook did not record its explicit event"
    exit 1
  fi
fi

if [ -x "$OPS_ROOT/scripts/harness-selfcheck.sh" ]; then
  harness_output=$(cd "$WORKTREE" && \
    ORCA_WORKSPACE_ID=fixture \
    WORKSPACE_ROOT="$WORKSPACE_ROOT" \
    bash "$OPS_ROOT/scripts/harness-selfcheck.sh" 2>&1 || true)
  if printf '%s\n' "$harness_output" | grep -Eq '^Hooks: [0-9]+ wired$'; then
    ok "harness self-check sees the onboarding-installed hooks from a worktree cwd"
  else
    printf '%s\n' "$harness_output"
    fail "harness self-check did not report a clean installed-hook set"
    exit 1
  fi
fi

root_only_output=$(cd "$WORKTREE" && \
  MOGUI_HOOK_FIRE_LOG="$TMP/root-only-fire.jsonl" \
  WORKSPACE_ROOT="$TMP/missing-workspace-root" \
  bash "$TRACKER" </dev/null 2>&1)
root_only_rc=$?
if [ "$root_only_rc" -eq 0 ] && \
  printf '%s\n' "$root_only_output" | grep -Fxq "$(tracker_skip_line 'WORKSPACE_ROOT is not a directory')" && \
  ! printf '%s\n' "$root_only_output" | grep -q 'Traceback'; then
  ok "missing workspace root prints a directory SKIP and exits 0 from a worktree cwd"
else
  printf '%s\n' "$root_only_output"
  fail "root-only tracker data did not report a clean SKIP"
  exit 1
fi

relative_root_output=$(cd "$WORKTREE" && \
  MOGUI_HOOK_FIRE_LOG="$TMP/relative-root-fire.jsonl" \
  WORKSPACE_ROOT="relative-root" \
  bash "$TRACKER" </dev/null 2>&1)
relative_root_rc=$?
if [ "$relative_root_rc" -eq 0 ] && \
  printf '%s\n' "$relative_root_output" | grep -Fxq "$(tracker_skip_line 'WORKSPACE_ROOT is not absolute')"; then
  ok "relative workspace root prints an absolute-path SKIP"
else
  printf '%s\n' "$relative_root_output"
  fail "relative workspace root did not report an absolute-path SKIP"
  exit 1
fi

default_root_output=$(cd "$WORKTREE" && \
  MOGUI_HOOK_FIRE_LOG="$TMP/default-root-fire.jsonl" \
  MOGUI_SETTINGS_FILE="$SETTINGS" \
  MOGUI_HOOKS_DIR="$OPS_ROOT/scripts/hooks" \
  PATH="$BIN_DIR:$PATH" \
  env -u BEADS_DIR -u WORKSPACE_ROOT bash "$TRACKER" </dev/null 2>&1)
default_root_rc=$?
if [ "$default_root_rc" -eq 0 ] && \
  printf '%s\n' "$default_root_output" | grep -q '^\[protections\]'; then
  ok "unset WORKSPACE_ROOT uses the rendered ROOT_DEFAULT and prints the banner"
else
  printf '%s\n' "$default_root_output"
  fail "unset WORKSPACE_ROOT did not use ROOT_DEFAULT"
  exit 1
fi

mkdir -p "$TMP/mutants"
python3 - "$SETTINGS" "$TMP/mutants" <<'PY'
import json
import os
import sys

source = json.load(open(sys.argv[1], encoding="utf-8"))
out_dir = sys.argv[2]
count = 0
for event, entries in source["hooks"].items():
    for entry_index, entry in enumerate(entries):
        for hook_index, hook in enumerate(entry.get("hooks", [])):
            command = hook.get("command", "")
            if not command:
                continue
            parts = command.split('"', 2)
            if len(parts) < 3 or not parts[1].endswith(".sh"):
                continue
            mutant = json.loads(json.dumps(source))
            mutant_command = mutant["hooks"][event][entry_index]["hooks"][hook_index]["command"]
            absolute = mutant_command.split('"', 2)[1]
            mutant["hooks"][event][entry_index]["hooks"][hook_index]["command"] = mutant_command.replace(
                absolute, "scripts/hooks/" + os.path.basename(absolute), 1
            )
            path = os.path.join(out_dir, f"mutant-{count}.json")
            json.dump(mutant, open(path, "w", encoding="utf-8"), indent=2)
            open(path, "a", encoding="utf-8").write("\n")
            count += 1
PY

mutant_count=0
while IFS= read -r mutant_settings; do
  if run_from_worktree "$mutant_settings"; then
    fail "failability: a relative installed hook path passed the worktree selfcheck ($mutant_settings)"
    exit 1
  fi
  mutant_count=$((mutant_count + 1))
done < <(find "$TMP/mutants" -type f -name 'mutant-*.json' | LC_ALL=C sort)
if [ "$mutant_count" -gt 0 ]; then
  ok "failability: every onboarding hook mutant fails the worktree selfcheck ($mutant_count mutants)"
else
  fail "failability: no onboarding hook mutants were generated"
  exit 1
fi

echo "test-hook-paths: OK"
