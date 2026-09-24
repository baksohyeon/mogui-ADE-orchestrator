# Master Placement Record

Measured during onboarding by the installer session.

- **Durable workspace selector**: `id:folder:<workspace selector>`
- **Workspace root**: `{{WORKSPACE_ROOT}}`
- **Seat kind**: folder workspace (workspace-level seat, not a repository worktree)

The selector above is the durable identity of the master's seat. Terminal handles are
scoped to the Orca app runtime and die with restarts; never record a handle as durable,
and never substitute a filesystem path for this selector.

## Proof (`orca terminal show` on the placement probe) (seat-specific example)

```json
{
  "handle": "<terminal handle>",
  "worktreeId": "folder:<workspace selector>",
  "worktreePath": "",
  "branch": "",
  "title": "...<workspace root, truncated>",
  "connected": true,
  "writable": true,
  "lastOutputAt": 1785741719450
}
```

Note: the empty `worktreePath` is the expected shape for a folder workspace; the seat is
judged by `worktreeId`. The probe terminal was opened solely to prove the seat and is closed
after this record; the founding spawn verifies placement against this selector again.

## Known sibling seat (not the master's seat) (seat-specific example)

A second same-titled folder terminal existed at measurement time under a different
`folder:<workspace selector>` (last output predating the probe request). It is presumed a
leftover from a prior folder-move recovery (see `{{WORKSPACE_ROOT}}/ORCA-WORKSPACE-GUIDE.md`)
and must not be used for spawning.
