# Product-path guard Bash write hardening report

Acknowledgement token: `ack-9c62568b271f`

## What the Bash branch did before this change

Before this patch, the Bash branch did parse and inspect the command string. It tokenized `tool_input.command` with `shlex`, split segments on shell control operators, resolved candidate paths against `working_directory`, denied known redirection writes, denied unparseable commands, denied opaque interpreter wrappers, and enforced legacy read-only command classes when `MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0`.

Measured gap before this patch: `dd if=/dev/null of=<product_root>/file.txt` returned `RC:0` because `dd` key-value output targets (`of=...`) were not recognized as write targets.

## Hook changes made

- Updated `scripts/hooks/product-path-guard.sh` to document Bash parsing as best effort and to list key blind spots.
- Classified explicit write-capable commands (`cp`, `mv`, `rm`, `rmdir`, `mkdir`, `install`, `ln`, `touch`, `truncate`, `tee`, `dd`) as write-capable for guarded-target checks.
- Added parsing for `dd` output targets via `of=...`.
- Expanded git mutation handling to include mutating subcommands while still permitting allowlisted read-only forms such as `git worktree list` in strict mode.
- Added regression coverage in `scripts/test-product-path-guard.sh` for `dd of=...`, `git reset --hard`, and strict allowlisted `git worktree list`.

## Covered write shapes (best effort)

The current Bash guard refuses these direct shapes when they target product paths:

- Shell redirections: `>`, `>>`, `2>`, `2>>`, `&>`, `>&`
- `tee <product_path>`
- `cp`, `mv`, `rm`, `mkdir`, `rmdir`, `install`, `ln`, `touch`, `truncate`
- `dd ... of=<product_path>`
- `sed -i` and `--in-place`
- Mutating git commands such as `git checkout`, `git reset --hard`, `git add`, `git commit`, `git merge`, `git rebase`, `git rm`, and mutating `git remote` actions
- `find ... -exec ...` write-capable patterns and opaque shell wrappers in `-exec`

## Uncovered or partial shapes

This parser is intentionally best effort and does not claim total write detection. Known uncovered or partial cases include:

- Shell variable expansion for targets where the product path appears only after runtime expansion (example below).
- Heredoc and sourced-script bodies that compute targets dynamically.
- Command substitution and nested shells that hide target paths from static token inspection.
- Command-specific key/value write flags beyond currently recognized forms (for example, tools that use nonstandard `key=value` output flags).

## Verification evidence

### Required behavior checks

```text
CASE:redirect_block
INPUT:echo bad > <product_root>/file.txt
RC:2
STDERR:[product-path-guard] BLOCKED: shell redirection is a write
```

```text
CASE:read_allow
INPUT:cat <product_root>/file.txt
RC:0
STDERR:(empty)
```

```text
CASE:own_workspace_write_allow
INPUT:printf ok > <caller_workspace>/file.txt
RC:0
STDERR:(empty)
```

### Demonstrated uncovered shape

```text
CASE:uncovered_env_expansion
INPUT:TARGET=<product_root>/file.txt cp /dev/null $TARGET
RC:0
STDERR:(empty)
```

Named uncovered shape: runtime shell variable expansion of write targets.

### Command verification

```text
$ bash scripts/test-product-path-guard.sh
product-path-guard regression tests passed
```

```text
$ python3 scripts/generate-manifest --check
<exit 0>
```

```text
$ PYTHONPATH=src python -m pytest tests -q
582 passed, 13 subtests passed in 43.66s
```
