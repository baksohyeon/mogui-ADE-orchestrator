# Product Path Guard

`scripts/hooks/product-path-guard.sh` is a `PreToolUse(Edit|Write|NotebookEdit|Bash)`
hook that denies a file-tool write into a configured product root, and denies
a Bash command whose best-effort parse shows it touching one. In legacy mode
(`MOGUI_PRODUCT_GUARD_FAIL_CLOSED` unset or `0`) a command that touches a
product root must also match a known read-only shape or it is denied; in
fail-closed mode (`MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1`) it must be in the
measured allowlist at `scripts/hooks/product-path-guard-readonly-allowlist.txt`
instead. The three shapes below are legacy-mode admissions only: none of them
widen fail-closed mode.

## Heredoc bodies

A heredoc body (`<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"`, `<<\WORD`) is
stripped, terminator line included, before the command is tokenized. Prose in
the body — an apostrophe, unbalanced quotes, anything — can no longer break
the tokenizer into a fail-closed "unparseable command" denial. Detecting the
operator itself is quote-and-comment-aware (`printf "%s" "use <<EOF"` is not
a heredoc, since the `<<` sits inside a double-quoted string; `echo hi # see
<<EOF below` is not one either, since it follows an unquoted `#` — this one
matters: without it, a real command on the next line could be misread as the
comment's "heredoc body" and silently dropped from the guard's view while
Bash still executes it) and does not require whitespace before `<<`
(`cat<<EOF` is recognized same as `cat << EOF`). A `<<<` here-string is not a
heredoc and is untouched. If a heredoc's terminator is never found, the
command is still treated as unparseable, exactly as before this change.

An operator preceded by an odd run of backslashes (`ls \<<EOF`) is not a
heredoc: bash reads an escaped `<` as a literal plus an input redirection, so
the following lines stay commands. A backslash-newline line continuation
inside the body is removed first, matching bash's own removal, so a `$(` or
backtick split across two lines by one still triggers the check below. When
the delimiter is unquoted (`<<EOF`), bash expands the body, so a body
containing `$(`, a backtick, or a `${...@P}` prompt-expansion transformation
is denied as unparseable (`heredoc body expansion`) instead of stripped; the
guard does not evaluate it. A bare `${...}` parameter expansion without
`@P` runs no code, so it does not trigger this check on its own. Under
`MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1` that check is unconditional; in legacy
mode the body instead gets the same `cd`,
product-root, and redirect-into-root scrutiny already applied to an
interpreter-fed heredoc body below, and is also denied when the hook's own
working directory is itself under a product root, since a relative write
that scrutiny cannot see would still land inside it; otherwise it is
admitted. The legacy-mode root test resolves a body token's path spelling
(an absolute path, a symlinked spelling, `~/...`, `$HOME/...`, a `./`- or
`../`-relative spelling, or a bare relative spelling with a slash) against
the hook's working directory instead of matching the configured root's exact
realpath string, so a spelling that never contains that string still denies.
A bare directory name with no slash at all (`$(cp source product-root)` with
the working directory beside the root) is not resolved by this test and is a
known gap left for a later round.
A quoted delimiter (`<<'EOF'`, `<<"EOF"`, `<<\EOF`) keeps the body
literal and it is stripped as before.

The operator's own line keeps its tokens: a redirect into a product root on
that line (`cat > <root>/file <<'EOF'`) still denies. When the operator line
is a bare interpreter invocation with no `-c` — `bash <<'EOF'`, `python3
<<'EOF'` — the heredoc body is the whole script, exactly as opaque as a `-c`
body, so it gets the same scrutiny before being stripped: a `cd`, the same
path-spelling resolution the legacy-mode unquoted heredoc body uses, or a
redirect into the root denies the command outright (`opaque interpreter
heredoc body may contain an unparsed write`), applied regardless of mode. The interpreter need not be the line's
first token: the operator line is segmented on `;`/`&&`/`||`/`|`/`&`, the
same way the main parser segments a whole command, so `true && bash
<<'EOF'`, `cd /tmp; python3 <<EOF`, and `echo x | sh <<EOF` all get scrutiny
on whichever segment carries the redirect. A heredoc consumed as plain data
by a non-interpreter command, or as stdin data alongside an explicit `-c`
script, is not treated this way — only an interpreter reading its own code
from the heredoc is.

