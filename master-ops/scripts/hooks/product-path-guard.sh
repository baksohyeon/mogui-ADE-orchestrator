#!/bin/bash
# PreToolUse(Edit|Write|NotebookEdit|Bash): product repository guard.
# Bash command parsing is best effort. It blocks observed direct write shapes
# (redirections, known write-capable commands, and selected mutating git
# subcommands) but does not parse opaque script bodies, shell expansions, or
# every command-specific path flag.
# Legacy mode admits opaque interpreter -c commands outside product root, while fail-closed mode denies unallowlisted interpreter commands regardless of cwd.
set -u

VERDICT="pass"
if [ -n "${MOGUI_INSTANCE_RUNTIME_CONFIG:-}" ]; then
  INSTANCE_RUNTIME_CONFIG="$MOGUI_INSTANCE_RUNTIME_CONFIG"
else
  INSTANCE_RUNTIME_CONFIG="{{RUNTIME_ROOT}}/config/instance-runtime.json"
fi
HOOK_DIR=$(cd "$(dirname "$0")" && pwd)
ALLOWLIST="${MOGUI_PRODUCT_GUARD_ALLOWLIST:-$HOOK_DIR/product-path-guard-readonly-allowlist.txt}"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ && pwd)}/.mogui/hook-fire-log.jsonl}"
FAIL_CLOSED="${MOGUI_PRODUCT_GUARD_FAIL_CLOSED:-0}"

mg_emit() {
  local level="$1" event="$2" outcome="$3" reason="$4"
  local command_class="${5:-}" target_scope="${6:-}"
  local tool_kind="${7:-bash}"
  local event_log="${MOGUI_EVENT_LOG:-$HOME/.mogui/event-log.jsonl}"
  EVENT_LOG="$event_log" MG_LEVEL="$level" MG_EVENT="$event" MG_OUTCOME="$outcome" \
    MG_REASON="$reason" MG_COMMAND_CLASS="$command_class" MG_TARGET_SCOPE="$target_scope" MG_TOOL_KIND="$tool_kind" \
    python3 - <<'PY' 2>/dev/null || true
import json, os, time
path = os.environ["EVENT_LOG"]
record = {
    "ts": int(time.time()), "level": os.environ["MG_LEVEL"],
    "event": os.environ["MG_EVENT"], "component": "tool-impl",
    "session_kind": "worker" if os.environ.get("ORCA_TASK_ID") else "unknown",
    "runtime_hint": os.environ.get("MOGUI_RUNTIME_HINT", "unknown"),
    "outcome": os.environ["MG_OUTCOME"], "evidence": "observed",
    "reason": os.environ["MG_REASON"],
    "command_class": os.environ["MG_COMMAND_CLASS"],
    "target_scope": os.environ["MG_TARGET_SCOPE"],
    "tool_kind": os.environ["MG_TOOL_KIND"],
}
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}

record_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")"
  VERDICT="$VERDICT" python3 - "$FIRE_LOG" <<'PY' 2>/dev/null || true
import json, os, sys, time
path = sys.argv[1]
record = {
    "ts": int(time.time()),
    "hook": "product-path-guard",
    "event": "PreToolUse",
    "cwd": os.getcwd(),
    "runtime_hint": os.environ.get("MOGUI_RUNTIME_HINT", "unknown"),
    "session_kind": (
        "worker"
        if (os.environ.get("ORCA_TASK_ID") or os.environ.get("ORCA_DISPATCH_ID") or ".orca/worktrees" in os.getcwd())
        else (
            "master" if os.path.exists(os.path.join(os.getcwd(), "docs", "MASTER-OPERATIONS.md")) else "unknown"
        )
    ),
    "verdict": os.environ.get("VERDICT", "pass"),
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}

# Preserve the legacy hook-fire schema and coverage signal; decision details go
# exclusively to event-log.jsonl through mg_emit.
trap record_fire EXIT

