# Merge-Ready: One Measurement For A Pull Request

`scripts/merge-ready` measures one pull request and exits non-zero unless it may merge without
asking the owner (#330). A worker runs it on its own PR before `worker_done`; the master runs it
again before merge. Neither side's own claim that a PR is ready substitutes for this run. Every
check, review, thread, changed-file, and comment measurement is gathered again after the tarball
test re-run finishes, and the PR's head is re-read at that point too: a push landing mid-run
invalidates everything gathered before it, so this script measures the head that is actually
there when it finishes, never the one it started with. The one exception is the stop list and
the `--contract` writes-scope check (measurement 5 below): both run once, early, from the diff
alone, before the test re-run starts; when either already decides "ask", the test re-run never
happens at all, and the summary line says so, since no PR code should run on this machine before
the owner has even been asked whether this diff is allowed to run anywhere.

## Usage

```bash
scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>] [--test-command <cmd>]
```

`--contract <file>` adds the contract-scope check under "What it measures" below (any changed
path outside that contract's `writes` globs asks the owner). `--test-command <cmd>` overrides the
test command this script would otherwise choose for `<owner/name>` (see "Test command" below);
pass it for a repository this script does not know, or from a test harness.

A dispatched worker's cwd is a product-repo worktree, not this ops repo, so the
`merge-ready-before-done` standing rule's text names this script by a relative path that would
not resolve there; `scripts/dispatch` rewrites it to this install's own absolute `scripts/`
directory before the brief ships, so the worker never needs to know where this repo lives.

## What it measures

0. **The PR itself is open and not a draft.** `state` must be `OPEN` and `isDraft` must be
   false; a closed, merged, or draft PR is not ready, named as such, regardless of what else
   passed.
1. **Required checks.** Every entry `gh pr checks --required` reports (branch protection's own
   required-check list) must have bucket `pass`. No exemption of any kind, from the PR body or
   anywhere else: a required check that is pending or failing blocks, full stop. An empty-but-
   parseable `[]` response is also not ready (`require_json ... nonempty-list`): a required-check
   list with nothing in it to measure is not the same thing as every required check having
   passed, and nothing should read that shape as a free pass. A check this repository runs but
   does not require (a review bot, a label/assignee check) never reaches this measurement at
   all. Every bot (GraphQL `author.__typename == "Bot"`, not a login-suffix guess) whose *latest
   decision* review on the exact head commit is `PENDING` or `CHANGES_REQUESTED` blocks
   separately; only `APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`, or `PENDING` count as a
   decision, so a plain `COMMENTED` review from the same bot on the same commit, earlier or
   later, never changes which decision is the latest one.
1b. **The review-bot roster.** Every login in `config/merge-ready-bots.txt` must show some
   engagement with the exact head: a GraphQL review on it (any state, including a plain
   `COMMENTED` one, which measurement 1 does not treat as a decision but which still proves the
   bot looked at this commit), or an issue comment posted or last edited at or after the head
   commit's own committer timestamp. The "or last edited" half matters in practice: cubic and
   CodeRabbit both post one issue comment per PR and edit it in place on every push rather than
   posting a fresh one each time, so a comment's `updated_at` is the field that actually moves on
   the push this measurement cares about; comparing only `created_at` would read that bot's
   genuine, just-updated comment as stale. The REST issue-comments API reports a bot's login with
   a `[bot]` suffix (`coderabbitai[bot]`) that the GraphQL API does not (`coderabbitai`); both
   sides are compared with that suffix stripped. A bot with no review and no qualifying comment
   is not ready, naming the bot. An issue comment matching "review limit reached" or "rate
   limited by" (case-insensitive) counts the same as any other qualifying comment from that bot;
   the script does not distinguish the two kinds in its verdict (the contract names the
   rate-limit phrasing specifically so a bot that could not actually review still reads as
   covered, not as a separate, weaker kind of coverage this script enforces differently). An
   empty bots file fails closed
   the same way an empty stop-paths file does (see measurement 5), for the same reason: a worker
   with shell access could otherwise blank it out and neutralize the whole roster check.
2. **Open review threads.** `reviewThreads(isResolved)` on the head must show zero unresolved
   threads.
3. **The test suite, re-run from a tarball of the head**, not from whatever is checked out
   locally. `tests/test_context_quality_scripts.py::test_context_quality_sampler_relative_anchor_git_log_works`
   is deselected because it needs a `.git` directory a tarball extraction does not have; that is
   the one exception named in the contract. Never runs at all when measurement 5 already decided
   "ask" from the diff alone (see "Early stop-list check" below).
4. **A master-pass marker on the exact head**, distinct from the worker's own pre-check marker.
   A PR comment must contain the line `merge-ready-master-pass sha=<40-hex head sha>
   critical=<N> important=<N>`. The newest matching line across all comments wins. Missing, for
   the wrong sha, or `critical > 0` or `important > 0`: not ready. The worker's own
   `merge-ready-worker-pass` marker (see "The markers" below) never satisfies this measurement;
   only the master's marker does.
5. **Stop-list paths, checked both early and again at the end.** Any changed path matching
   `config/merge-ready-stop-paths.txt` is "ask", never "merge": the charter, the workspace card,
   role state, the boot comparison set, the scanner and redaction config, CI workflow and
   CODEOWNERS definitions, succession/bootstrap code, guard hooks, gate code, the tier policy,
   and worker settings. A stop-paths file that parses but names no real entries (blank or all
   comments) is not ready, not read as "nothing to block". With `--contract`, any changed path
   outside that contract's own `writes` globs (read only from its opening front-matter block,
   never from an example elsewhere in the contract's body text) is also "ask"; a contract with no
   `writes:` field in its front matter is not ready instead, since there is no declared scope to
   check against, not a stop-list hit.

## Early stop-list check

The stop list and the `--contract` writes-scope half of measurement 5 run once, immediately after
resolving the PR's head sha, before the tarball test re-run: a diff that was always going to be
"ask" should not cost a full test re-run first. When either decides "ask" at this point, the
script prints its verdict with `; tests not run (stop list decided before the test re-run)`
appended and exits 2 immediately; the required-checks, bot-roster, review-thread, and marker
measurements never run either, since there is nothing left to decide once the owner must be
asked. The same two checks run again, unconditionally, at the very end against whatever files the
head actually has once the test re-run is over: a stop-listed file that lands only via a push
mid-run is still caught there, the early pass is purely an optimization for the common case where
the diff decides the outcome from the start.

## Test command

Chosen per repository by a `case` statement inside the script, keyed on `--repo`:
`mogui-ADE-orchestrator` gets `PYTHONPATH=src python3 -m pytest tests -q` with the one deselect
above baked in. A repository this script does not know has no default and is "not ready" with
that reason, unless `--test-command` supplies one. A command passed with `--test-command` runs
exactly as given, with no deselect added for it. A tarball that cannot be fetched or extracted is
a test-re-run failure like any other, not an immediate exit, so a stop-list hit discovered
afterward still wins (exit 2) the same way it would if the tests had merely failed.

## The markers

There are two, never interchangeable, because master and workers share one GitHub account and
the marker name is the only thing that tells them apart:

- `merge-ready-worker-pass sha=<full head sha> critical=<N> important=<N>`: the worker's own
  pre-check, posted after its own independent review pass, before `worker_done`. This marker is
  an informational attestation only; `scripts/merge-ready` never reads it for measurement 4, and
  posting it never advances a PR toward exit 0 on its own.
- `merge-ready-master-pass sha=<full head sha> critical=<N> important=<N>`: the master's own,
  posted only after the master's own independent review. This is the only marker measurement 4
  checks. A worker must never post this one; doing so would be exactly the self-report this
  script exists to not trust, just moved from a completion message into a PR comment.

Either marker as a PR comment (or as a line inside a longer, human-readable review comment) right
after finishing the matching review pass, substituting the real head sha and the Critical/
Important counts that pass found. The sha ties a marker to one exact commit: a comment posted
before the last push does not count for the current head, and merge-ready always reads the
newest matching line of the kind it is looking for, so a fix round that posts a fresh marker
supersedes an older one of the same kind without having to delete it.

## Exit codes

- `0` merge: every measurement passed and no stop-list path was touched.
- `1` not ready: a measurement failed, a `gh` call could not be read or parsed, or the invocation
  itself could not run (bad usage, `gh`/`python3` missing, an unreadable `--contract`, stop-paths,
  or bots file). `2` is reserved for "ask" alone; nothing that merely failed to run is close
  enough to "ask the owner" to share its exit code.
- `2` ask the owner: a changed path matches the stop list, or (with `--contract`) falls outside
  the contract's `writes` globs. When the early check (see "Early stop-list check" above) decides
  this from the diff alone, the test re-run never runs at all; the same check also runs again at
  the very end, against whatever the head actually has once the test re-run is over, and can
  still exit 2 there, after the test re-run already ran, if a push mid-run introduced the hit.

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

The master-pass marker (measurement 4) is read from any PR comment; this script has no way to
tell a review pass the master actually ran from a marker typed by anyone who happens to have
push access to the same GitHub account, the same honest gap `scripts/land`'s own runbook names
for a gate that "exits 0 without actually testing anything": merge-ready trusts that whoever
posts `merge-ready-master-pass` is the master and ran a real review, the way it trusts the
operator's `--test-command` to actually be the real test suite. The worker/master marker split
(#330 round 2) narrows this from "anyone posting any marker" to "anyone posting the specific
master-named marker", which is a convention enforced by naming, not an identity check this script
can verify.

The review-bot roster's "for the head or newer" timing bound (measurement 1b, compared against
the later of a comment's `created_at` and `updated_at`) is an approximation: a REST issue comment
carries no commit reference at all, so the head commit's own committer timestamp is the closest
available proxy for "this comment is about the current push", not a guarantee. A bot that
re-posts or re-edits an old comment's text verbatim after a genuinely new push, or whose
comment's timestamp the GitHub API reports with clock skew, would read the same way a comment
truly about the new head does; a PR author who can set their own head commit's committer date
(`GIT_COMMITTER_DATE` is fully author-controlled) could in principle backdate it to make an old
bot comment appear to qualify, though this has not been demonstrated end to end against this
script.

A contract's `writes:` field schema-validly accepts an explicit empty list (`writes: []`,
declaring that nothing is in scope); both the early and the final stop-list/writes-scope checks
treat that the same way, as every changed path being outside scope, never as "no list, so
nothing to check" (that reading is reserved for a genuinely missing `writes:` field, which is a
not-ready case, not an ask). The early check's own stop-list/writes-scope pass is a second,
independent read of the same two rules the final aggregator applies; if that early pass itself
fails to run to completion for any reason other than deciding 0 (proceed) or 2 (ask), the script
treats that as not ready rather than silently falling through to the test re-run as if the early
pass had cleanly passed.

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
the stop list when it is absent, and that path is resolved once, relative to this script's own
install location, with no environment override: a worker with ordinary shell access could
otherwise point an override at an empty file and neutralize the stop list entirely.

The test re-run executes the PR's own code (`eval "${TEST_CMD}"`, run from the extracted tarball)
with the same filesystem privileges as the rest of this script, under a working directory one
level below a predictable, fixed set of sibling temp-file names (`checks.json`, `graphql.json`,
and so on) that this script itself only writes to *after* the test command has already run. Right
before any of step 3's `gh` calls run, this script checks that none of its own sibling output
paths already exist (a real file or a symlink, dangling or not); if one does, it refuses rather
than writing through it. `set -C` (`noclobber`), set near the top of the script, backs this for
the bash-redirected writes, but the explicit check, not `set -C` alone, is the actual fix: `gh pr
checks` legitimately exits non-zero on a merely *failing* (not unreadable) required check while
still printing valid JSON, so the fallback a few lines below that tolerates that exact shape would
also have tolerated a file the test command planted ahead of time, parsed as valid JSON, and never
actually queried from `gh` at all -- a real, demonstrated way to reach `0` on a failing required
check, found and closed before merge. The explicit check also covers the paginated-response
flatten step's Python-side `open(path, "w")` writes, which `set -C` does not reach at all, since
noclobber is a bash shell property, not a filesystem one. The one place this script writes the
same path twice on purpose (`fetch_paginated_array`'s own stderr file, once for the `gh` call and
again for the flatten step that follows it) uses `2>|` to say so explicitly, rather than tripping
its own tamper check on a write it intended.

Reviews and review threads are read up to 100 each; a PR past either limit is "not ready, rerun
with pagination" rather than measured on a partial page, but this script does not implement
cursor pagination to go further, the same scope limit `scripts/pr-steward-status` already
accepts for the same data. The `gh` calls and the test re-run itself have no timeout, so a hung
request or a hung test blocks the verdict until something else kills the process; wrapping the
test command in a timeout was considered and left out, since GNU `timeout` is not reliably
present on every machine this script runs on (macOS ships none by default, only `gtimeout` from
a separate Homebrew install).

Only a review in `APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`, or `PENDING` state updates a bot's
standing state for this measurement; a plain `COMMENTED` review (a remark with no decision)
leaves a prior `CHANGES_REQUESTED` or `PENDING` in force, the same way GitHub's own review-decision
model treats a comment as not clearing a standing decision.

`--contract`'s `writes:` field is schema-optional (`dispatch_gate.py` records it but does not
require it), yet the `merge-ready-before-done` standing rule tells a worker to always pass
`--contract` when the task delivered one, and a contract with no `writes:` then reads not ready
with no way for the worker to fix it by editing its own delivered contract. Measured against 198
historical contracts with a front-matter block: all 198 already include `writes:`, so this is a
latent schema gap, not an observed failure, and is not tightened further here.
