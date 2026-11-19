# Merge-Ready: One Measurement For A Pull Request

`scripts/merge-ready` measures one pull request and exits non-zero unless its GitHub state is ready
without asking the owner (#330). A worker runs it on its own PR before `worker_done`; the master
runs it again before merge. The command reads GitHub state and local gate configuration. It never
executes code from the pull request.

The master's independent review and head-tarball test are separate required steps. This command
does not attest to either step. After both steps pass, the master merges with
`gh pr merge --match-head-commit <sha>`, using the full head sha printed in this command's summary.

## Usage

```bash
scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>]
```

`--contract <file>` adds the contract-scope check: any changed path outside that contract's
`writes` globs asks the owner. Without this option, the command prints that the out-of-contract
check was skipped.

Existing installs must provide their instance-owned `config/merge-ready-stop-paths.txt` and
`config/merge-ready-bots.txt` before running this command. Copy both template files into the
install's `config/` directory:

```bash
cp <template>/config/merge-ready-stop-paths.txt <install>/config/merge-ready-stop-paths.txt
cp <template>/config/merge-ready-bots.txt <install>/config/merge-ready-bots.txt
```

The command fails closed when either file is missing, when the stop-list has no entries, or when
the roster file is empty or comment-only. It has no environment override for either path.

A dispatched worker's cwd is a product-repo worktree, not this ops repo. `scripts/dispatch`
rewrites the standing rule's relative script path to the installed `scripts/` directory before
the brief ships.

## What it measures

0. **The PR is open and not a draft.** `state` must be `OPEN` and `isDraft` must be false.

1. **Required checks.** The command compares names reported by `gh pr checks --required` with the
   full required set from all pages of `gh api repos/<owner/name>/rules/branches/<base>`. It also reads the
   legacy `gh api repos/<owner/name>/branches/<base>/protection/required_status_checks` endpoint;
   a `404 Branch not protected` response contributes no legacy contexts, while any other failure
   to read either source is not ready. Every required context must be reported with bucket `pass`.
   A parseable empty list is not ready because there is no required check to measure. A check that
   this repository runs but does not require never reaches this measurement. Every bot whose latest
   decision review on the exact head is `PENDING` or `CHANGES_REQUESTED` blocks separately. Only
   `APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`, and `PENDING` are decision states; a plain
   `COMMENTED` review does not change the latest decision.

1b. **The review-bot roster.** Every login in `config/merge-ready-bots.txt` must have a standalone
   GraphQL review on the exact head, including a plain `COMMENTED` review, or a measured rate-limit
   notice from that bot. A review is standalone when it has a non-empty review body or includes a
   top-level review comment; an empty review whose comments are all replies does not cover the bot.
   A dismissed review does not cover the bot. The notice must match the exact form emitted by the
   configured bot and its `created_at` must be at or after the measured head push event. A bot
   without either form of current engagement is not ready. An empty roster fails closed.

2. **Open review threads.** `reviewThreads(isResolved)` on the head must show zero unresolved
   threads.

3. **Stop-list and contract paths.** Any changed path matching
   `config/merge-ready-stop-paths.txt` asks the owner. The list covers charter, workspace card,
   role state, boot comparison set, scanner and redaction configuration, CI workflow and CODEOWNERS
   definitions, succession and bootstrap code, guard hooks, gate code, tier policy, worker
   settings, and this command's own files. A stop-paths file with no real entries fails closed.
   With `--contract`, any changed path outside the contract's `writes` globs asks the owner. Both
   the new and old name of a renamed path are checked.

## Collected responses

The command validates the shape of every response before using it. It pins changed files, check
runs, reviews, and the final head check to the initial head sha. It reads the PR head and compare
files, required checks, GraphQL reviews and threads, PR comments, and a matching PR timeline push
event when a rate-limit exemption needs a timestamp. Check-run timestamps do not qualify an
exemption. It reads the PR head again after the other responses; a changed head makes the result
not ready so the command can be run again.

Reviews and review threads are read up to 100 each. A connection with another page is not ready
and names pagination as the next action. The compare response caps responses at 3000 files;
the command exits `1` when the flattened response reaches 3000 because the complete path set cannot
be verified.

## Exit codes

- `0` merge: every measurement passed and no stop-list path was touched.
- `1` not ready: a check, roster, review thread, PR-state, response-shape, pagination, file-cap, or
  invocation measurement failed. An unavailable GitHub response and an unparseable response are
  both exit `1`.
- `2` ask the owner: a changed path matches the stop list or falls outside the contract's `writes`
  globs.

Every result is one summary line prefixed `merge-ready: merge ·`, `merge-ready: not ready ·`, or
`merge-ready: ask ·`.

## Honest limits

An empty `gh pr checks --required` response can represent either an unconfigured required-check
list or checks that have not started. The command treats both as not ready rather than guessing.

The command can verify the bot login and the exact rate-limit marker and required line declared in
`config/merge-ready-bots.txt`, but it cannot determine whether the bot's notice was truthful. The
head push event is generated by GitHub and provides the time comparison for current coverage.
Clock skew can still affect the comparison.

The `writes` field is read only from the contract's opening front matter. Python `fnmatch` handles
the declared globs, and its `*` crosses `/`. A contract without `writes:` is not ready; an explicit
empty list means every changed path is outside scope.

## What this command does not catch

- Required checks run pull-request code. Editing `tests/conftest.py` to skip tests can make a check
  pass; this command trusts the check result. Add such paths to the stop list when the install must
  protect against that change.
- A required check with no app pinned in the ruleset is satisfied by any commit status with the
  same name. Pin required checks to the GitHub Actions app when the install needs that guarantee.
- An account with write access can resolve review threads. This command reads the resolved status
  it receives from GitHub; it does not establish who was allowed to resolve a thread.
- A shared master and worker GitHub account lets the worker merge directly. These gates cover
  honest worker mistakes, not access control. Use a separate worker account with no merge rights.
