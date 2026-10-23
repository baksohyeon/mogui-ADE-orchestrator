# dispatch-smoke

`scripts/dispatch-smoke` is a seat-run check that `scripts/dispatch`
still reaches a worker on a live instance. `test-dispatch-smoke.sh` covers the
template's pure functions in CI; this script covers the rendered wrapper on a
real seat, which CI cannot do (it needs Orca and a `claude` install).

## What it verifies

- Path under test: the wrapper's created-pane path, `gate check` ->
  `contract delivered` -> `task-create` -> `terminal create` in a fresh
  worktree -> `dispatch --inject` -> `register` -> delivery classification,
  for `--runtime claude` only.
- Failure input: a top-tier model id with no `--top-approved`. The wrapper
  refuses before the gate check, so this case is deterministic and writes
  nothing anywhere.
- Normal input: an efficient-tier claude model (`claude-haiku-4-5` by
  default) with a scratch contract whose only task is to prove the contract
  was read.
- Success for the normal case means all three layers hold: the wrapper exits
  0 with its milestones in order, the Orca dispatch for that task reaches
  `completed` within `--worker-timeout`, and the worker's `SMOKE.txt` holds
  the read token the wrapper appended to the delivered contract.

Out of scope: the reused-pane path (`--terminal` with no `--worktree`), the
codex and cursor runtimes, and worker output quality. A pass here says the
pipe is open end to end; it says nothing about what the worker produced.

## The three layers and localization

What a failing run prints depends on the failure path:

- **precondition** (exit 10): one stderr line naming the failed check; no
  verdict line.
- **failure case** (exit 11): the `smoke FAIL layer=gate step=...` verdict,
  plus `failure.log`'s tail on stderr.
- **normal case** (exit 12, layers gate/orca/register/delivery/wrapper): the
  `smoke FAIL layer=<layer> step=<step>` verdict, plus `smoke.log`'s tail on
  stderr.
- **timeout** (exit 12, layer=timeout): the verdict plus the last line of
  `smoke.log` on stderr.
- **isolation** (exit 13): the stderr block naming the differing file(s) and
  the added row(s)/listing(s), plus the `smoke FAIL layer=isolation` verdict.

| exit | layer | step | look next |
|---|---|---|---|
| 10 | (precondition) | named in the stderr line | the checkout/install itself: unrendered wrapper, missing seam, `claude` not on PATH, `orca status` |
| 11 | gate | `top-tier-refusal`, `task-count-unreadable`, or `runtime-unavailable` | the refusal text in `failure.log`; confirm the scratch ledger is empty and the task count is unchanged |
| 12, wrapper exit 2 | gate | (none) | the gate's denial reason in `smoke.log` |
| 12, wrapper exit 3 | orca | `task-create`, `terminal-create`, or `dispatch` | `orca orchestration task-list --json`, then `orca terminal read --terminal <handle> --limit 40` for the pane the arrow line names |
| 12, wrapper exit 4 | register | (none) | the register denial reason in `smoke.log`; the worker is running, resolve by hand |
| 0, `class=done` | delivery | (none, a pass) | the dispatch record already read `completed`; the pane itself carries no signal for this case |
| 12, wrapper exit 5 and `class=unknown` with dispatch status `completed` | delivery | `unknown worker=completed` | `orca orchestration dispatch-show --task <task> --json`; the pane itself for what the delivery check actually saw |
| 12, wrapper exit 5 (or any exit with `class=` other than `agent-started` or `done`) | delivery | the delivery `class` (`hook-trust`, `limit`, `unknown`, ...) | `orca terminal read --terminal <handle> --limit 40` on the worktree's pane |
| 12, other nonzero | wrapper | the wrapper's own exit code | the printed `smoke.log` tail on stderr |
| 12, layer-2 timeout | worker | the last `dispatch-show` status seen | `orca orchestration dispatch-show --task <task> --json`; the worker's own home event log |
| 12, layer-3 mismatch | contract-read | `missing` or `mismatch` | `<worktree>/SMOKE.txt` directly |
| 13 | isolation | `leak` or `concurrent-writer` | the added ledger row(s) or contract copy name(s) printed to stderr |

