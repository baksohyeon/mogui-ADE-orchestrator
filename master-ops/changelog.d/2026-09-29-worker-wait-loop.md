One wait loop over live dispatches, with dead and stall verdicts from measured state (2026-09-29):

- `master-ops/scripts/worker-wait`: new, self-contained script — one loop per Run over
  `check --wait --types worker_done,escalation,question`. A pure-heartbeat batch is acked and the
  wait re-armed silently (parsed with `raw_decode`, since keepalive documents precede the result
  in the same stream); anything else wakes the caller and is left unacknowledged for the
  coordinator to ack after acting. `--once` runs a single accounting pass with no wait at all — a
  read-only snapshot safe to run from any seat. Before arming the wait, a second `worker-wait` on
  the same Run refuses with exit 2 via a lock file at `~/.mogui/worker-wait/<run_id>.lock` holding
  the waiter's pid; a lock whose pid is no longer alive is taken over rather than honored.
- Accounting per pass, from `orca orchestration worker-list --run <id>`, `orca terminal list`
  (`lastOutputAt`), the registered pid (via `scripts/dispatch-gate register`'s new fields, read
  from the dispatch ledger), and one `scripts/worker-pane-sweep` call: `working`, `DEAD` (pid
  recorded, not alive), `STALL` (pid alive, output stale, sweep class idle/shell/limit/
  start-screen/update/approval), `UNKNOWN` (no pid, sweep cannot classify), and `OPEN_PANE` for a
  settled dispatch whose pane is still listed. A no-pid row can never read `DEAD` or `STALL` — both
  require a measured pid — and, when the sweep does classify a no-pid row as something other than
  `working`, the sweep class is reported verbatim rather than forced into `UNKNOWN`, since every
  real row on this seat is a no-pid row (`dispatch` creates a worker's terminal through `orca
  terminal create`, an RPC, so it never has a local pid to record). Only `DEAD`, `STALL`, and
  `OPEN_PANE` wake the caller; the loop never closes a pane, never abandons a dispatch, and never
  sends to a pane.
- `scripts/dispatch-gate register` gains `--worker-pid` and `--pane` (both optional), stored on
  the ledger row only when given. `master-ops/scripts/dispatch` now passes `--pane "$TERMINAL"`;
  it never passes `--worker-pid`, since it always creates the worker's terminal through the Orca
  RPC rather than launching the process itself.
- Tests: `tests/test_worker_wait.py` (fake `orca` and `ps` on `PATH`) covers the heartbeat
  ack-and-rearm, an unacked `worker_done` wake, `DEAD`/`STALL`/`working`/`UNKNOWN` verdicts (pure
  and end-to-end through the real `worker-pane-sweep`), `OPEN_PANE`, the ledger-to-pid/pane index,
  a held lock refusing a second waiter, and a stale lock being taken over.
  `tests/test_dispatch_gate.py` gained the `--worker-pid`/`--pane` round-trip through the ledger,
  both via the API and the CLI, and confirms omitted fields write no placeholder keys.
  `master-ops/scripts/test-worker-wait.sh`: `--once --json` against a scratch ledger and fake
  `orca` prints the table and exits 0, and a held lock exits 2 — each case also run against a
  sed-mutated copy of the script to prove it can fail, then against the original to confirm it
  passes again.
- Runbook: `master-ops/docs/runbooks/worker-wait.md` — the verdict table, what the coordinator
  does on each verdict, and the single-waiter rule. Cross-linked from
  `master-ops/docs/charter/05-dispatch-gate.md`.
- Review hardening (cubic and CodeRabbit, same PR): the loop accounts once before ever waiting
  (an already-settled Run no longer sits through a wait timeout) and returns immediately on a real
  delivery or an actionable verdict instead of looping past it — the prior shape re-entered
  `check --wait` with the same already-seen ack after printing a delivery, which the orchestration
  contract replays forever until acked, and a heartbeat-only batch was re-armed inside an internal
  loop that could starve accounting for as long as heartbeats kept arriving. `_pid_alive` and the
  ledger's `worker_pid` now distinguish "confirmed not running" from "could not be measured" (bad
  pid data, empty/whitespace pid, `ps` missing or erroring) — only a confirmed answer may read
  `DEAD`; an unmeasurable one reads `UNKNOWN`. The `STALL` verdict now requires a measured age, not
  just a stall-shaped sweep class, so a pid alive with no readable `lastOutputAt` no longer reads
  `STALL` from the sweep class alone. `orca orchestration worker-list` failing or returning a
  well-formed `{"ok": false, ...}` envelope now raises rather than being read as zero dispatches
  (which would exit 0, claiming the Run had settled). The lock is now acquired with
  `os.open(O_CREAT|O_EXCL)` instead of an `exists()`-then-`write_text()` check, closing the
  race the single-waiter rule exists to close. `master-ops/scripts/test-worker-wait.sh`'s lock
  mutant now asserts the bypassed-lock exit code exactly (`-eq 0`) instead of merely `-ne 2`, and
  no longer depends on GNU `timeout` (not present on macOS by default) since the fixed initial
  accounting pass makes the bypassed case exit before any wait call.
- Tracker: `mgm-pstc`.
