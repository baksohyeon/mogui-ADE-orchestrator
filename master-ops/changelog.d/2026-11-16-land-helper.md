- New `scripts/land --repo <path> --gate '<command>' <commit>...` for repositories whose
  `main` takes commits without a PR: fetch, cherry-pick, run the gate and continue only on its
  exit code (never a line of its output), confirm the remote is an ancestor, push, then confirm
  the remote matches the pushed `HEAD`, stopping at the first failure and resetting the checkout.
  `docs/runbooks/land.md` has the steps and exit codes. Fixes #318.
