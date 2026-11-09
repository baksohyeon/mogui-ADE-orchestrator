# Memory `[[name]]` Link Check

`scripts/memory-link-check` sorts every missing `[[name]]` memory link by
why it is missing: a missing name is allowed by design. By default only
`typo` and `invalid` fail; `tracker-key` fails too under
`--strict-tracker-keys`. A `[[name]]` inside a fenced block or an inline
code span (for example a TOML `[[table]]` name) is not collected.

Run before committing a memory mirror, or by hand on the live directory.

## Usage

```bash
scripts/memory-link-check --memory-dir memory/ --bd-keys tracker-keys.txt
```

`--bd-keys` (optional): tracker memory keys, one per line, `-` for stdin.
`--max-distance`: Levenshtein distance counted as a typo (default 2).

## Groups, checked in this order

- `invalid`: a path separator in the name, or an existing target that is
  not a regular file. Never resolves to a plain file; fix the link.
- `tracker-key`: the name is in `--bd-keys`. Checked before `typo`: an
  explicit key outranks a guessed near-miss. Point the link at the key's
  detail document, or leave it.
- `typo`: within `--max-distance` of an existing file name. A tie between
  two equally close names is reported as a tie, not dropped. Fix the link.
- `not-yet-written`: none of the above. Leave it alone.

## Exit codes

- `0`: `typo` and `invalid` are empty, and `tracker-key` is empty or
  `--strict-tracker-keys` was not passed.
- `1`: `typo` or `invalid` is non-empty, or `--strict-tracker-keys` was
  passed with a non-empty `tracker-key`.
- `2`: a usage error (non-directory `--memory-dir`, negative
  `--max-distance`), or a memory file or `--bd-keys` source that cannot be
  read or is not valid UTF-8; the error names the file.
