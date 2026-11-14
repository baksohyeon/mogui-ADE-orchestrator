# Installed hooks resolve from the workspace

Hook wiring now uses rendered operations-repository paths, and the harness
self-check parses quoted command paths without depending on the session cwd.
Worktree coverage proves the listed installed hook paths resolve from a worker
worktree, while the tracker hook reports a clean skip when workspace-root data
is unavailable.
