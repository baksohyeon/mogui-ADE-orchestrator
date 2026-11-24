Execution rule classes (2026-11-24):

- The template now classifies actions as G0 through G3 before execution and
  reserves Proposal -> Approval -> Execution for G2, G3, and unknown classes.
- An existing installation with its own `Execution rule:` line keeps that
  local rule, while an installation that relied on the built-in default now
  receives the classify-first text. An installation that needs the previous
  default can set `Execution rule: Proposal -> Approval -> Execution.` in its
  instance role-state file.
