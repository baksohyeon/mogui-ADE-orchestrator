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
the tokenizer into a fail-closed "unparseable command" denial. The operator's
own line keeps its tokens: a redirect into a product root on that line
(`cat > <root>/file <<'EOF'`) still denies. A `<<<` here-string is not a
heredoc and is untouched. If a heredoc's terminator is never found, the
command is still treated as unparseable, exactly as before this change.

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

`legacy_readonly` gained `diff`, `cmp`, `comm`, `sed`, `awk`, `wc`, `sort`,
`uniq`, `cut`, `tr`, `shasum`, `sha256sum`, `md5`, `xxd`, `od`, `less`,
`more`, `jq`, and `git blame`, `git cat-file`, `git ls-tree`, `git
merge-base`, `git merge-tree`, `git rev-list`, `git branch --show-current`,
`git worktree`, `git fetch` joined `legacy_git_readonly`. `sed` and `awk`
admit only without `-i` and without a `w`/`W` command in the program text;
either one keeps the denial (an in-place edit is already caught earlier as
write-capable when it touches the root). `python3` admits only when it has no
`-c` argument and its first non-flag argument is `-` or resolves outside
every product root; a script path inside the root, or any `-c`, still denies.
`git branch` admits only the exact `--show-current` invocation; any other
`git branch` invocation (creating, deleting, renaming a branch) is still a
write and is unaffected by this addition.

## Testing

`scripts/test-product-path-guard.sh` covers a pass/deny pair per shape above,
plus dedicated cases for `git blame`, `git worktree list`, `git fetch`,
`git branch --show-current`, and `git branch <name>` staying denied.

## Further Reading

- Hook fire coverage: [hook-fire-observability.md](hook-fire-observability.md)
