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

The operator's own line keeps its tokens: a redirect into a product root on
that line (`cat > <root>/file <<'EOF'`) still denies. When the operator line
is a bare interpreter invocation with no `-c` — `bash <<'EOF'`, `python3
<<'EOF'` — the heredoc body is the whole script, exactly as opaque as a `-c`
body, so it gets the same scrutiny before being stripped: a `cd`, a root
substring anywhere in the body, or a redirect into the root denies the
command outright (`opaque interpreter heredoc body may contain an unparsed
write`), applied regardless of mode. A heredoc consumed as plain data by a
non-interpreter command, or as stdin data alongside an explicit `-c` script,
is not treated this way — only an interpreter reading its own code from the
heredoc is.

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
resolves into the root.

`sed` and `awk` are admitted through a separate branch, not the
`legacy_readonly` set: only without `-i`, without `-f` (an external script
file this guard cannot read the contents of), and without an unsafe
construct in the inspected program text: a `w`/`W` command for either, or a
`system(` call for `awk` specifically (`awk 'BEGIN{system("rm ...")}'` would
otherwise execute a write without ever naming a write-capable command). Any
one of these keeps the denial (an in-place edit is already caught earlier as
write-capable when it touches the root).

`python3` admits, when it reaches this gate (see above — cwd under the root
is the common way), only when it has no `-c` argument and its first
non-flag argument is `-` or resolves outside every product root.

`git branch` admits only the exact `--show-current` invocation; any other
`git branch` invocation (creating, deleting, renaming a branch) is still a
write and is unaffected by this addition.

## Testing

`scripts/test-product-path-guard.sh` covers a pass/deny pair per shape above,
plus dedicated cases for `git blame`, `git worktree list`, `git fetch`,
`git branch --show-current`, and `git branch <name>` staying denied.

## Further Reading

- Hook fire coverage: [hook-fire-observability.md](hook-fire-observability.md)
