- New `scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>] [--test-command <cmd>]`
  (#330): one measurement, run by a worker before `worker_done` and by the master before merge.
  Exit `0` merge, `1` not ready (including a `gh` call or the invocation itself failing to run),
  `2` ask the owner, with one summary line naming every failing or asking item. Measures: every
  required check (`gh pr checks --required`, branch protection's own list) has bucket `pass`, no
  exemption of any kind; every bot review on the exact head is not pending or changes-requested,
  and every bot in `config/merge-ready-bots.txt` shows a review or a recent comment on the head
  (a rate-limit comment from that bot is the one way to cover it without an actual review); zero
  open review threads; the test suite re-run from a tarball of the head, with one named deselect
  for the test that needs a `.git`; a `merge-ready-master-pass sha=... critical=... important=...`
  marker the master posts after its own review (the worker's own separate `merge-ready-worker-pass`
  pre-check marker never satisfies this); and the stop list in `config/merge-ready-stop-paths.txt`
  (charter, workspace card, role state, boot comparison set, scanner config, guard hooks, gate
  code, tier policy, worker settings, CI/CODEOWNERS definitions, succession/bootstrap code, and
  this script's own files), checked once early (before the test re-run even starts, so no PR code
  runs on this machine before an "ask") and once more at the end, against both a renamed file's
  old and new path, plus, with `--contract`, any changed path outside that contract's `writes`
  globs. Every gathered `gh` response is validated for shape, not just for having run, so an
  empty-but-valid one (missing `pullRequest`, an empty files or required-checks list) is not
  ready, never a silent pass. `docs/runbooks/merge-ready.md` has the full measurement list, the
  marker format, and the honest limits (the review-bot roster's comment timestamp bound is an
  approximation, `writes` globs matching with `fnmatch` whose `*` already crosses `/`, and the
  3000-file cap on GitHub's own files API).
- New standing-rule block `merge-ready-before-done`, appended to every dispatched brief the way
  `mail-before-done` and `required-infra` already are (skipped for work that does not end in a
  PR): run an independent review pass, post its marker, run `scripts/merge-ready` on your own PR
  before `worker_done`, and quote its line. `scripts/dispatch` resolves the block's script path
  to this install's own absolute `scripts/` directory, since a dispatched worker's cwd is a
  product-repo worktree, not this ops repo.
- Review-pass fixes to `scripts/merge-ready` (two independent automated reviews on PR #338):
  every check, review, thread, changed-file, and comment measurement is now gathered again after
  the tarball test re-run finishes, and the PR's head is compared against the one tested, not
  ready if either moved mid-run; a closed, merged, or draft PR is not ready rather than
  potentially passing; a bot's superseded review on the same head (replaced by a later one from
  the same bot) no longer counts; an empty-but-structurally-present `reviews`/`reviewThreads`
  connection (missing `nodes`/`pageInfo`) is not ready, not a silent zero; a stop-paths file with
  no real entries is not ready, not "nothing to block"; the `writes` glob list is read only from
  the contract's opening front matter, never an example in its body text, and a contract with no
  `writes:` field is not ready rather than an ask, since there is no declared scope to check
  against; the stop list adds `master-ops/AGENTS.md`, the redaction scanner script, the approval
  gate module, the Codex hook-trust script, the Codex/Claude/Agy/Cursor worker pretrust scripts,
  and `scripts/dispatch-gate`; and the stop-paths file location has no environment override,
  closing a path a worker's own shell access could otherwise have used to neutralize the stop
  list. A second review round on that fix commit found two more: the post-test head re-check now
  reads last, after checks/files/comments, narrowing the window a late push could still land in,
  and the `writes:` list parser now strips only the outer brackets (the same rule
  `dispatch_gate.py`'s own front-matter parser uses) instead of a regex that stopped at the first
  `]`, so a glob with its own brackets (an `fnmatch` character class) survives intact.
- Round 2 (#330), from the master's own review: removed the PR-body `rate-limited:` exemption
  entirely (a required check never skips, from anywhere); split the single review-pass marker
  into the worker's own `merge-ready-worker-pass` pre-check and the master's `merge-ready-master-
  pass`, only the latter gating exit 0; an empty required-checks list is now not ready instead of
  a silent pass; added the `config/merge-ready-bots.txt` review-bot roster (`cubic-dev-ai`,
  `coderabbitai`), each bot covered by a head review or a comment posted or last edited at or
  after the head commit's own timestamp (catching a bot that edits one sticky comment per push
  rather than posting a fresh one each time); the stop list and `--contract` writes-scope check
  now run once early, before the test re-run starts, short-circuiting with no test run at all
  when either already decides "ask"; `gh api ... --paginate --slurp` replaces relying on
  `--paginate` alone to combine pages; and `set -C` (`noclobber`) now guards every one of this
  script's own writes to a predictable sibling temp-file name against a symlink the test
  command's own run could have planted first.
