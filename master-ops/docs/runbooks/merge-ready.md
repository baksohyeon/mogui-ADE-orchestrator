# Merge-Ready: One Measurement For A Pull Request

`scripts/merge-ready` measures one pull request and exits non-zero unless it may merge without
asking the owner (#330). A worker runs it on its own PR before `worker_done`; the master runs it
again before merge. The command reads GitHub state and local gate configuration. It never executes
code from the pull request.

Before the master posts `merge-ready-master-pass`, the master performs a separate test step from
a head tarball. That step belongs to the master's review procedure and is not performed by
`scripts/merge-ready`.

## Usage

```bash
scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>]
```

`--contract <file>` adds the contract-scope check: any changed path outside that contract's
`writes` globs asks the owner.

A dispatched worker's cwd is a product-repo worktree, not this ops repo. `scripts/dispatch`
rewrites the standing rule's relative script path to the installed `scripts/` directory before
the brief ships.

## What it measures

0. **The PR is open and not a draft.** `state` must be `OPEN` and `isDraft` must be false.

1. **Required checks.** Every entry reported by `gh pr checks --required` must have bucket `pass`.
   A parseable empty list is not ready because there is no required check to measure. A check that
   this repository runs but does not require never reaches this measurement. Every bot whose latest
   decision review on the exact head is `PENDING` or `CHANGES_REQUESTED` blocks separately. Only
   `APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`, and `PENDING` are decision states; a plain
   `COMMENTED` review does not change the latest decision.

1b. **The review-bot roster.** Every login in `config/merge-ready-bots.txt` must have a GraphQL
   review on the exact head, including a plain `COMMENTED` review, or a measured rate-limit comment
   from that bot. A rate-limit comment must contain `review limit reached` or `rate limited by`,
   case-insensitively, and must be posted or last edited at or after the head commit's committer
   timestamp. A bot without either form of current engagement is not ready. An empty roster fails
   closed.

2. **Open review threads.** `reviewThreads(isResolved)` on the head must show zero unresolved
   threads.

3. **The master's separate test step.** The master reruns the suite from a tarball of the exact
   head before posting the master marker. This command records no test result and does not execute
   the pull request.

4. **A master-pass marker on the exact head.** A PR comment must contain the line
   `merge-ready-master-pass sha=<40-hex head sha> critical=<N> important=<N>`. The newest matching
   line across all comments wins. Missing, wrong-sha, or nonzero Critical or Important counts are
   not ready. The worker's `merge-ready-worker-pass` marker never satisfies this measurement.

5. **Stop-list and contract paths.** Any changed path matching
   `config/merge-ready-stop-paths.txt` asks the owner. The list covers charter, workspace card,
   role state, boot comparison set, scanner and redaction configuration, CI workflow and CODEOWNERS
   definitions, succession and bootstrap code, guard hooks, gate code, tier policy, worker
   settings, and this command's own files. A stop-paths file with no real entries fails closed.
   With `--contract`, any changed path outside the contract's `writes` globs asks the owner. Both
   the new and old name of a renamed path are checked.

## Collected responses

The command validates the shape of every response before using it. It reads the PR head and
changed files, required checks, GraphQL reviews and threads, PR comments, and the head commit's
committer timestamp. It reads the PR head again after the other responses; a changed head makes
the result not ready so the command can be run again.

Reviews and review threads are read up to 100 each. A connection with another page is not ready
and names pagination as the next action. REST PR files are subject to GitHub's 3000-file API cap;
the command cannot detect truncation beyond that API response.

## The markers

There are two markers, and they are never interchangeable:

- `merge-ready-worker-pass sha=<full head sha> critical=<N> important=<N>` is the worker's
  informational pre-check, posted after its independent review and before `worker_done`.
- `merge-ready-master-pass sha=<full head sha> critical=<N> important=<N>` is the master's marker,
  posted after the master's independent review and separate head-tarball test step. It is the only
  marker this command checks for exit `0`.

The marker's SHA ties it to one exact commit. A marker from before the last push does not count for
the current head. A fresh matching marker supersedes an older matching line without requiring the
older comment to be deleted.

## Exit codes

- `0` merge: every measurement passed and no stop-list path was touched.
- `1` not ready: a check, roster, review thread, marker, PR-state, response-shape, pagination, or
  invocation measurement failed. An unavailable GitHub response and an unparseable response are
  both exit `1`.
- `2` ask the owner: a changed path matches the stop list or falls outside the contract's `writes`
  globs.

Every result is one summary line prefixed `merge-ready: merge ·`, `merge-ready: not ready ·`, or
`merge-ready: ask ·`.

## Honest limits

An empty `gh pr checks --required` response can represent either an unconfigured required-check
list or checks that have not started. The command treats both as not ready rather than guessing.

The master marker is a convention. The command cannot prove which account author posted it; it
checks the marker name, SHA, and recorded findings. A rate-limit comment has no commit reference,
so the head commit's committer timestamp is the available proxy for current coverage. A bot could
have edited old text after a push, and clock skew could affect the comparison.

The `writes` field is read only from the contract's opening front matter. Python `fnmatch` handles
the declared globs, and its `*` crosses `/`. A contract without `writes:` is not ready; an explicit
empty list means every changed path is outside scope.
