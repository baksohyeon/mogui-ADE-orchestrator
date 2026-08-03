# §6. Succession

Governs master succession and recovery procedures. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Normal operation is continue-and-compact. Promote accepted knowledge, active tracks, and open decisions into the issue tracker or Git promptly so only disposable context is lost.

After compaction, the first action is issue-tracker context reload and active-track reconfirmation.

Succession is a single clean-spawn procedure. It is triggered by explicit user instruction. The master may propose succession around high context pressure, but automatic succession is not allowed.

Clean succession procedure:

1. Current master runs a promotion audit for accepted knowledge, active tracks, and open decisions.
2. Current master spawns a clean successor with an explicit workspace selector, kickoff file, root `{{WORKSPACE_ROOT}}`, model `{{MODEL_ID}}`, and machine-readable response when the host supports it.
3. Current master verifies successor liveness, leaves a one-line retirement note, and freezes.
4. Successor boots, declares Role State, measures the actual model field, captures the placement evidence three-set, closes or retires the predecessor pane when the host supports it, and appends a concise Lineage entry.

Placement evidence three-set:

1. host pane or worktree selector matches the intended workspace
2. process current working directory is under `{{WORKSPACE_ROOT}}`
3. session artifact or log path belongs to the expected workspace/session namespace

Accident recovery is not succession. Process death, host restart, stale UI handle, or accidental pane closure should first try same-session resume after proving no live duplicate process owns the session.
