- New `scripts/merge-ready --repo <owner/name> --pr <n> [--contract <file>]` (#330): one
  GitHub-state measurement run by a worker before `worker_done` and by the master before merge.
  Exit `0` means every required check passed, the review-bot roster is covered, no review thread
  remains unresolved, the exact-head master marker records zero findings, and no stop-list or
  contract-scope path asks the owner. Exit `1` covers failed measurements and unreadable or
  unparseable GitHub responses. Exit `2` asks the owner for stop-list or contract-scope paths.
- The command never executes pull-request code. Before posting `merge-ready-master-pass`, the
  master separately reruns the suite from a tarball of the exact head.
- The standing `merge-ready-before-done` rule requires an independent worker review, a
  `merge-ready-worker-pass` marker, the command's summary line, and the master's separate
  head-tarball test step before the master marker. The worker and master markers remain distinct.
- The review-bot roster accepts a review on the exact head or a measured rate-limit comment from
  the configured bot. Required checks never use a rate-limit exception. Empty required-check,
  roster, stop-list, or malformed-response shapes fail closed.
