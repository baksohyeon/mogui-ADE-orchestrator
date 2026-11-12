# fix: codex workers can commit in a fresh worktree

## Summary
Codex workers launched in fresh linked worktrees with the `workspace-write` sandbox were blocked on the first `git add` with "index.lock: Operation not permitted". The index lives outside the sandbox's write root (`.git/worktrees/<name>/`). Running `git status --porcelain` once before the worker launches "unlocks" the index, allowing all subsequent sandboxed git operations in that session to succeed.

## Root Cause
Git worktree indices reside in the shared `.git/worktrees/<name>/` directory, which falls outside the `workspace-write` sandbox's permitted write paths (worktree root, `/tmp`, `$TMPDIR`). The fix is to initialize git's index state before sandbox isolation by running a git read operation (status) from the wrapper, outside the sandbox.

## Changes
- `master-ops/scripts/dispatch`: Added `git status --porcelain` call for codex runtime only, before worker launch (section 3c)
- `master-ops/scripts/test-dispatch-codex-git-index.sh`: Test verifying the fix does not break the wrapper

## Testing
Verified on fresh linked worktrees that `git status --porcelain` successfully enables subsequent `git add` operations without "index.lock" errors.

## References
- Card: mgm-up2w
- Postmortem: `docs/postmortem/2026-11-12-codex-worker-git-index-outside-sandbox.md`
