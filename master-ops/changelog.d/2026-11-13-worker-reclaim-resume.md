# Worker reclaim resumes by worktree

`worker-reap` records the Orca worktree selector and available agent session id
at dispatch time, selects panes by worktree membership, and closes them through
Orca only after the existing `worker-pane-sweep` reports every member idle.
Landing accepts squash merges through a path-scoped content comparison and
reports whether ancestry or content decided the result. The dispatch runbook
now routes abnormal worker exits through session resume before re-dispatch.