## Exit codes

- `0` pass
- `10` a precondition failed (named on stderr); nothing was touched
- `11` the failure case did not fail the way it should have
- `12` the normal case failed at one of the three layers above
- `13` isolation broke: `$HOME/.mogui`'s ledger sha or the contracts listing
  changed during the run

## Isolation

`MOGUI_STATE_DIR` moves the wrapper's mutable state for the duration of each
invocation: the dispatch ledger, the delivered-contract copies, the gate's
tickets and known-roots file, and the event log `mogui_log.py` writes. It
does not move `$HOME` itself.

What stays shared by design, because moving it would defeat the point of a
seat-run smoke or because `MOGUI_STATE_DIR` was never meant to reach it:

- Orca's own task, dispatch, and terminal records. These persist in Orca
  after cleanup; the smoke only fences and closes the pane and worktree it
  created, it does not delete the orchestration history.
- The runtimes' real trust state. Pre-trust runs against the scratch
  worktree's real path, under the real `$HOME`, so a first visit adds a
  trust entry for that path that cleanup cannot remove. This is deliberate:
  moving `$HOME` to isolate it would also hide whatever trust dialog a real
  dispatch would hit.
- The worker's own hook events under the worker's own `$HOME` (the `#177`
  thread on `MOGUI_EVENT_LOG`): the dispatched worker process is not itself
  launched with `MOGUI_STATE_DIR` set, so whatever it writes through its own
  hooks lands in the real location.
- Every other `$HOME`-relative path the wrapper still touches outside the
  five seam-covered files: the claude transcript glob derived from the
  worktree for the active model probe (`$HOME/.claude/projects/...`, read-only);
  the codex accounts directory and `$HOME/.codex` (codex-only, not touched by a
  `--runtime claude` smoke); `$HOME/.cursor/projects` (cursor-only, not
  reached here either).

## When to run

After any change to `scripts/dispatch` on the instance, and at boot when the
seat's last recorded smoke predates the wrapper's mtime.

## Cost

One haiku worker, one scratch worktree, one to three minutes.

## Reading a failure

Read the verdict line first, then the tail of `smoke.log` the script prints
to stderr on any layer-1 failure (or the tail of `failure.log` for an
exit-11 failure-case mismatch). `smoke.log` lives under the scratch `$STATE`
directory, which cleanup removes at the end of every run, so only the
printed tail survives past the run; the full log does not. A `--keep-state`
flag that skips that removal and prints the kept path is not implemented; it
is out of scope for this round. For a layer-2 timeout, read the dispatch's
own status with `orca orchestration dispatch-show --task <task> --json` and
the pane with `orca terminal read --terminal <handle> --limit 40`. For an
isolation break (exit 13), the added ledger row(s) or contract copy name(s)
are printed to stderr so the reader can see whose write it was: `leak` means
the row or copy references this smoke's own contract sha, task id, or
dispatch id; `concurrent-writer` means it does not, and another seat wrote
the shared ledger during the run.

## Orca vocabulary measured for this contract

- `orca status --json` reports readiness as `.ok` (boolean); dispatch-smoke
  treats anything other than `true` as precondition 4 failing.
- `orca orchestration dispatch-show --task <id> --json` carries the dispatch
  under `.result.dispatch`, with `.status` the field this script polls and
  `completed` the value it waits for (measured against this contract's own
  dispatch once it finished: `status: completed`, `completed_at` set, and
  `termination_reason: null`).
- `orca worktree create --json` returns the new worktree's absolute path at
  `.result.worktree.path` and its name at `.result.worktree.displayName`.
- `orca orchestration task-list --json` requires a bound Run in the calling
  context (`error.code: "run_required"` otherwise); dispatch-smoke's
  task-count check only holds on a seat that already has one bound, which is
  the normal state for a master's own seat. A `run_required` response is
  printed as `error:run_required` on both sides of the comparison rather
  than silently treated as an unchanged count.
