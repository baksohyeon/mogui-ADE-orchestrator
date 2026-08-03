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
4. Successor: bind a standing coordinator Run to this session (create or reuse an existing durable Run and record its address in a shared location so peers can find it), declare Role State, measure the actual model field, capture the placement evidence three-set, close or retire the predecessor pane when the host supports it, and append a concise entry to `docs/lineage/MASTER-LINEAGE.md`. A handle recorded in its place will be dead by the next restart.

Placement evidence three-set:

1. host pane or worktree selector matches the intended workspace
2. process current working directory is under `{{WORKSPACE_ROOT}}`
3. session artifact or log path belongs to the expected workspace/session namespace

## Retirement Completion And Revival Checks

Retirement of a session is complete only when three disappearances are measured, not when a close command returns: the process (pid gone), the host pane (no live handle in the host's terminal list), and the tty (device and login chain gone). Close command return values have been wrong in both directions on real hosts; the measurement decides.

A frozen session stays resumable forever, from any terminal the agent CLI runs in, including a phone or a remote machine. Measured live: four retired masters were revived at once by a mobile resume, attached to ttys outside the host runtime where pane doctrine cannot see them. Therefore:

- At boot, and whenever the owner reports stray sessions, scan running agent processes for the session ids recorded in `docs/lineage/MASTER-LINEAGE.md`. Resume arguments differ per agent CLI, so the key is the session id itself in the process argv, not any one CLI's flag.
- On a hit, in order: read the revived session's own record for activity since freezing (tool calls, repository writes); recover any unanswered owner instruction into the current master; terminate the agent process; hang up the hosting terminal chain; confirm the tty is gone. A shell with other children gets its children measured first.

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
