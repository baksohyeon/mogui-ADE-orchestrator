- `scripts/dispatch` appends the `mail-before-done` standing-rule block to
  every brief when the install's rules file carries it (run `orca
  orchestration check` once before `worker_done`, and apply or explain any
  coordinator mail it returns), the same way it already appends the
  token-budget line; a contract naming the block explicitly in
  `standing_rules` still gets it exactly once. An install whose rules file
  predates this change gets a warning instead and dispatches without the
  block. Fixes #310.
- `docs/runbooks/worker-wait.md` states that more work for a pane whose
  dispatch already sent `worker_done` goes as a new dispatch to the same
  pane; text typed into the pane runs outside any dispatch, so Orca sends no
  stop alerts for it. Fixes #307.
- `docs/runbooks/worker-wait.md`'s approval-clearing guidance adds
  `--wait-submit` plus a pane re-read (`orca terminal read --screen`) before
  an answered approval counts as cleared, and names `orca orchestration deny`
  for a refusal; `scripts/worker-pane-sweep` prints the same re-read check on
  every `approval` row. Fixes #286.