## Interpreter arguments

An interpreter command (`bash`, `sh`, `dash`, `ksh`, `zsh`, `python`,
`python3`, `perl`, `ruby`, `node`) no longer denies merely because some
argument's text contains a product root. A plain argument is a write shape,
and still denies, only when a product path follows `-o`, `--output`, or a
literal `>` inside that same argument token, or when it is inside a `-c` body
that a known writer (`cp`, `mv`, `tee`) would write to. A plain argument with
no such shape is a read: the interpreter is given a path to open, and opening
is not writing. This also means a plain argument naming a product path is no
longer counted as a touch on its own — the command still denies if it touches
the root some other way (cwd under the root, a redirect, a `-o`/`--output`
flag). A `-c` body is otherwise unchanged: it still denies on a `cd`, a root
substring anywhere in the body, or a redirect into the root, and a bare `-c`
run from a cwd under the root is still denied unconditionally, matching the
fail-closed rule.

## Legacy read-only policy

This section covers commands that reach the `legacy_readonly`/
`legacy_git_readonly` gate — that is, a command that touches a product root
some way other than a plain interpreter argument (shape 2 above already
admits that case without reaching this gate at all: `python3
<root>/script.py` from a cwd outside the root is a read regardless of this
section, since the argument alone is never counted as a touch).

`legacy_readonly` gained `diff`, `cmp`, `comm`, `wc`, `sort`, `uniq`, `cut`,
`tr`, `shasum`, `sha256sum`, `md5`, `xxd`, `od`, `less`, `more`, `jq`; `git
blame`, `git cat-file`, `git ls-tree`, `git merge-base`, `git merge-tree`,
`git rev-list`, `git branch --show-current`, `git worktree`, `git fetch`
joined `legacy_git_readonly`. `git worktree` is listed as its raw command
class, but `git worktree add`/`remove`/etc. are still independently caught
and denied as write-capable before this gate is reached — in practice only
`git worktree list` passes. `diff`/`cmp`/`sort` lose the admission if an
`-o`/`--output` flag resolves into the root (`sort -o <root>/out` writes
there, unlike its other listed siblings); `uniq`/`xxd` lose it if their
second positional operand — an optional output file, not an input file —
resolves into the root, after first accounting for each command's own
value-taking options (`-s`, `-f`, `-w` for `uniq`; `-s`, `-l`, `-c`, `-g` for
`xxd`) so a flag's value is never mistaken for that operand.

`sed` and `awk` are admitted through a separate branch, not the
`legacy_readonly` set: without `-i` anywhere in a combined short-flag
cluster (`-ni` disqualifies just as `-i` alone does), without `-f` (an
external script file this guard cannot read the contents of), and without an
unsafe construct in the inspected program text. For `sed` that is a `w`, `W`,
or `e` command — `w`/`W` need not be followed by whitespace (`s/a/b/w/path`
is a valid write with no space before the filename), and `e` (standalone or
as the `s///e` flag) executes its match as a shell command. For `awk` that is
a `system(` call, or a literal `>` or `|` in the program text (`print >
file`, `print | "cmd"`, and `"cmd" | getline` are program-level I/O and
command execution this guard has no other way to see). Any one of these
keeps the denial (an in-place edit is already caught earlier as write-capable
when it touches the root).

`python3` admits, when it reaches this gate (see above — cwd under the root
is the common way), only when it has no `-c` argument and its first
non-flag argument is `-` or resolves outside every product root.

`git branch` admits only the exact `--show-current` invocation; any other
`git branch` invocation (creating, deleting, renaming a branch) is still a
write and is unaffected by this addition.

## Worker mode

