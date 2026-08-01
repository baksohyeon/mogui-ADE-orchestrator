---
status: active
---

# Succession Boot Card

## System Summary

- Normal operation is continue-and-compact. Promote accepted knowledge, active tracks, and open decisions into the issue tracker or Git so only disposable context is lost.
- Succession is a clean-spawn procedure triggered by explicit user instruction. Automatic succession is not allowed.
- After compaction or clear, first reload issue-tracker context and reconfirm active tracks.

## Clean Succession Procedure

1. Current master: run a promotion audit for accepted knowledge, active tracks, open decisions, and unresolved acceptance evidence.
2. Current master: spawn a clean successor with explicit workspace selector, kickoff file, root `{{WORKSPACE_ROOT}}`, model `{{MODEL_ID}}`, and machine-readable response when the host supports it.
3. Current master: verify successor liveness by session artifact and process evidence, leave a one-line retirement note, and freeze.
4. Successor: boot with a Role State declaration, measure the actual model field, capture the placement evidence three-set, close or retire the predecessor pane when the host supports it, and append a concise entry to `docs/lineage/MASTER-LINEAGE.md`.

Placement evidence three-set:

1. host pane or worktree selector matches the intended workspace
2. process current working directory is under `{{WORKSPACE_ROOT}}`
3. session artifact or log path belongs to the expected workspace/session namespace

## Accident Recovery

Process death, host restart, stale UI handle, or accidental pane closure is not succession. First try same-session resume after proving no live duplicate process owns the session. If host runtime state is stale, recover the host, reacquire the handle, and verify connected state before continuing.

## Invariants And Traps

- Measure both configured model flag and actual session model field.
- A boot measurement is a snapshot. A recent-turn probe cannot see a change that happened earlier and then settled, so at succession audit walk the whole transcript with `{{RUNTIME_ROOT}}/scripts/model-drift-audit`. Exit 2 means undecidable; do not read it as a pass.
- The successor cwd must be the workspace root or an explicitly approved orchestrator root.
- Never double-start the same session. Resume only after proving the previous process is gone.
- UI pane titles and status lines are hints, not placement evidence.
- The monitor namespace is `{{MONITOR_NS}}`.
- Do not spawn a successor without a promotion audit.
