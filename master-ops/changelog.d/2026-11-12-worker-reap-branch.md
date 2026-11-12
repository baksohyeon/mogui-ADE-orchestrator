# fix: worker-reap retires the matching merged local branch

After a clean merged worktree is removed, `worker-reap` now captures the local
branch tip and checks the pull request state through `gh`. It deletes the local
branch only when the pull request is `MERGED` and `headRefOid` equals that tip,
which covers squash merges while keeping branches for missing, open, or
unmeasurable pull requests and for changed tips.

Dry runs report the planned branch deletion, and every refusal records a reason
alongside the existing reap actions.
