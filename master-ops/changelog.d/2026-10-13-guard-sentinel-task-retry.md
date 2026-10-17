Guard sentinel and Task retry corrections (2026-10-13):

- Keep the product-path guard's unsubstituted `{{RUNTIME_ROOT}}` sentinel out
  of template replacement, so an installed hook accepts its default runtime
  config path instead of blocking every tool call.
- Document Orca 1.4.224's coordinator-worktree Task binding, the
  `terminal_worktree_mismatch` from cross-worktree `worker-start` retries, and
  the `dispatch --inject` recovery path.
