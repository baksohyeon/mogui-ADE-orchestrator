# fix: worker-reap retires the matching merged local branch

Before a clean merged worktree is removed, `worker-reap` now captures the local
branch tip and repository and checks the pull request state through `gh`. After
removal, it deletes the local branch only when the pull request is `MERGED` and
`headRefOid` equals that tip, which covers squash merges while keeping branches
for missing, open, or unmeasurable pull requests and for changed tips.

Dry runs report the planned branch deletion, and every refusal records a reason
alongside the existing reap actions.
