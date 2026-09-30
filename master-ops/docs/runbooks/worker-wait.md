# worker-wait runbook

## What it does

**`scripts/worker-wait`** — one wait loop over a Run's live dispatches. It
accounts for every `dispatched` dispatch of the Run first, from the
registered pid, `lastOutputAt`, and `scripts/worker-pane-sweep`, before ever
waiting — an already-settled Run exits immediately rather than sitting
through a wait timeout it did not need. Each further pass blocks on `orca
orchestration check --wait --types worker_done,escalation,question`, acks and
silently re-arms a pure-heartbeat batch (a headless `claude -p` worker never
heartbeats at all, so this cannot be the only signal — see below), then
accounts again. The loop returns control — it does not keep running — the
moment a pass has something to act on: a real (non-heartbeat) delivery, or an
accounting row with an actionable verdict. Re-arming after that is the
coordinator's job (run `worker-wait` again after acting), same as it always
was for a bare `check --wait`; what this loop removes is the re-arming a
*boring* pass needs — a heartbeat, or a timeout with nothing actionable and
dispatches still open. `--once` runs a single accounting pass with no wait at
all: a safe, read-only snapshot that never touches the message queue, so it
is the mode to reach for when inspecting a Run you are not the coordinator
of.

Only one `worker-wait` may hold a given Run: a second one refuses with exit 2
rather than corrupting the first's wait state (measured 2026-09-29: two
waiters on one Run corrupted each other's signal file). `worker-wait` also
exits 2, never 0, when `orca orchestration worker-list` itself fails or
returns malformed JSON — a listing failure is not evidence the Run has
settled, and reporting it as one would be the exact false-success bug the
tool exists to avoid.

## Why this exists

A coordinator's `check --wait` returns on one signal or a timeout and must be
re-armed by hand; both seats measured forgetting this the same day. A worker
that dies without sending `worker_done` (API connection lost mid-turn, a
session limit, a backgrounded wait that ends the turn) leaves its dispatch
`dispatched` forever, found only when the owner happens to look at the pane.
Heartbeats do not cover this: a headless `claude -p` worker never heartbeats
at all (three of four dispatches at the ops seat had `last_heartbeat_at` null
through completion), so a heartbeat-only stall check has no signal for that
class of worker. `worker-list`/`worker-show` report `liveness` null for a
headless dispatch, which is the harness naming absence, not proof of death.
`worker-pane-sweep` already classifies every live pane; this loop is the
place that combines that classifier with the registered pid and `lastOutputAt`
into one verdict per dispatch, on a schedule, without ever acting on what it
finds.

## Verdicts

| Verdict | Condition |
|---|---|
| `working` | Pid alive and output younger than the stall window, or the sweep already says `working` |
| `DEAD` | Pid recorded and not alive (no `worker_done` — the dispatch is still `dispatched`) |
| `STALL` | Pid alive, output older than the stall window, sweep class `idle`, `shell`, `limit`, `start-screen`, `update`, or `approval` |
| `UNKNOWN` | No pid recorded and the sweep cannot classify the pane |
| `OPEN_PANE` | A settled dispatch (`completed`/`failed`/`accepted`/`abandoned`) whose pane is still listed |

A row without a recorded pid never reads `DEAD` or `STALL` — those verdicts
require a measured pid, per contract. `dispatch` cannot supply one today: it
always creates the worker's terminal through `orca terminal create`, an RPC
to the Orca host, so it never has a local OS pid to record — every real row
on this seat is a no-pid row. When a no-pid row's sweep class is one this
table has no name for (e.g. `idle` with no pid), `worker-wait` reports the
sweep class verbatim (lowercase, e.g. `idle`) rather than forcing it into
`UNKNOWN` or `STALL`; this row does not wake the caller. This is a documented
extension beyond the contract's literal verdict enum, not a sixth verdict —
the contract's four verdicts plus `OPEN_PANE` are the only verdict values the
loop reports; only `DEAD`, `STALL`, and `OPEN_PANE` wake the caller.

Only `DEAD`, `STALL`, and `OPEN_PANE` wake the caller — the loop returns
control on that row, same as a `worker_done`/`escalation`/`question`
delivery, for the coordinator to act and then re-run `worker-wait`.
`working` and `UNKNOWN` are visible in the table but never wake anything.

## What the coordinator does per verdict

- **`working`** — leave it alone.
- **`DEAD`** — read the pane first (`orca terminal read --terminal <pane>`) to
  confirm no agent is actually there; only then `orca orchestration
  worker-abandon --dispatch <id>` (fences the worker without claiming its
  process stopped — see its own `--help`). Never abandon from the table alone.
- **`STALL`** with sweep class `approval` — clear the in-scope approval per
  the review-and-routing charter section; anything else in scope is the
  owner's call.
- **`STALL`** with sweep class `limit` or `shell` — redispatch elsewhere; the
  worktree and terminal are not reusable as-is.
- **`STALL`** with sweep class `start-screen` or `update` — dismiss/restart
  per `worker-pane-sweep`'s own notes; never inject text into a start screen.
- **`OPEN_PANE`** — `scripts/worker-reap` for the settled dispatch once its
  worktree is confirmed safe to remove.
- **`UNKNOWN`** or a bare sweep-class row — read the pane; this is the
  contract's own answer for a case it cannot resolve from measured state.

`worker-wait` never closes a pane, never abandons a dispatch, and never sends
to a pane. It reports; the coordinator decides — the same rule
`worker-pane-sweep` states at its own line 19.

## Usage

```bash
# One read-only snapshot of a Run's live dispatches — safe to run from any
# seat, does not touch the message queue or take the lock.
scripts/worker-wait --once --json --run run_abc123

# The continuous loop, for the Run's own coordinator. Holds the per-Run lock
# for as long as any dispatch of the Run is `dispatched`.
scripts/worker-wait --run run_abc123

# Default --run is the Run bound to this terminal; default --stall-minutes is 10.
scripts/worker-wait --stall-minutes 5
```

`--ledger` overrides the dispatch ledger path (default
`~/.mogui/dispatch-ledger.jsonl`, the same file `scripts/dispatch-gate
register` writes to via its `--worker-pid`/`--pane` flags).

The lock lives at `~/.mogui/worker-wait/<run_id>.lock`, holding the waiter's
pid; a lock whose pid is no longer alive is taken over rather than honored.

## Related docs

- `docs/runbooks/orca-wait.md` — the same `check --wait`/deliveryId ack-chain
  protocol, for a coordinator's own inbox rather than a Run's dispatches.
- `scripts/worker-pane-sweep` — the pane classifier this loop calls once per
  pass.
- `docs/charter/05-dispatch-gate.md` — the register step that can now record
  a worker's pid and pane.
