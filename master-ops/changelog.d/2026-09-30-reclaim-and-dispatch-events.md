Reclamation that measures before it closes, and a dispatch lifecycle you can read back (2026-09-30):

- `src/master_runtime/core/worker_reap.py`: `WorkerReaper.reap()` no longer closes a settled
  dispatch's pane unconditionally. Three measurements now gate the close, all required: the
  terminal handle is still present in `orca terminal list`; no `dispatched` row in `orca
  orchestration worker-list` (paginated, every Run) names the same handle — a newer dispatch may
  have reused the pane before this one was reaped; and no agent CLI process (`claude`, `codex`,
  `cursor`, `agy`, `grok`, matched by comm basename) has its cwd inside the dispatch's worktree
  (`lsof -a -p <pid> -d cwd -Fn`, falling back to `/proc/<pid>/cwd`). A measurement that could not
  be taken at all is a refusal, the same as a measurement that failed — never a pass. Each refusal
  is a named reason in `actions_taken` (`pane_absent`, `reused_by:<dispatch-id>`,
  `agent_process:<pid>:<comm>`, or an `_unmeasured` suffix). `--dry-run` now prints
  `would_close_terminal:`/`would_remove_worktree:` instead of the executed-action strings, and
  never prints `terminal_closed` — the bug this scope item exists for: a dry run on a pane closed
  hours earlier, and on a pane a newer, still-`dispatched` dispatch was using, both reported
  `terminal_closed:<handle>` with no check against measured state. Untracked `__pycache__/` litter
  no longer counts as dirty when deciding whether a worktree is safe to remove. `ReapRecord` gained
  a `measurements` field (`terminal_present`, `terminal_reused_by`, `agent_process`,
  `worktree_clean`, `worktree_merged`) carried through to the ledger and the CLI's JSON output.
- `master-ops/scripts/worker-wait` gains `--reap` (default off): an `OPEN_PANE` row additionally
  calls `scripts/worker-reap --task-id <id> --json` for that row's dispatch and folds the reaper's
  record into the row under a `reap` key, instead of the coordinator running it as a manual
  follow-up. `_worker_list` now also tracks a handle-to-taskId map (every worker-list row seen, not
  just `dispatched` ones) so an `OPEN_PANE` row can resolve the task id of whichever dispatch last
  claimed that pane. Without `--reap`, `--once --json` output is byte-identical to before. A
  missing `scripts/worker-reap` (a template-applied tree with no sibling orchestrator checkout)
  reports `worker_reap_not_found` on the row rather than raising.
- Dispatch lifecycle events, through the existing `master-ops/scripts/mogui_log.py` `emit()`, no
  new file: `master-ops/scripts/dispatch` emits `dispatch_launched` after its register step, with
  dispatch id, task id, pane, pid (usually empty — `dispatch` creates the worker's terminal through
  an RPC, not a local process), and model. `scripts/dispatch-gate register` emits
  `dispatch_registered`. `worker-wait` emits `wait_verdict` once per actionable row (`DEAD`,
  `STALL`, `OPEN_PANE`) per accounting pass, and `wait_wake` once per non-heartbeat delivery, with
  the message type(s) and delivery id. `scripts/worker-reap` emits `reaped` with `actions_taken`
  after a real (non-dry-run) reap. Every event carries `dispatch_id`/`task_id` where known.
  `mogui_log._session_kind()` now returns `master` when the process's cwd is the workspace root
  (`config/workspace-descriptor.json`'s `workspace_root`, checked at `<cwd>/config/`, or the new
  `MOGUI_SEAT_ROOT` environment variable when set — checked first, ahead of the descriptor file),
  `worker` as today (unchanged: `ORCA_TASK_ID` set, or `.orca/worktrees` in the cwd), `unknown`
  otherwise. `worker-wait`'s `mogui_log` import is fail-open (a copy of the script made without its
  sibling, or a template-apply that has not landed `mogui_log.py` yet, logs nothing instead of
  crashing the wait loop) — this file is template-applied together with its sibling in normal
  deployment, so the fallback is a defensive floor, not the expected path.
- `scripts/dispatch-timeline <task_id|dispatch_id>`, new, read-only
  (`src/master_runtime/core/dispatch_timeline.py` plus a thin CLI, mirroring `worker-reap`'s own
  split): joins the ledger row(s), every event-log line, and the current `dispatch-show` record for
  one dispatch into a time-ordered table (timestamp, source, event, outcome, detail) and `--json`.
  A source with nothing matching is named in `missing_sources`, never silently absent. `--since
  <hours>` with no id lists every dispatch seen in that window with its last event — the seat's
  daily accounting view.
- Tests, each with a failability case: `tests/test_worker_reap.py` gained pane-absent,
  pane-reused-by-a-dispatched-dispatch, agent-process-in-the-worktree, each measurement's
  unmeasured case, `__pycache__`-litter-is-not-dirty (mocked and real-git), and dry-run-shape
  cases, alongside the existing dirty/clean/squash-merge coverage (now routed through one
  `_MeasuredEnvironment` fake covering all five external measurements, defaulted to the happy
  path). `tests/test_worker_wait.py` gained `--reap` invoking the reaper exactly once per
  `OPEN_PANE` row and not otherwise, plus an autouse fixture pointing `mogui_log.LOG_DIR` at a
  scratch path so the suite never appends to a developer's real `~/.mogui/event-log.jsonl`.
  `tests/test_mogui_log.py` (new): `session_kind` `master` via `MOGUI_SEAT_ROOT` and via the
  descriptor file, `worker`, `unknown`, and a malformed descriptor swallowed rather than raised.
  `tests/test_dispatch_timeline.py` (new): join order across all three sources, each source named
  missing independently (not just an all-or-nothing check), and `--since` windowing.
  `master-ops/scripts/test-dispatch-timeline.sh` (new, promoted shell test): `--json` against
  fixture ledger/event-log files and a fake `orca`, with a sort-removal mutant against a mirrored
  scripts+src tree (`__pycache__` stripped from the copy, since a stale compiled copy of the
  mutated module silently shadowed the edit during development of this test).
- Docs: `master-ops/docs/runbooks/worker-wait.md` gained the `--reap` section and the reaper's
  three pane measurements; new `master-ops/docs/runbooks/dispatch-timeline.md` names the event
  kinds and the accounting view. `docs/runbooks/worker-reap.md` (repo root) corrected — it
  described the pre-existing unconditional close and a two-measurement-only worktree check; now
  describes all three pane measurements, `--dry-run`'s `would_*` action shape, and the
  `measurements` field on the record and ledger row. `docs/public/reference.md` gained a row for
  `scripts/dispatch-timeline`. `MANIFEST.json` regenerated for the new files.
- Tracker: `mgm-cxj2`.
