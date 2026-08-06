#!/bin/bash
# PreToolUse(Edit|Write|NotebookEdit|Bash): hard-block master writes to product repositories.
# Owner decision 2026-08-03 (upgraded from the charter's warn-only spec after a measured
# same-day violation). Override: MOGUI_INLINE_EDIT_OVERRIDE=1 — allowed but logged.

log_fire() {
  mkdir -p ~/.mogui
  local session_kind="unknown"
  if [ -n "$ORCA_TASK_ID" ] || [ -n "$ORCA_DISPATCH_ID" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    session_kind="worker"
  fi
  printf '{"ts":%d,"hook":"product-path-guard","event":"PreToolUse","cwd":"%s","runtime_hint":"%s","session_kind":"%s"}\n' \
    "$(date +%s)" "$PWD" "${MOGUI_RUNTIME_HINT:-unknown}" "$session_kind" >> ~/.mogui/hook-fire-log.jsonl 2>/dev/null || true
}

log_fire

input=$(cat)
SCRIPTS_DIR=$(cd "$(dirname "$0")/.." && pwd)
INSTANCE_RUNTIME_CONFIG=${MOGUI_INSTANCE_RUNTIME_CONFIG:-$SCRIPTS_DIR/../config/instance-runtime.json}

log_override() {
  local guarded_path="$1"
  mkdir -p ~/.mogui
  printf '{"ts":"%s","path":"%s","kind":"override"}\n' "$(date -u +%FT%TZ)" "$guarded_path" >> ~/.mogui/guard-suppressions.jsonl
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

repos = data.get("product_repositories")
if not isinstance(repos, list) or not repos:
    print("configuration malformed: product_repositories must be a non-empty array", file=sys.stderr)
    sys.exit(1)

for repo in repos:
    if not isinstance(repo, str) or not repo.strip() or not os.path.isabs(os.path.expanduser(repo)):
        print("configuration malformed: product_repositories entries must be absolute paths", file=sys.stderr)
        sys.exit(1)
    print(os.path.normpath(os.path.expanduser(repo)))
'
}

is_product_repo_path() {
  local guarded_path="$1"
  local repo
  while IFS= read -r repo; do
    case "$guarded_path" in
      "$repo"|"$repo"/*) return 0 ;;
    esac
  done
  return 1
}

guard_path() {
  local guarded_path="$1"
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
