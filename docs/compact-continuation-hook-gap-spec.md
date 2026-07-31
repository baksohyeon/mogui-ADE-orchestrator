# Compact Continuation Hook Gap Spec

Date: 2026-07-31

## Scope

This document specifies the harness wiring that is still required outside this
contract. No hook configuration file is changed by this work.

## Implemented Script Behavior

`scripts/master-bootstrap-live` now treats `SessionStart` input with
`source == "compact"` as a high-risk first-injection event.

The script prepends a top-priority banner stating that the synthetic
continuation turn before this hook output may have run without rehydration. The
banner requires a read of the canonical `role-state.md`, an explicit Role State
declaration, and stopping if the read is unavailable.

The compact recall suppression block still hides Role State and active-track
sections before emitting the recall probe. Section matching is regex-based for
Markdown headings such as `## Role State`, `### role state`, `## Active Tracks`,
and `## 활성 트랙`. If suppression logic fails, the script preserves the
original block and still emits the first-injection warning.

## Required Hook Wiring

The hook layer should ensure the same warning reaches the first prompt-visible
turn after compaction. If the host only delivers `SessionStart(source=compact)`
output on the next user prompt, the warning must be injected at the front of
that prompt-visible block.

The hook layer should also maintain a per-session compact marker with these
states:

- `compact_detected`: a compact source event was observed.
- `first_injection_emitted`: the first-injection banner was delivered.
- `role_state_declared`: the agent has declared Role State in the current
  post-compact session.

Before state-changing commands such as merge, push, deploy, ticket transition,
or production write, the hook layer should fail closed if
`role_state_declared` is absent after `compact_detected`.

## Non-Goals

This contract does not edit `.claude/`, hook registration files, shell startup
files, or host-specific settings. Those changes belong to a separate lane.
