# Memory `[[name]]` Link Check

`scripts/memory-link-check` finds every `[[name]]` link in a memory
directory's `*.md` files whose target file does not exist, and sorts each
missing name into a group that says why it is missing. A missing name is
allowed by design (it marks something worth writing later); only a
near-miss on an existing file name is a defect.

Run it before committing a memory mirror into an operations repository, or
by hand against the live memory directory.

## Usage

```bash
scripts/memory-link-check --memory-dir memory/
scripts/memory-link-check --memory-dir memory/ --bd-keys tracker-keys.txt
```

`--bd-keys` takes a file of tracker memory keys, one per line (`-` for
stdin). `--max-distance` sets the Levenshtein distance counted as a typo
(default 2).

## Groups

- `typo`: an existing file's name is close enough (within `--max-distance`)
  that this is probably a misspelling. Fix the link.
- `tracker-key`: the name is in `--bd-keys`, naming a short rule kept in
  the tracker's own memory store. Point the link at that key's detail
  document if it has one; otherwise leave it.
- `not-yet-written`: a name reserved for something not written yet. Leave
  it alone.

## Exit codes

- `0`: `typo` is empty (and, without `--strict-tracker-keys`, regardless of
  the other two groups).
- `1`: `typo` is non-empty, or `--strict-tracker-keys` was passed and
  `tracker-key` is non-empty.
- `2`: usage or runtime error, for example a non-directory `--memory-dir`.
