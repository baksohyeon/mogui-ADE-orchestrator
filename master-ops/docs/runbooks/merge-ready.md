# Merge-Ready: One Measurement For A Pull Request

`scripts/merge-ready` measures one pull request and exits non-zero unless it may merge without
asking the owner (#330). A worker runs it on its own PR before `worker_done`; the master runs it
again before merge. Neither side's own claim that a PR is ready substitutes for this run.

## Usage

```bash
scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>] [--test-command <cmd>]
```

`--contract <file>` adds stop-list item 3 (any changed path outside that contract's `writes`
globs asks the owner). `--test-command <cmd>` overrides the test command this script would
otherwise choose for `<owner/name>` (see "Test command" below); pass it for a repository this
script does not know, or from a test harness.

A dispatched worker's cwd is a product-repo worktree, not this ops repo, so the
`merge-ready-before-done` standing rule's text names this script by a relative path that would
not resolve there; `scripts/dispatch` rewrites it to this install's own absolute `scripts/`
directory before the brief ships, so the worker never needs to know where this repo lives.

## What it measures

1. **Required checks and review bots.** Every entry `gh pr checks --required` reports (branch
   protection's own required-check list) must have bucket `pass`, except a check named on a
   `rate-limited: <name>[, <name>...]` line in the PR body (case-insensitive, comma-separated);
   that is the only skip. A check this repository runs but does not require (a review bot, a
   label/assignee check) never reaches this measurement at all. Every bot (GraphQL
   `author.__typename == "Bot"`, not a login-suffix guess) that reviewed the exact head commit
   must not be `PENDING` or `CHANGES_REQUESTED`.
2. **Open review threads.** `reviewThreads(isResolved)` on the head must show zero unresolved
   threads.
3. **The test suite, re-run from a tarball of the head**, not from whatever is checked out
   locally. `tests/test_context_quality_scripts.py::test_context_quality_sampler_relative_anchor_git_log_works`
   is deselected because it needs a `.git` directory a tarball extraction does not have; that is
   the one exception named in the contract.
4. **A recorded review pass on the exact head.** A PR comment must contain the line
   `merge-ready-review-pass sha=<40-hex head sha> critical=<N> important=<N>`. The newest matching
   line across all comments wins. Missing, for the wrong sha, or `critical > 0` or `important >
   0`: not ready.
5. **Stop-list paths.** Any changed path matching `config/merge-ready-stop-paths.txt` is "ask",
   never "merge": the charter, the workspace card, role state, the boot comparison set, the
   scanner config, guard hooks, gate code, the tier policy, and worker settings. With
   `--contract`, any changed path outside that contract's `writes` globs is also "ask".

## Test command

Chosen per repository by a `case` statement inside the script, keyed on `--repo`:
`mogui-ADE-orchestrator` gets `PYTHONPATH=src python -m pytest tests -q` with the one deselect
above baked in. A repository this script does not know has no default and is "not ready" with
that reason, unless `--test-command` supplies one. A command passed with `--test-command` runs
exactly as given, with no deselect added for it.

## The marker

Post `merge-ready-review-pass sha=<full head sha> critical=<N> important=<N>` as a PR comment
(or as a line inside a longer, human-readable review comment) right after finishing a review
pass, substituting the real head sha and the Critical/Important counts that pass found. The
sha ties the marker to one exact commit: a comment posted before the last push does not count
for the current head, and merge-ready always reads the newest matching line, so a fix round that
posts a fresh marker supersedes an older one without having to delete it.

## Exit codes

- `0` merge: every measurement passed and no stop-list path was touched.
- `1` not ready: a measurement failed, a `gh` call could not be read or parsed, or the invocation
  itself could not run (bad usage, `gh`/`python3` missing, an unreadable `--contract` or
  stop-paths file). `2` is reserved for "ask" alone; nothing that merely failed to run is close
  enough to "ask the owner" to share its exit code.
- `2` ask the owner: a changed path matches the stop list, or (with `--contract`) falls outside
  the contract's `writes` globs. Ask wins over not-ready when both are true, since the owner
  decides regardless of what else failed.

One summary line on stdout, prefixed `merge-ready: merge ·`, `merge-ready: not ready ·`, or
`merge-ready: ask ·`, names every failing or asking item.

## Honest limits

`gh pr checks --required` conflates two different situations behind the same shape: a branch
with genuinely no required checks configured, and a branch whose required checks exist but have
not posted a single check-run yet (a PR that was just opened, before CI starts). Both print no
JSON at all and exit non-zero with "no required checks reported on the '<branch>' branch", so
this script cannot tell them apart and treats both as not ready rather than guessing that nothing
is required; a freshly opened PR reads as not ready until its required checks have started
reporting, which is correct for the common case even though it is also conservative for the rare
one.

The review-pass marker (measurement 4) is read from any PR comment; this script has no way to
tell a review pass an independent reviewer actually ran from one the worker invented to satisfy
the check, the same honest gap `scripts/land`'s own runbook names for a gate that "exits 0
without actually testing anything": merge-ready trusts that whoever posts the marker ran a real
review, the way it trusts the operator's `--test-command` to actually be the real test suite.

`--contract`'s `writes` globs match with Python's `fnmatch`, whose `*` already crosses `/`, so
`a/**` and `a/*` match the same set of paths; a contract relying on `**` meaning "this directory
only, not deeper" would be matched more loosely than it reads. The stop list and the `writes`
check only look at changed *paths* (both the new and, for a rename, the old name); a change that
stays inside an allowed path but still edits something stop-listed by content, not by location,
is not this script's job. `gh api .../pulls/.../files` caps out at 3000 entries with no error or
truncation signal; a PR past that size is measured on an incomplete file list.

`config/merge-ready-stop-paths.txt` lives in a directory `scripts/generate-manifest` never
lists as a template-installed file (`instance_owned`, see `rules/standing-rules.md`), so no
re-stamp, upgrade, or fresh onboarding install ever copies it in from the template on its own;
every install, old or newly onboarded, has to add this file by hand once, from this version.
`merge-ready` fails closed (not ready, naming the missing file) rather than silently skipping
the stop list when it is absent.
