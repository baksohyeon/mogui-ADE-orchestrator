#!/bin/bash
# PreToolUse(Edit|Write|NotebookEdit|Bash): hard-block master writes to product repositories.
# Owner decision 2026-08-03 (upgraded from the charter's warn-only spec after a measured
# same-day violation). Override: MOGUI_INLINE_EDIT_OVERRIDE=1 — allowed but logged.

log_fire() {
  local fire_log="${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}"
  mkdir -p "$(dirname "$fire_log")"
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"product-path-guard","event":"PreToolUse","cwd":"%s","runtime_hint":"%s","session_kind":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" >> "$fire_log" 2>/dev/null || true
}

log_fire

input=$(cat)
SCRIPTS_DIR=$(cd "$(dirname "$0")/.." && pwd)
# The onboarding schema owns this value in the runtime repository, not beside the
# operations scripts. Tests and deliberate host overrides may set the env var.
if [ -n "${MOGUI_INSTANCE_RUNTIME_CONFIG:-}" ]; then
  INSTANCE_RUNTIME_CONFIG="$MOGUI_INSTANCE_RUNTIME_CONFIG"
else
  INSTANCE_RUNTIME_CONFIG="{{RUNTIME_ROOT}}/config/instance-runtime.json"
fi

log_override() {
  local guarded_path="$1"
  local suppression_log="${MOGUI_HOOK_SUPPRESSION_LOG:-$HOME/.mogui/guard-suppressions.jsonl}"
  mkdir -p "$(dirname "$suppression_log")"
  printf '{"ts":"%s","path":"%s","kind":"override"}\n' "$(date -u +%FT%TZ)" "$guarded_path" >> "$suppression_log"
}

load_product_repositories() {
  CONFIG_PATH="$INSTANCE_RUNTIME_CONFIG" python3 -c '
import json
import os
import sys

path = os.environ.get("CONFIG_PATH", "")
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as exc:
    print(f"configuration missing or unreadable: {path}: {exc}", file=sys.stderr)
    sys.exit(1)

repo = data.get("product_repo")
if not isinstance(repo, str) or not repo.strip():
    print("configuration malformed: product_repo must be a non-empty absolute path", file=sys.stderr)
    sys.exit(1)

if not os.path.isabs(os.path.expanduser(repo)):
    print("configuration malformed: product_repo must be an absolute path", file=sys.stderr)
    sys.exit(1)
print(os.path.realpath(os.path.expanduser(repo)))
'
}

