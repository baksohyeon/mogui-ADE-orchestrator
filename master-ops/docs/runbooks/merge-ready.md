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

When either file is missing, the command exits `2` and prints this copy instruction. Upgrade mode
also seeds each missing file after confirmation and preserves an existing file as instance-owned.

The worker token needs repository `Administration: read` permission to read legacy branch
protection. If the protection endpoint is unavailable to that token, the command reads the branch
response's `protection.required_status_checks`; if the rules endpoint returns HTTP 403 for a plan
limitation, it uses those legacy sources and asks the owner with exit `2` when neither source can
establish the required set. Other unreadable responses retain their normal not-ready result.

The command asks the owner with exit `2` when either file is missing, and fails closed when the
stop-list has no entries or the roster file is empty or comment-only. It has no environment
override for either path.

A dispatched worker's cwd is a product-repo worktree, not this ops repo. `scripts/dispatch`
rewrites the standing rule's relative script path to the installed `scripts/` directory before
the brief ships.

## What it measures

0. **The PR is open and not a draft.** `state` must be `OPEN` and `isDraft` must be false.

1. **Required checks.** The command compares names reported by `gh pr checks --required` with the
   full required set from all pages of `gh api repos/<owner/name>/rules/branches/<base>`. It also reads the
   legacy `gh api repos/<owner/name>/branches/<base>/protection/required_status_checks` endpoint.
   When that endpoint is unavailable, it reads `protection.required_status_checks` from
   `gh api repos/<owner/name>/branches/<base>`; an unprotected branch contributes no legacy
   contexts. Failure to read both legacy sources is not ready. Every required context must be
   reported with bucket `pass`.
   A parseable empty list is not ready because there is no required check to measure. A check that
   this repository runs but does not require never reaches this measurement. Every bot whose latest
   decision review on the exact head is `PENDING` or `CHANGES_REQUESTED` blocks separately. Only
   `APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`, and `PENDING` are decision states; a plain
   `COMMENTED` review does not change the latest decision.

1b. **The review-bot roster.** Every login in `config/merge-ready-bots.txt` must have a standalone
   GraphQL review on the exact head, including a plain `COMMENTED` review, or a measured rate-limit
   notice from that bot. A review is standalone when it has a non-empty review body or includes a
   top-level review comment on the returned page; an empty review whose comments are all replies does
   not cover the bot. A top-level comment on the returned page covers the review even when nested
   comments have another page; when no top-level comment is returned and more pages remain, the
   measurement is not ready rather than treating the review as coverage.
   A dismissed review does not cover the bot. The notice must match the exact form emitted by the
   configured bot and its `created_at` must be at or after the measured head push event. A bot
   without either form of current engagement is not ready. An empty roster fails closed.

2. **Open review threads.** `reviewThreads(isResolved)` on the head must show zero unresolved
   threads.

3. **Stop-list and contract paths.** Any changed path matching
   `config/merge-ready-stop-paths.txt` asks the owner. Entries work with both the template
   prefix and the installed root layout. The list covers charter, workspace card,
   role state, boot comparison set, scanner and redaction configuration, CI workflow and CODEOWNERS
   definitions, succession and bootstrap code, guard hooks, gate code, tier policy, worker
   settings, and this command's own files. A stop-paths file with no real entries fails closed.
   With `--contract`, any changed path outside the contract's `writes` globs asks the owner. Both
   the new and old name of a renamed path are checked.

## Collected responses

The command validates the shape of every response before using it. It reads the complete paginated
pull-request file list, checks the measured head before and after that read, and uses
`gh pr checks --required` for the reported check verdict. It reads required-check rules, legacy
required contexts, GraphQL reviews and threads, PR comments, and the latest qualifying PR timeline
push event when a rate-limit exemption needs a timestamp. After the other responses are collected,
the final head check reads `headRefOid` and `baseRefName` again and compares them with the initial
`head_sha` and `baseRefName`; a mismatch makes the result not ready so the command can be run again.
Check-run timestamps do not qualify an exemption. An ordinary push never qualifies because GitHub's
`committed` timeline events carry no server-recorded `created_at`; only a force-push event with a
server-recorded time can establish the exemption boundary. If no such qualifying push event exists,
the rate-limit exemption is unavailable and the command stays not ready; it does not substitute a
commit or check-run timestamp.

Reviews and review threads are read in pages of up to 100 using their GraphQL cursors. The command
stops with exit `1` and names the pagination cap after ten pages, or when a page is malformed. Nested
review comments are also read up to 100 for each review, but an empty review with a top-level comment
on the returned page remains usable even when its nested comments have another page. When no top-level
comment is returned and more nested-comment pages remain, the measurement is not ready. The
pull-request files endpoint caps responses at 3000 files; the command exits `1` when the flattened
response reaches 3000 because the complete path set cannot be verified.

The rules endpoint can include non-check rules such as creation, update, deletion, non-fast-forward,
pull-request, linear-history, merge-queue, deployment, signature, naming-pattern, path-restriction,
reviewer, and file-size rules. These rules do not supply required check contexts, so the measurement
recognizes them and continues; a new or check-gating rule type such as `workflows` or `code_scanning`
fails closed with exit `1` when no stop-list or contract ask is known, or exit `2` when an ask is known,
instead of silently omitting a required gate. GitHub enforces required
deployments and required reviewers at merge time; this command does not attest to either requirement.

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
latest qualifying head push event is generated by GitHub and provides the time comparison for
current coverage. Clock skew can still affect the comparison.

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
