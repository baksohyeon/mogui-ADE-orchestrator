- New `scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>] [--test-command <cmd>]`
  (#330): one measurement, run by a worker before `worker_done` and by the master before merge.
  Exit `0` merge, `1` not ready (including a `gh` call or the invocation itself failing to run),
  `2` ask the owner, with one summary line naming every failing or asking item. Measures: every
  required check (`gh pr checks --required`, branch protection's own list) has bucket `pass`,
  except one the PR body names `rate-limited:`; every bot review on the exact head is not pending
  or changes-requested; zero open review threads; the test suite re-run from a tarball of the
  head, with one named deselect for the test that needs a `.git`; a `merge-ready-review-pass
  sha=... critical=... important=...` marker recorded for the exact head with no Critical or
  Important findings; and the stop list in `config/merge-ready-stop-paths.txt` (charter,
  workspace card, role state, boot comparison set, scanner config, guard hooks, gate code, tier
  policy, worker settings, the stop-paths file and this script itself), checked against both a
  renamed file's old and new path, plus, with `--contract`, any changed path outside that
  contract's `writes` globs. Every gathered `gh` response is validated for shape, not just for
  having run, so an empty-but-valid one (missing `pullRequest`, an empty files list) is not
  ready, never a silent pass. `docs/runbooks/merge-ready.md` has the full measurement list, the
  marker format, and the honest limits (no way to verify a posted review pass was a real one,
  `writes` globs matching with `fnmatch` whose `*` already crosses `/`, the 3000-file cap on
  GitHub's own files API, and `gh pr checks --required` reading identically for "nothing is
  required" and "required checks exist but have not posted yet").
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
