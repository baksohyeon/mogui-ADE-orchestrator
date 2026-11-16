# Landing Commits Without a Pull Request

`scripts/land` carries one or more already-made commits onto a repository's `main` when that
repository takes commits without a PR, and it stops at the first failed step instead of chaining
commands whose exit code a later `|` or `;` could drop. A worker's own claim that a gate passed is
not accepted in place of this run; this is the master's re-run, on the commit that is about to
land on `main`.

## Usage

```bash
scripts/land --repo <path> --gate '<command>' <commit>...
```

`<path>` is the repository checkout to land into; `<command>` runs in that repository's root (for
example `PYTHONPATH=src python -m pytest tests -q`); `<commit>...` are one or more commit-ishes,
in the order they should land.

## Steps

In order, stopping at the first failure:

1. the checkout is on `main`, clean, and equal to `origin/main` after `git fetch origin`
2. `git cherry-pick` each commit; on conflict, abort the cherry-pick
3. run the gate in the repository root with its full output kept in a log file whose path is
   printed; continue only on exit `0`, read from the gate's own process, not from any line of
   its output (a truncated or misread line is how issue #318 happened)
4. confirm `origin/main` (as fetched in step 1) is an ancestor of `HEAD`
5. `git push origin main` (never `--force`)
6. fetch again and confirm `origin/main` now equals the local `HEAD`

Any failure after step 2 resets the checkout to the `origin/main` it started from and says so.
A failure in step 6 resets the checkout the same way, but the push in step 5 already went out by
then; the message names the sha that may already have landed on the remote.

## Exit Codes

- `0`: landed and pushed; `origin/main` confirmed equal to the local `HEAD`.
- `1`: a step above said no. The repository was not ready, the cherry-pick conflicted, the gate
  exited nonzero, the ancestor check failed, the push failed, or the post-push confirmation
  failed; the checkout is reset to the sha it started from in every one of these cases.
- `2`: the check could not run at all: bad usage, the repository path given is not a git
  checkout, a commit argument does not resolve, `git fetch` failed, or an internal step (reading
  `HEAD`, writing a log file, verifying a reset) failed.

## Honest Limit

The gate is whatever command the caller passes; `land` only trusts its exit code. A gate that
itself exits `0` without actually testing anything will still land.
