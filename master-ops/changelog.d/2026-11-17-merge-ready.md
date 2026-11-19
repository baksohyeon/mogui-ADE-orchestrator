- New `scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>]` (#330): one
  GitHub-state measurement run by a worker before `worker_done` and by the master before merge.
  Exit `0` means every required check passed, the review-bot roster is covered, no review thread
  remains unresolved, and no stop-list or contract-scope path asks the owner. The summary carries
  the full measured head sha for the master's separate merge command. Exit `1` covers failed
  measurements and unreadable or unparseable GitHub responses. Exit `2` asks the owner for
  stop-list or contract-scope paths.
- The command never executes pull-request code. The master separately performs its independent
  review and reruns the suite from a tarball of the exact head before using
  `gh pr merge --match-head-commit <sha>`.
- Existing installs must copy `config/merge-ready-stop-paths.txt` into their own `config/` directory
  before running the command. The command fails closed when that file is missing or empty.
- The review-bot roster compares an exact bot notice with a GitHub-generated check-suite or
  check-run creation time, with a matching PR timeline push event as fallback, so an
  author-controlled committer timestamp cannot qualify an older notice. The command rejects a
  response at GitHub's 3000-file cap and reports when the out-of-contract check was skipped.
- The stop list in `config/merge-ready-stop-paths.txt` covers charter, workspace, gate, hook,
  workflow, scanner, and CODEOWNERS controls. Its examples include `.github/labeler.yml`,
  `.github/release.yml`, `CODEOWNERS`, `.github/CODEOWNERS`, and `docs/CODEOWNERS`.
- Required checks never use a rate-limit exception. Empty required-check, roster, stop-list, or
  malformed-response shapes fail closed.
