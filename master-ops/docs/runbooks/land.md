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
2. `git cherry-pick` each commit; on conflict, abort the cherry-pick; record `picked`, the sha
   this produced, before anything else runs
3. run the gate in the repository root under `set -o pipefail`, with its full output kept in a
   log file whose path is printed; continue only on exit `0`, read from the gate's own process,
   not from any line of its output (a truncated or misread line is how issue #318 happened)
4. confirm the checkout is still on `main`, still at `picked`, and still clean; a gate that
   commits, amends, checks out something else, or leaves an edit on a tracked file without
   committing it fails this step
5. confirm `origin/main` (as fetched in step 1) is an ancestor of `picked`
6. `git push origin "${picked}:main"` (never `--force`), the sha the gate actually ran on, not
   whatever `HEAD` happens to be by then
7. fetch again and confirm `origin/main` now has `picked` as an ancestor

A step-1 failure (wrong branch, dirty checkout, or local `main` not equal to `origin/main`)
leaves the checkout exactly as it was found, since nothing has changed yet. Any failure from
step 2 onward resets the checkout to the sha it started from and says so, unless the checkout
holds uncommitted changes a `reset --hard` would destroy, in which case `land` refuses to reset
and prints `start_sha` and `picked` so the operator can recover by hand instead of losing that
work silently. That dirty check runs before `cherry-pick --abort` in every case except the
cherry-picks' own conflict in step 2, so a conflict the gate itself leaves unresolved in step 3
reads as a refusal (exit 2) instead of being discarded by the abort before `land` ever sees it.
A failure in step 7 resets the checkout the same way, but the push in step 6 already went out by
then; the message names the sha that may already have landed on the remote.

## Exit Codes

- `0`: landed and pushed; `origin/main` confirmed to have `picked` as an ancestor.
- `1`: a step above said no. The repository was not ready (step 1), the cherry-pick conflicted,
  the gate exited nonzero, the gate moved or dirtied the checkout (step 4), the ancestor check
  failed, the push failed, or the post-push fetch or confirmation (step 7) failed, and the
  checkout was reset back to the sha it started from. A step-1 failure leaves the checkout
  untouched, since nothing has changed yet.
- `2`: the check could not run at all, or could not safely recover from a failure: bad usage,
  the repository path given is not a git checkout, a commit argument does not resolve, a
  `--gate` that is empty or only whitespace, the pre-push `git fetch` (step 1) failed, an
  internal step (reading `HEAD`, writing a log file) failed, resetting the checkout itself
  failed, or a reset was refused because the checkout held uncommitted changes.

## Honest Limit

The gate is whatever command the caller passes; `land` only trusts its exit code, and that exit
code runs under `set -o pipefail`, so a pipeline inside the gate command reports its first
failing stage rather than only its last one. A gate that itself exits `0` without actually
testing anything will still land.

Step 4's clean check does not distinguish a tracked-file edit from an untracked build artifact;
anything a gate's own run leaves behind that is not already gitignored reads as the gate having
dirtied the checkout, and the run fails even though the gate itself passed. Point a repository's
`--gate` command at something that cleans up after itself, or gitignore what it leaves, before
wiring it into `land`.

Every cleanliness check passes `--ignore-submodules=none`, so a dirty submodule is not hidden by
a `submodule.<name>.ignore` setting in the repository's own config. Every cleanliness check also
treats an unfinished cherry-pick (`CHERRY_PICK_HEAD` or a `.git/sequencer` directory) as dirty on
its own, even when `git status --porcelain` itself is clean. A conflict resolved by staging a
result identical to `HEAD`, without running `cherry-pick --continue`, is otherwise invisible to a
plain status check.
