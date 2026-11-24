Execution rule classes (2026-11-24):

- The template now classifies actions as G0 through G3 before execution and
  reserves Proposal -> Approval -> Execution for G2, G3, and unknown classes.
- An existing installation keeps its current rule by retaining its own
  `Execution rule:` line in the instance role-state file; the hook uses that
  line instead of the built-in default.