is_product_repo_path() {
  local guarded_path
  guarded_path=$(python3 -c 'import os,sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$1")
  local repo
  while IFS= read -r repo; do
    case "$guarded_path" in
      "$repo"|"$repo"/*) return 0 ;;
    esac
  done
  return 1
}

guard_path() {
  local guarded_path
  guarded_path=$(python3 -c 'import os,sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$1")
  local repos_output
  if ! repos_output=$(load_product_repositories 2>&1); then
    echo "[product-path-guard] BLOCKED: cannot load product repository configuration from $INSTANCE_RUNTIME_CONFIG ($repos_output). This guard fails closed; fix config/instance-runtime.json before editing guarded surfaces." >&2
    exit 2
  fi
  if printf '%s\n' "$repos_output" | is_product_repo_path "$guarded_path"; then
    if [ "${MOGUI_INLINE_EDIT_OVERRIDE:-0}" = "1" ]; then
      log_override "$guarded_path"
      exit 0
    fi
    echo "[product-path-guard] BLOCKED: $guarded_path is product-repo territory. The master dispatches workers ([Document Map](../docs/charter/01-document-map.md) / [Execution Principles](../docs/charter/03-execution-principles.md)): write a contract under mogui-master-ops/contracts/, pass the dispatch gate, and dispatch via orca orchestration. If this is gitignored instance state, relocate it to the operations repository's config/instance-runtime.json instead of dispatching product work. Override only with MOGUI_INLINE_EDIT_OVERRIDE=1 (logged to ~/.mogui/guard-suppressions.jsonl)." >&2
    exit 2
  fi
}

# Parse every Bash command, not only git. A non-git command can write through a
# redirection or a tool argument, and a command parser that silently discards it
# turns the guard into a git-only check. Unknown commands running from a product
# repository fail closed; read-only commands remain allowed.
guard_command_paths() {
  local guarded_roots="$1"
  local result
  result=$(PRODUCT_ROOTS="$guarded_roots" python3 -c '
import json, os, shlex, sys

try:
    payload = json.load(sys.stdin)
except Exception:
    print("UNSAFE:invalid-json")
    raise SystemExit

command = (payload.get("tool_input") or {}).get("command", "")
if not command:
    raise SystemExit
roots = [os.path.realpath(os.path.expanduser(x)) for x in os.environ.get("PRODUCT_ROOTS", "").splitlines() if x]
start = os.path.realpath(os.path.expanduser(
    (payload.get("tool_input") or {}).get("working_directory")
    or payload.get("cwd") or payload.get("working_directory") or os.getcwd()
))
readonly = {"pwd", "ls", "ll", "cat", "head", "tail", "grep", "rg", "find", "stat", "file", "whoami", "env", "true", "false", "test", "printf"}
git_readonly = {"status", "log", "diff", "show", "rev-parse", "branch", "tag", " ls-files", "ls-files", "describe", "for-each-ref", "remote", "config --get"}
def under(path):
    path = os.path.realpath(os.path.expanduser(path))
    return any(path == root or path.startswith(root + os.sep) for root in roots)
def resolve(base, value):
    value = os.path.expanduser(value)
    return os.path.realpath(value if os.path.isabs(value) else os.path.join(base, value))
try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|><")
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
except Exception:
    print("UNSAFE:unparseable-command")
    raise SystemExit

segments, current = [], []
for token in tokens:
    if token in {";", "&&", "||", "|", "&"}:
        if current: segments.append(current)
        current = []
    else:
        current.append(token)
if current: segments.append(current)

for parts in segments:
    if not parts: continue
    if parts[0] == "cd":
        if len(parts) < 2: print("UNSAFE:cd-without-target"); raise SystemExit
        current = resolve(current, parts[1])
        if under(current):
            print("BLOCK:" + current); raise SystemExit
        continue
    command_name = os.path.basename(parts[0])
    if command_name == "git":
        idx, git_cwd, work_tree, git_dir, sub = 1, current, None, None, ""
        while idx < len(parts):
            token = parts[idx]
            if token == "-C":
                if idx + 1 >= len(parts): print("UNSAFE:git-C-without-target"); raise SystemExit
                git_cwd = resolve(git_cwd, parts[idx + 1]); idx += 2; continue
            if token.startswith("-C") and token != "-C":
                git_cwd = resolve(git_cwd, token[2:]); idx += 1; continue
            if token in ("--work-tree", "--git-dir"):
                if idx + 1 >= len(parts): print("UNSAFE:git-option-without-value"); raise SystemExit
                value = parts[idx + 1]
                if token == "--work-tree": work_tree = resolve(git_cwd, value)
                else: git_dir = resolve(git_cwd, value)
                idx += 2; continue
            if token.startswith("--work-tree="): work_tree = resolve(git_cwd, token.split("=", 1)[1]); idx += 1; continue
            if token.startswith("--git-dir="): git_dir = resolve(git_cwd, token.split("=", 1)[1]); idx += 1; continue
            if token.startswith("-"): idx += 1; continue
            sub = token; break
        read = sub in {"status", "log", "diff", "show", "rev-parse", "ls-files", "describe", "for-each-ref", "remote"}
        if sub == "config" and idx + 1 < len(parts) and parts[idx + 1] in {"--get", "--get-all", "--list"}: read = True
        if not read:
            if git_dir and not work_tree:
                print("UNSAFE:git-dir-without-work-tree"); raise SystemExit
            target = work_tree or git_cwd
            if under(target): print("BLOCK:" + os.path.realpath(target)); raise SystemExit
        continue
    # Redirection targets and absolute path arguments are write evidence.
    for i, token in enumerate(parts[1:], 1):
        if token in {">", ">>", "<", "2>", "2>>", "&>"} and i + 1 < len(parts):
            candidate = resolve(current, parts[i + 1])
            if under(candidate): print("BLOCK:" + candidate); raise SystemExit
        elif token.startswith("/") or token.startswith("~/"):
            candidate = resolve(current, token)
            if under(candidate): print("BLOCK:" + candidate); raise SystemExit
    if under(current) and command_name not in readonly:
        print("BLOCK:" + current); raise SystemExit
' <<<"$input")
  case "$result" in
    BLOCK:*) guard_path "${result#BLOCK:}" ;;
    UNSAFE:*) echo "[product-path-guard] BLOCKED: cannot safely parse command (${result#UNSAFE:}); refusing to run it." >&2; exit 2 ;;
  esac
}

path=$(printf '%s' "$input" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    ti=d.get('tool_input',{})
    print(ti.get('file_path') or ti.get('notebook_path') or '')
except Exception:
    print('')
" 2>/dev/null)
[ -n "$path" ] && guard_path "$path"

configured_roots=$(load_product_repositories 2>/dev/null) || {
  echo "[product-path-guard] BLOCKED: cannot load product repository configuration from $INSTANCE_RUNTIME_CONFIG; this guard fails closed." >&2
  exit 2
}
guard_command_paths "$configured_roots"

bash_git_write_target=$(printf '%s' "$input" | python3 -c "
import json
import os
import re
import shlex
import subprocess
import sys

WRITE_COMMANDS = {
    'commit', 'merge', 'rebase', 'push', 'reset', 'checkout', 'switch',
    'cherry-pick', 'revert', 'apply', 'am', 'clean'
}
GLOBAL_WITH_VALUE = {'-c', '--config-env', '-C', '--exec-path', '--git-dir', '--work-tree', '--namespace'}
GLOBAL_NO_VALUE = {
    '--version', '--help', '-p', '--paginate', '-P', '--no-pager',
    '--no-replace-objects', '--bare', '--literal-pathspecs',
    '--glob-pathspecs', '--noglob-pathspecs', '--icase-pathspecs'
}
ASSIGNMENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=.*$')

def resolve(base, candidate):
    if not candidate:
        return os.path.normpath(base)
    expanded = os.path.expanduser(candidate)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(base, expanded))

def split_segments(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|')
    lexer.whitespace_split = True
    lexer.commenters = ''
    tokens = list(lexer)
    segments = []
    current = []
    for token in tokens:
        if token in {';', '&&', '||', '|', '&'}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments

def strip_prefix(segment):
    out = list(segment)
    while out and ASSIGNMENT_RE.match(out[0]):
        out = out[1:]
    if out and out[0] == 'env':
        out = out[1:]
        while out and (ASSIGNMENT_RE.match(out[0]) or out[0].startswith('-')):
            out = out[1:]
    return out

def write_git_command(git_parts):
    idx = 1
    git_cwd = None
    subcommand = ''
    while idx < len(git_parts):
        token = git_parts[idx]
        if token == '-C':
            if idx + 1 >= len(git_parts):
                return None, ''
            git_cwd = ('REL', git_parts[idx + 1]) if git_cwd is None else ('REL', git_parts[idx + 1], git_cwd)
            idx += 2
            continue
        if token.startswith('-C') and token != '-C':
            value = token[2:]
            if value:
                git_cwd = ('REL', value) if git_cwd is None else ('REL', value, git_cwd)
            idx += 1
            continue
        if token in GLOBAL_WITH_VALUE:
            idx += 2
            continue
        if token in GLOBAL_NO_VALUE:
            idx += 1
            continue
        if token.startswith('--') and '=' in token:
            flag = token.split('=', 1)[0]
            if flag in GLOBAL_WITH_VALUE:
                idx += 1
                continue
        if token.startswith('-'):
            idx += 1
            continue
        subcommand = token
        break

    if not subcommand:
        return None, ''

    args = git_parts[idx + 1:]
    is_write = subcommand in WRITE_COMMANDS
    if subcommand == 'branch':
        is_write = any(a in ('-d', '-D', '--delete') for a in args)
    elif subcommand == 'tag':
        is_write = any(a in ('-d', '--delete') for a in args)
    if not is_write:
        return None, ''

    return git_cwd, subcommand

def apply_git_c(base_cwd, marker):
    if marker is None:
        return base_cwd
    parts = []
    m = marker
    while isinstance(m, tuple):
        if len(m) >= 2:
            parts.append(m[1])
        m = m[2] if len(m) == 3 else None
    cwd = base_cwd
    for p in reversed(parts):
        cwd = resolve(cwd, p)
    return cwd

def repo_root(path):
    try:
        out = subprocess.check_output(
            ['git', '-C', path, 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        return os.path.normpath(out)
    except Exception:
        return ''

try:
    payload = json.load(sys.stdin)
except Exception:
    print('')
    sys.exit(0)

tool_input = payload.get('tool_input', {})
command = tool_input.get('command', '')
if not command:
    print('')
    sys.exit(0)

start_cwd = tool_input.get('working_directory') or payload.get('cwd') or payload.get('working_directory') or os.getcwd()
cwd = os.path.normpath(os.path.expanduser(start_cwd))

for segment in split_segments(command):
    parts = strip_prefix(segment)
    if not parts:
        continue
    if parts[0] == 'cd':
        target = parts[1] if len(parts) > 1 else os.path.expanduser('~')
        cwd = resolve(cwd, target)
        continue
    if parts[0] != 'git':
        continue
    git_c_marker, subcommand = write_git_command(parts)
    if not subcommand:
        continue
    git_cwd = apply_git_c(cwd, git_c_marker)
    root = repo_root(git_cwd)
    if root:
        print(root)
        sys.exit(0)

print('')
" 2>/dev/null)

[ -n "$bash_git_write_target" ] && guard_path "$bash_git_write_target"
exit 0