if [[ "$INSTANCE_RUNTIME_CONFIG" == *"{{RUNTIME_ROOT}}"* ]]; then
  VERDICT="block"
  echo "[product-path-guard] BLOCKED: unsubstituted {{RUNTIME_ROOT}} token in INSTANCE_RUNTIME_CONFIG; set MOGUI_INSTANCE_RUNTIME_CONFIG to a real runtime config path" >&2
  exit 2
fi

load_product_repositories() {
  CONFIG_PATH="$INSTANCE_RUNTIME_CONFIG" python3 -c '
import json, os, sys
path = os.environ["CONFIG_PATH"]
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
except Exception as exc:
    print(f"configuration missing or unreadable: {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)

def absolute(value, field):
    if not isinstance(value, str) or not value.strip() or not os.path.isabs(os.path.expanduser(value)):
        print(f"configuration malformed: {field} must be an absolute path", file=sys.stderr)
        raise SystemExit(1)
    return os.path.realpath(os.path.expanduser(value))

repos_value = data.get("product_repositories")
repo_value = data.get("product_repo")
if repos_value is not None:
    if not isinstance(repos_value, list) or not repos_value:
        print("configuration malformed: product_repositories must be a non-empty array", file=sys.stderr)
        raise SystemExit(1)
    repos = [absolute(entry, "product_repositories") for entry in repos_value]
    if repo_value is not None:
        if not isinstance(repo_value, str):
            print("configuration malformed: product_repo must be a string or null", file=sys.stderr)
            raise SystemExit(1)
        if repo_value.strip():
            absolute(repo_value, "product_repo")
            print("configuration warning: product_repositories and product_repo are both set; product_repositories wins", file=sys.stderr)
elif repo_value is not None:
    repos = [absolute(repo_value, "product_repo")]
else:
    print("configuration malformed: product_repositories (or product_repo) is required", file=sys.stderr)
    raise SystemExit(1)

for repo in repos:
    print(repo)
'
}

is_under_any() {
  local target="$1"
  shift
  python3 - "$target" "$@" <<'PY'
import os, sys
target = os.path.realpath(os.path.expanduser(sys.argv[1]))
for root in sys.argv[2:]:
    root = os.path.realpath(os.path.expanduser(root))
    if target == root or target.startswith(root + os.sep):
        print("yes")
        raise SystemExit
print("no")
PY
}

blocked() {
  local reason="$1" command_class="${2:-}" reason_code="${3:-guarded_target}"
  VERDICT="block"
  if [ "$command_class" = "file-tool" ] || [ "$command_class" = "file_tool" ]; then
    mg_emit error product_path_guard finding "$reason_code" "$command_class" guarded file
  else
    mg_emit error product_path_guard finding "$reason_code" "$command_class" guarded bash
  fi
  echo "[product-path-guard] BLOCKED: $reason" >&2
  exit 2
}

input=$(cat)
if ! printf '%s' "$input" | python3 -c 'import json,sys; payload=json.load(sys.stdin); tool=payload.get("tool_input") if isinstance(payload, dict) else None; raise SystemExit(0 if isinstance(payload, dict) and isinstance(tool, dict) else 1)' >/dev/null 2>&1; then
  blocked "invalid hook input" ""
fi
repos=$(load_product_repositories) || blocked "cannot load product_repositories from $INSTANCE_RUNTIME_CONFIG" ""
repo_array=()
while IFS= read -r repo_line; do
  [ -n "$repo_line" ] && repo_array+=("$repo_line")
done <<<"$repos"

file_path=$(printf '%s' "$input" | python3 -c 'import json,sys; tool=json.load(sys.stdin)["tool_input"]; print(tool.get("file_path") or tool.get("notebook_path") or "")' 2>/dev/null) || blocked "invalid hook input" ""
if [ -n "$file_path" ]; then
  target=$(python3 -c 'import os,sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$file_path") || blocked "cannot resolve file target" ""
  [ "$(is_under_any "$target" "${repo_array[@]}")" = yes ] || { mg_emit info product_path_guard pass file_tool file_tool outside file; exit 0; }
  if [ "${MOGUI_INLINE_EDIT_OVERRIDE:-0}" = 1 ]; then
    VERDICT="override"
    mg_emit notice product_path_guard pass override file_tool guarded file
    exit 0
  fi
  blocked "$target is product-repo territory; dispatch product writes through a contract" "file-tool" guarded_target
fi

command=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tool_input"].get("command", ""))' 2>/dev/null) || blocked "invalid hook input" ""
[ -n "$command" ] || { mg_emit info product_path_guard pass empty_command; exit 0; }

result=$(PRODUCT_ROOTS="$repos" ALLOWLIST="$ALLOWLIST" FAIL_CLOSED="$FAIL_CLOSED" python3 -c '
import json, os, re, shlex, sys
payload=json.load(sys.stdin)
tool=payload.get("tool_input", {})
command=tool.get("command", "")
cwd=os.path.realpath(os.path.expanduser(tool.get("working_directory") or payload.get("cwd") or os.getcwd()))
roots=[os.path.realpath(os.path.expanduser(line)) for line in os.environ["PRODUCT_ROOTS"].splitlines() if line.strip()]
LEGACY_MODE = os.environ["FAIL_CLOSED"] != "1"
INTERPRETER_NAMES = {"bash", "sh", "dash", "ksh", "zsh", "python", "python3", "perl", "ruby", "node"}
PLAIN_PATH_TARGET_EXEMPT = {"cp", "install", "ln"} | (INTERPRETER_NAMES if LEGACY_MODE else set())
SQ=chr(39)
HEREDOC_OPERATOR_RE = re.compile(r"<<(?!<)(-)?\s*(?:" + SQ + r"([^" + SQ + r"]*)" + SQ + r"|\"([^\"]*)\"|\\(\S+)|([^\s<>|&;()]+))")
def unquoted_mask(line):
    mask=[]
    in_single=False
    in_double=False
    in_comment=False
    escaped=False
    prev_char=""
    for ch in line:
        if not in_single and not in_double and not in_comment and ch == "#" and prev_char in ("", " ", "\t"):
            in_comment=True
        mask.append(not in_single and not in_double and not in_comment)
        prev_char=ch
        if in_comment:
            continue
        if escaped:
            escaped=False
            continue
        if ch == "\\" and not in_single:
            escaped=True
        elif ch == SQ and not in_double:
            in_single = not in_single
        elif ch == chr(34) and not in_single:
            in_double = not in_double
    return mask
def find_heredoc_operators(line):
    mask=unquoted_mask(line)
    operators=[]
    for match in HEREDOC_OPERATOR_RE.finditer(line):
        start=match.start()
        if start > 0 and line[start - 1] == "<":
            continue
        if start < len(mask) and not mask[start]:
            continue
        word=next(g for g in match.groups()[1:] if g is not None)
        operators.append((word, bool(match.group(1))))
    return operators
def strip_heredocs(text):
    lines=text.split("\n")
    out=[]
    i=0
    n=len(lines)
    forced_deny_name=None
    while i < n:
        line=lines[i]
        out.append(line)
        operators=find_heredoc_operators(line)
        if operators:
            operator_line_name=""
            operator_line_has_dash_c=False
            try:
                operator_line_tokens=list(shlex.shlex(line, posix=True, punctuation_chars=";&|><"))
                if operator_line_tokens:
                    operator_line_name=os.path.basename(operator_line_tokens[0])
                    operator_line_has_dash_c="-c" in operator_line_tokens[1:]
            except Exception:
                pass
            j=i + 1
            for word, strip_tabs in operators:
                body_lines=[]
                terminated=False
                while j < n:
                    raw_line=lines[j]
                    candidate=raw_line.lstrip("\t") if strip_tabs else raw_line
                    j += 1
                    if candidate == word:
                        terminated=True
                        break
                    body_lines.append(raw_line)
                if not terminated:
                    return None, None
                # A heredoc feeding an interpreter stdin is as opaque as a -c
                # body (no -c means the heredoc itself is the script), so it
                # gets the same root/cd/redirect scrutiny before being admitted.
                if operator_line_name in INTERPRETER_NAMES and not operator_line_has_dash_c:
                    body_text="\n".join(body_lines)
                    if (
                        contains_cd_token(body_text)
                        or any(root in body_text for root in roots)
                        or redirects_into_root(body_text, cwd)
                    ):
                        forced_deny_name=operator_line_name
            i=j
            continue
        i += 1
    return "\n".join(out), forced_deny_name
def resolve(base, value):
    value=os.path.expanduser(value)
    return os.path.realpath(value if os.path.isabs(value) else os.path.join(base, value))
def under(value):
    value=os.path.realpath(os.path.expanduser(value))
    return any(value == root or value.startswith(root + os.sep) for root in roots)
def contains_cd_token(value):
    return re.search(r"(^|[\s;&|()])cd([\s;&|()]|$)", value) is not None
def redirects_into_root(value, base):
    try:
        body_tokens=list(shlex.shlex(value, posix=True, punctuation_chars=";&|><"))
    except Exception:
        return False
    redirections={">",">>","2>","2>>","&>",">&",">|"}
    i=0
    while i < len(body_tokens):
        token=body_tokens[i]
        if token in redirections:
            if i + 1 >= len(body_tokens):
                return True
            if under(resolve(base, body_tokens[i + 1])):
                return True
            i += 2
            continue
        i += 1
    return False
def collect_non_option_operands(parts, start, options_with_values):
    values=set(options_with_values)
    index=start
    out=[]
    while index < len(parts):
        token=parts[index]
        if token == "--":
            out.extend(parts[index + 1 :])
            break
        if token in values:
            index += 2
            continue
        if any(option.startswith("--") and token.startswith(option + "=") for option in values):
            index += 1
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        out.append(token)
        index += 1
    return out
def has_install_directory_mode(option_tokens):
    install_value_short={"g", "m", "o", "S", "t"}
    install_flag_short={"d"}
    index=0
    while index < len(option_tokens):
        token=option_tokens[index]
        if token == "--":
            break
        if token == "--directory":
            return True
        if token.startswith("--"):
            index += 1
            continue
        if token.startswith("-") and token != "-":
            short=token[1:]
            pos=0
            while pos < len(short):
                flag=short[pos]
                if flag in install_flag_short:
                    return True
                if flag in install_value_short:
                    if pos + 1 < len(short):
                        break
                    index += 1
                    break
                pos += 1
        index += 1
    return False
heredoc_stripped_command, heredoc_forced_deny_name=strip_heredocs(command)
if heredoc_stripped_command is None:
    print("DENY\tunparseable\tunparseable command")
    raise SystemExit
if heredoc_forced_deny_name:
    print("DENY\t" + heredoc_forced_deny_name + "\topaque interpreter heredoc body may contain an unparsed write")
    raise SystemExit
try:
    tokens=list(shlex.shlex(heredoc_stripped_command, posix=True, punctuation_chars=";&|><"))
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
last_command_class=""
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
        if os.environ["FAIL_CLOSED"] != "1" and under(current_cwd):
            print("DENY\tcd\tlegacy policy blocks entering product root")
            raise SystemExit
        continue
    sub=""
    sub_pos=-1
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
            sub=token; sub_pos=i; break
        command_class="git" + (" " + sub if sub else "")
        if sub == "branch" and sub_pos >= 0:
            branch_args=[token for token in parts[sub_pos + 1 :] if token != "--"]
            if branch_args == ["--show-current"]:
                command_class="git branch --show-current"
        remote_action=""
        if sub == "remote" and sub_pos >= 0:
            remote_index=sub_pos + 1
            while remote_index < len(parts):
                if parts[remote_index] in {"-v", "--verbose"}:
                    remote_index += 1
                    continue
                if parts[remote_index].startswith("-"):
                    remote_index += 2
                    continue
                remote_action=parts[remote_index]
                break
        if git_dir and not work_tree:
            print("DENY\t"+command_class+"\tgit-dir has no resolvable work-tree")
            raise SystemExit
        target=work_tree or git_target
    else:
        command_class=name
        target=current_cwd
        if name in INTERPRETER_NAMES:
            bare_dash_c = "-c" in parts[1:]
            dash_c_index = parts.index("-c") if bare_dash_c else -1
            dash_c_body=""
            if bare_dash_c and dash_c_index + 1 < len(parts):
                dash_c_body=parts[dash_c_index + 1]
            if LEGACY_MODE:
                # A plain argument is a write shape only if it follows -o/--output, or
                # holds a root path after a literal ">" within the same token; the -c
                # body itself is excluded here and covered by legacy_dash_c_body_denied.
                root_token_in_args=False
                prev_token=None
                for arg_index, token in enumerate(parts[1:], 1):
                    if bare_dash_c and arg_index == dash_c_index + 1:
                        prev_token=token
                        continue
                    is_write_shape = (
                        (prev_token in ("-o", "--output") and any(root in token for root in roots))
                        or (token.startswith("--output=") and any(root in token.split("=", 1)[1] for root in roots))
                        or (">" in token and any(root in token.split(">", 1)[1] for root in roots))
                    )
                    if is_write_shape:
                        root_token_in_args=True
                        break
                    prev_token=token
            else:
                root_token_in_args = any(any(root in token for root in roots) for token in parts[1:])
            legacy_dash_c_body_denied=False
            if bare_dash_c and LEGACY_MODE and not under(current_cwd):
                legacy_dash_c_body_denied = (
                    contains_cd_token(dash_c_body)
                    or any(root in dash_c_body for root in roots)
                    or redirects_into_root(dash_c_body, current_cwd)
                )
            if root_token_in_args or legacy_dash_c_body_denied or (
                bare_dash_c and (not LEGACY_MODE or under(current_cwd))
            ):
                print("DENY\t"+command_class+"\topaque interpreter command may contain an unparsed write")
                raise SystemExit
    last_command_class=command_class
    target_hits=[]
    for i,token in enumerate(parts[1:],1):
        if token in {">",">>","2>","2>>","&>",">&",">|"}:
            if i+1 >= len(parts): print("DENY\t"+command_class+"\tredirection target is missing"); raise SystemExit
            target_hits.append(resolve(current_cwd, parts[i+1]))
        elif (token.startswith("/") or token.startswith("~/")) and name not in PLAIN_PATH_TARGET_EXEMPT:
            target_hits.append(resolve(current_cwd, token))
        elif token == "--output" and i + 1 < len(parts):
            target_hits.append(resolve(current_cwd, parts[i + 1]))
        elif token.startswith("--output="):
            target_hits.append(resolve(current_cwd, token.split("=", 1)[1]))
    git_dir_touches=bool(git_dir and under(git_dir))
    touches=under(target) or git_dir_touches or any(under(x) for x in target_hits)
    if "-exec" in parts and any(root in " ".join(parts) for root in roots):
        touches=True
    option_tokens=parts[1 : parts.index("--")] if "--" in parts[1:] else parts[1:]
    apply_option_tokens=option_tokens
    write_args={"-exec","-execdir","xargs","--in-place"}
    if name in {"sed","perl","ruby"}:
        write_args.add("-i")
    git_always_mutating={
        "add", "checkout", "cherry-pick", "commit", "merge",
        "mv", "rebase", "reset", "restore", "revert", "rm",
    }
    git_subsub=""
    git_subsub_ambiguous=False
    if name == "git" and sub and sub_pos >= 0:
        sub_index=sub_pos + 1
        stash_value_options={"-m", "--message"}
        while sub_index < len(parts):
            token=parts[sub_index]
            if token in stash_value_options:
                git_subsub_ambiguous=True
                sub_index += 2
                continue
            if token.startswith("--message="):
                git_subsub_ambiguous=True
                sub_index += 1
                continue
            if token.startswith("-"):
                sub_index += 1
                continue
            git_subsub=token
            break
    apply_readonly_mode=any(token in {"--check", "--stat", "--numstat", "--summary"} for token in apply_option_tokens)
    apply_force_mode=any(token == "--apply" for token in apply_option_tokens)
    stash_show_writes_output = (
        sub == "stash"
        and git_subsub == "show"
        and any(token == "--output" or token.startswith("--output=") for token in parts[sub_pos + 1 :])
    )
    git_mutation = name == "git" and (
        (sub == "remote" and remote_action in {"rename","set-head","set-branches","update","prune","set-url","add","remove"})
        or (sub == "diff" and any(token == "--output" or token.startswith("--output=") for token in parts))
        or (sub in git_always_mutating)
        or (sub == "apply" and (not apply_readonly_mode or apply_force_mode))
        or stash_show_writes_output
        or (sub == "clean" and not any(token in {"-n", "--dry-run"} for token in parts))
        or (sub == "stash" and (git_subsub_ambiguous or git_subsub not in {"list", "show"}))
        or (sub == "worktree" and git_subsub not in {"list"})
    )
    command_write_capable = name in {
        "cp", "mv", "rm", "rmdir", "mkdir", "install", "ln", "touch", "truncate", "tee", "dd"
    }
    write_capable=any(token in write_args for token in parts[1:]) or git_mutation or command_write_capable
    if "-exec" in parts and any(token in {"sh", "bash", "dash", "zsh", "ksh"} for token in parts):
        print("DENY\t"+command_class+"\topaque find exec wrapper is not admitted")
        raise SystemExit
    if write_capable:
        write_targets=[]
        if name == "dd":
            for token in parts[1:]:
                if token.startswith("of="):
                    write_targets.append(token.split("=", 1)[1])
        elif name == "cp":
            cp_operands=collect_non_option_operands(parts, 1, {"-t", "--target-directory"})
            for index,token in enumerate(parts[1:],1):
                if token in {"-t", "--target-directory"} and index + 1 < len(parts):
                    write_targets.append(parts[index + 1])
                elif token.startswith("--target-directory="):
                    write_targets.append(token.split("=", 1)[1])
            if not write_targets and len(cp_operands) >= 2:
                write_targets.append(cp_operands[-1])
        elif name == "install":
            install_value_options={"-g", "-m", "-o", "-S", "-t", "--suffix", "--target-directory", "--group", "--mode", "--owner", "--context"}
            install_operands=collect_non_option_operands(parts, 1, install_value_options)
            for index,token in enumerate(parts[1:],1):
                if token in {"-t", "--target-directory"} and index + 1 < len(parts):
                    write_targets.append(parts[index + 1])
                elif token.startswith("--target-directory="):
                    write_targets.append(token.split("=", 1)[1])
            if not write_targets and install_operands:
                install_directory_mode=has_install_directory_mode(option_tokens)
                if install_directory_mode:
                    write_targets.extend(install_operands)
                elif len(install_operands) >= 2:
                    write_targets.append(install_operands[-1])
        elif name == "ln":
            ln_operands=collect_non_option_operands(parts, 1, {"-t", "--target-directory", "-S", "--suffix"})
            ln_destination_mode=False
            for index,token in enumerate(parts[1:],1):
                if token in {"-t", "--target-directory"} and index + 1 < len(parts):
                    write_targets.append(parts[index + 1])
                    ln_destination_mode=True
                elif token.startswith("--target-directory="):
                    write_targets.append(token.split("=", 1)[1])
                    ln_destination_mode=True
            if not write_targets and len(ln_operands) >= 2:
                write_targets.append(ln_operands[-1])
            if ln_destination_mode:
                source_operands=ln_operands
            else:
                source_operands=ln_operands[:-1] if len(ln_operands) >= 2 else ln_operands
            write_targets.extend(source_operands)
        else:
            for token in parts[1:]:
                if not token.startswith("-") and token not in {";"}:
                    write_targets.append(token)
        for value in write_targets:
            target_hits.append(resolve(current_cwd, value))
        touches=under(target) or git_dir_touches or any(under(x) for x in target_hits)
    if not touches:
        continue
    if write_capable and touches:
        print("DENY\t"+command_class+"\twrite-capable argument is not admitted")
        raise SystemExit
    if any(token in {">",">>","2>","2>>","&>",">&",">|"} for token in parts):
        print("DENY\t"+command_class+"\tshell redirection is a write")
        raise SystemExit
    if os.environ["FAIL_CLOSED"] == "1" and command_class not in allow:
        print("DENY\t"+command_class+"\tcommand is not in measured read-only allowlist")
        raise SystemExit
    if LEGACY_MODE:
        legacy_readonly={
            "pwd","ls","ll","cat","head","tail","grep","rg","find","stat","file","whoami","env","true","false","test","printf",
            "diff","cmp","comm","wc","sort","uniq","cut","tr","shasum","sha256sum","md5","xxd","od","less","more","jq",
        }
        legacy_git_readonly={
            "git status","git log","git diff","git show","git rev-parse","git ls-files","git describe","git for-each-ref","git remote",
            "git blame","git cat-file","git ls-tree","git merge-base","git merge-tree","git rev-list",
            "git branch --show-current","git worktree","git fetch",
        }
        is_measured_readonly = command_class in legacy_readonly or command_class in legacy_git_readonly
        if is_measured_readonly and name in ("diff", "cmp", "sort"):
            output_flag_operand=None
            for index, token in enumerate(parts[1:], 1):
                if token in ("-o", "--output") and index + 1 < len(parts):
                    output_flag_operand=parts[index + 1]
                elif token.startswith("--output="):
                    output_flag_operand=token.split("=", 1)[1]
                elif token.startswith("-o") and token != "-o" and not token.startswith("--"):
                    output_flag_operand=token[2:]
            if output_flag_operand is not None and under(resolve(current_cwd, output_flag_operand)):
                is_measured_readonly=False
        if is_measured_readonly and name in ("uniq", "xxd"):
            positional_operands=collect_non_option_operands(parts, 1, set())
            if len(positional_operands) >= 2 and under(resolve(current_cwd, positional_operands[1])):
                is_measured_readonly=False
        if not is_measured_readonly and name in ("sed", "awk"):
            has_inplace = any(token == "-i" or token.startswith("-i") for token in parts[1:])
            has_external_script_file = any(token == "-f" or token.startswith("-f") for token in parts[1:])
            program_option_values = {"-v"} if name == "awk" else set()
            program_operands = collect_non_option_operands(parts, 1, program_option_values)
            has_unsafe_command = any(re.search(r"(^|[^A-Za-z])[wW](\s|$)", operand) for operand in program_operands)
            if name == "awk":
                has_unsafe_command = has_unsafe_command or any("system(" in operand for operand in program_operands)
            if not has_inplace and not has_external_script_file and not has_unsafe_command:
                is_measured_readonly=True
        if not is_measured_readonly and name == "python3" and not bare_dash_c:
            non_flag_args=[token for token in parts[1:] if not token.startswith("-")]
            if non_flag_args:
                first_arg=non_flag_args[0]
                if first_arg == "-" or not under(resolve(current_cwd, first_arg)):
                    is_measured_readonly=True
        if not is_measured_readonly:
            print("DENY\t"+command_class+"\tcommand is not in legacy read-only policy")
            raise SystemExit
print("ALLOW\t" + (last_command_class or "empty") + "\tread-only allowlist")
' <<<"$input")
parser_status=$?
if [ "$parser_status" -ne 0 ]; then
  blocked "cannot safely parse Bash command" "" unresolved_target
fi
decision=${result%%$'\t'*}
command_class=${result#*$'\t'}
command_class=${command_class%%$'\t'*}
reason=${result#*$'\t'*$'\t'}
if [ "$decision" = DENY ]; then
  if [ "$reason" = "unparseable command" ] || [ "$reason" = "cd target cannot be resolved" ]; then
    blocked "$reason" "$command_class" unresolved_target
  fi
  blocked "$reason" "$command_class" guarded_target
fi
mg_emit info product_path_guard pass read_only_command "$command_class" guarded bash
