- New `scripts/land --repo <path> --gate '<command>' <commit>...` for repositories whose
  `main` takes commits without a PR: fetch, cherry-pick and record the sha that produced
  (`picked`), run the gate and continue only on its exit code (never a line of its output),
  confirm the checkout is still on `main` at `picked` and clean, confirm the remote is an
  ancestor, push `picked` (never whatever `HEAD` happens to be by then), then confirm the
  remote now has `picked` as an ancestor, stopping at the first failure and resetting the
  checkout. A `--gate` that is empty or only whitespace is rejected before anything runs, and a
  reset that would destroy uncommitted changes left on the checkout is refused instead, with
  recovery shas printed, rather than silently discarding them. `docs/runbooks/land.md` has the
  steps and exit codes. Fixes #318.
