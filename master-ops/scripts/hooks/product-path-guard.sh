#!/bin/bash
# PreToolUse(Edit|Write|NotebookEdit|Bash): fail-closed product repository guard.
# Bash uses a measured read-only allowlist. An unknown command or unresolved target
# is denied; the allowlist is intentionally not inferred from command names.
set -u

if [ -n "${MOGUI_INSTANCE_RUNTIME_CONFIG:-}" ]; then
  INSTANCE_RUNTIME_CONFIG="$MOGUI_INSTANCE_RUNTIME_CONFIG"
else
  INSTANCE_RUNTIME_CONFIG="{{RUNTIME_ROOT}}/config/instance-runtime.json"
fi
HOOK_DIR=$(cd "$(dirname "$0")" && pwd)
ALLOWLIST="${MOGUI_PRODUCT_GUARD_ALLOWLIST:-$HOOK_DIR/product-path-guard-readonly-allowlist.txt}"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}"

record_fire() {
  local command_class="${1:-}" decision="${2:-observed}"
  mkdir -p "$(dirname "$FIRE_LOG")"
  COMMAND_CLASS="$command_class" DECISION="$decision" python3 - "$FIRE_LOG" <<'PY' 2>/dev/null || true
import json, os, sys, time
path = sys.argv[1]
record = {
    "ts": int(time.time()),
    "hook": "product-path-guard",
    "event": "PreToolUse",
    "cwd": os.getcwd(),
    "runtime_hint": os.environ.get("MOGUI_RUNTIME_HINT", "unknown"),
    "session_kind": "worker" if (os.environ.get("ORCA_TASK_ID") or os.environ.get("ORCA_DISPATCH_ID") or ".orca/worktrees" in os.getcwd()) else "unknown",
    "command_class": os.environ.get("COMMAND_CLASS", ""),
    "decision": os.environ.get("DECISION", "observed"),
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}

load_product_repo() {
  CONFIG_PATH="$INSTANCE_RUNTIME_CONFIG" python3 -c '
import json, os, sys
path = os.environ["CONFIG_PATH"]
try:
    with open(path, encoding="utf-8") as fh:
        value = json.load(fh).get("product_repo")
except Exception as exc:
    print(f"configuration missing or unreadable: {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(value, str) or not value.strip() or not os.path.isabs(os.path.expanduser(value)):
    print("configuration malformed: product_repo must be an absolute path", file=sys.stderr)
    raise SystemExit(1)
print(os.path.realpath(os.path.expanduser(value)))
'
}

is_under() {
  python3 - "$1" "$2" <<'PY'
import os, sys
root = os.path.realpath(os.path.expanduser(sys.argv[1]))
target = os.path.realpath(os.path.expanduser(sys.argv[2]))
print("yes" if target == root or target.startswith(root + os.sep) else "no")
PY
}

blocked() {
  local reason="$1" command_class="${2:-}"
  record_fire "$command_class" blocked
  echo "[product-path-guard] BLOCKED: $reason" >&2
  exit 2
}

input=$(cat)
repo=$(load_product_repo 2>/dev/null) || blocked "cannot load product_repo from $INSTANCE_RUNTIME_CONFIG" ""

file_path=$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); t=d.get("tool_input",{}); print(t.get("file_path") or t.get("notebook_path") or "")' 2>/dev/null) || blocked "invalid hook input" ""
if [ -n "$file_path" ]; then
  target=$(python3 -c 'import os,sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$file_path") || blocked "cannot resolve file target" ""
  [ "$(is_under "$repo" "$target")" = yes ] || { record_fire "file-tool" allowed; exit 0; }
  if [ "${MOGUI_INLINE_EDIT_OVERRIDE:-0}" = 1 ]; then
    record_fire "file-tool" override
    exit 0
  fi
  blocked "$target is product-repo territory; dispatch product writes through a contract" "file-tool"
fi

command=$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command", ""))' 2>/dev/null) || blocked "invalid hook input" ""
[ -n "$command" ] || { record_fire "" allowed; exit 0; }

result=$(PRODUCT_ROOT="$repo" ALLOWLIST="$ALLOWLIST" python3 -c '
import json, os, shlex, sys
payload=json.load(sys.stdin)
tool=payload.get("tool_input", {})
command=tool.get("command", "")
cwd=os.path.realpath(os.path.expanduser(tool.get("working_directory") or payload.get("cwd") or os.getcwd()))
root=os.path.realpath(os.path.expanduser(os.environ["PRODUCT_ROOT"]))
def resolve(base, value):
    value=os.path.expanduser(value)
    return os.path.realpath(value if os.path.isabs(value) else os.path.join(base, value))
def under(value):
    value=os.path.realpath(os.path.expanduser(value))
    return value == root or value.startswith(root + os.sep)
try:
    tokens=list(shlex.shlex(command, posix=True, punctuation_chars=";&|><"))
except Exception:
    print("DENY\tunparseable\tunparseable command")
    raise SystemExit
segments=[]; current=[]
for token in tokens:
    if token in {";","&&","||","|","&"}:
        if current: segments.append(current)
        current=[]
    else: current.append(token)
if current: segments.append(current)
current_cwd=cwd
allow=set()
try:
    with open(os.environ["ALLOWLIST"], encoding="utf-8") as fh:
        allow={line.strip() for line in fh if line.strip() and not line.lstrip().startswith("#")}
except OSError:
    pass
for parts in segments:
    if not parts: continue
    name=os.path.basename(parts[0])
    if name == "cd":
        if len(parts) != 2:
            print("DENY\tcd\tcd target cannot be resolved")
            raise SystemExit
        current_cwd=resolve(current_cwd, parts[1])
        continue
    sub=""
    git_target=current_cwd
    work_tree=None
    git_dir=None
    if name == "git":
        i=1
        while i < len(parts):
            token=parts[i]
            if token == "-C":
                if i+1 >= len(parts): print("DENY\tgit\tgit -C target is missing"); raise SystemExit
                git_target=resolve(git_target, parts[i+1]); i+=2; continue
            if token.startswith("-C") and token != "-C":
                git_target=resolve(git_target, token[2:]); i+=1; continue
            if token in ("--work-tree", "--git-dir"):
                if i+1 >= len(parts): print("DENY\tgit\tgit target option is missing"); raise SystemExit
                value=resolve(git_target, parts[i+1])
                if token == "--work-tree": work_tree=value
                else: git_dir=value
                i+=2; continue
            if token.startswith("--work-tree="): work_tree=resolve(git_target, token.split("=",1)[1]); i+=1; continue
            if token.startswith("--git-dir="): git_dir=resolve(git_target, token.split("=",1)[1]); i+=1; continue
            if token.startswith("-"): i+=1; continue
            sub=token; break
        command_class="git" + (" " + sub if sub else "")
        if git_dir and not work_tree:
            print("DENY\t"+command_class+"\tgit-dir has no resolvable work-tree")
            raise SystemExit
        target=work_tree or git_target
    else:
        command_class=name
        target=current_cwd
        if name in {"bash", "sh", "dash", "ksh", "zsh", "python", "python3", "perl", "ruby", "node"}:
            if any(">" in token or root in token for token in parts[1:]):
                print("DENY\t"+command_class+"\topaque interpreter command may contain an unparsed write")
                raise SystemExit
    target_hits=[]
    for i,token in enumerate(parts[1:],1):
        if token in {">",">>","2>","2>>","&>"}:
            if i+1 >= len(parts): print("DENY\t"+command_class+"\tredirection target is missing"); raise SystemExit
            target_hits.append(resolve(current_cwd, parts[i+1]))
        elif token.startswith("/") or token.startswith("~/"):
            target_hits.append(resolve(current_cwd, token))
    touches=under(target) or any(under(x) for x in target_hits)
    if not touches:
        continue
    if any(token in {">",">>","2>","2>>","&>"} for token in parts):
        print("DENY\t"+command_class+"\tshell redirection is a write")
        raise SystemExit
    if command_class not in allow:
        print("DENY\t"+command_class+"\tcommand is not in measured read-only allowlist")
        raise SystemExit
print("ALLOW\t" + (";".join(sorted(allow)) if allow else "empty") + "\tread-only allowlist")
' <<<"$input")
decision=${result%%$'\t'*}
command_class=${result#*$'\t'}
command_class=${command_class%%$'\t'*}
reason=${result#*$'\t'*$'\t'}
if [ "$decision" = DENY ]; then
  blocked "$reason" "$command_class"
fi
record_fire "$command_class" allowed