A dispatched worker is guarded by the same hook with the territory flipped.
When `MOGUI_WORKER_WRITE_ROOT` is set to an absolute path, everything outside
that root is guarded and `product_repositories` is not read (a worker's
worktree sits under a product root by design, and worker mode does not need
the runtime config at all). A file-tool write whose target resolves outside
the root is denied. A Bash command whose best-effort parse shows a write
target outside the root is denied, with the same legacy read-only admissions
master mode has: `cat`, `git -C <master checkout> status`, and the rest of
that list still pass against a path outside the root, while
`git -C <master checkout> reset --hard` does not. Four device files stay writable, `/dev/null`, `/dev/stdout`,
`/dev/stderr`, and `/dev/tty` (compared resolved), so `2>/dev/null` is not a
denial; any other `/dev` path, `/dev/shm` included, is outside the root. When
the deny rests on a path outside the root (a write target, a redirect
target, or the touching path of a read-only-policy deny), the denial text
names that path and the root; otherwise it carries no path, so a read
operand is never named as the cause. A relative or empty-after-resolution root fails closed.
An empty or unset `MOGUI_WORKER_WRITE_ROOT` is not this failure: it means master mode,
not a refusal, and a newly created Claude pane gets a non-empty, absolute path; reused panes and
other runtimes are not covered by this settings file.

What it leaves out, by design or as a known gap:

- `cd` to a directory outside the root is denied by the existing legacy rule
  for entering guarded territory; reach another checkout with `git -C`
  instead. `cd` back into the root is admitted, so a worker whose shell cwd
  drifted outside can recover.
- The raw root-substring heuristics are off in worker mode, since mentioning
  the root is the normal case there. An opaque interpreter body
  (`python3 -c "open('/elsewhere', 'w')"`) is therefore admitted unless it
  carries a redirect or `cd` the parser can see; this is best effort, like
  every Bash parse in this hook.
- Temporary files outside the worktree (a host scratchpad, `/tmp`) are
  outside the root and denied. A worker keeps its temporary files inside its
  worktree, untracked.

### How a worker gets it

`scripts/dispatch` writes one settings file per claude dispatch at
`~/.mogui/worker-settings/<task-id>.json` (under `MOGUI_STATE_DIR` when that
seam is set), never inside the worktree and never committed, and launches the
worker with `claude ... --settings <that file>`. The file carries two
`PreToolUse` matchers, `Edit|Write|NotebookEdit` and `Bash`, each running
this hook as `MOGUI_WORKER_WRITE_ROOT=<worktree> MOGUI_RUNTIME_HINT=claude
<scripts>/hooks/product-path-guard.sh`. It holds the worktree path and the
hook path only: no pane handle, no token, no secret.

A reused pane (`--terminal`) is not covered: its claude is already running,
so `--settings` cannot reach it, and rewriting the file it launched with
does not either (measured 2026-11-10 on claude 2.1.319: after the file was
repointed at a new root, the running pane still refused writes against its
launch-time root). `dispatch` writes no file for a reused pane and prints
`write root: not enforced on a reused pane`; dispatch to a new pane when the
task needs its write root. No cleanup
path removes the file today: `worker-reap` lives in `src/` and was outside
this change, so the files accumulate one per claude dispatch until a later
round adds removal there.

Codex workers receive their write root from the workspace-write sandbox through
`--approve-for-me` (measured 2026-11-11); `codex_bypass_approvals_and_sandbox: true`
selects the unsandboxed bypass path. An eligible sandbox escalation under
`--approve-for-me` is decided by the Codex automatic reviewer, not by a human;
whether it ever approves a write outside the worktree is unmeasured; one
observation on 2026-11-12 recorded 7 `~/.mogui` writes denied with none escalated.

## Testing

`scripts/test-product-path-guard.sh` covers a pass/deny pair per shape above,
plus dedicated cases for `git blame`, `git worktree list`, `git fetch`,
`git branch --show-current`, and `git branch <name>` staying denied, and a
worker-mode block: a file-tool write and a Bash redirection inside the root
pass, the same two outside the root deny and name the root and the path.

## Further Reading

- Hook fire coverage: [hook-fire-observability.md](hook-fire-observability.md)
