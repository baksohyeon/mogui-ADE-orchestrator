# Loop runbook

The procedure the master follows around `scripts/loop-check` for a bounded run
over `loop-ok` tracker items. The script evaluates a progress file and prints
one verdict line; this runbook is what the master does with that line.

## 1. What the loop is and is not

The loop lets the master carry several tracker items from `ready` to a
terminal state inside one owner-approved stretch, spending context on
verification instead of on being prompted once per round. It is a procedure
the master runs inside its own session, not a new agent, a background
process, or a new dispatch path: every round still goes through the existing
contract, dispatch, and verification steps, unchanged. Merges, architectural
items, and anything the standing rules route to the owner stay outside it.

## 2. Before a run

1. Get the owner's approval by name, with the budget: `rounds=<n>
   hours=<h>` (defaults 3 and 4). Write that sentence into the progress
   file's `approved` line.
2. Label the eligible tracker items `loop-ok` by hand. The loop never labels
   an item itself.
3. Create `docs/loop/<YYYY-MM-DD>-<name>.md` in ops with `status: running`
   and an empty table, following this grammar:

   ```
   # Loop <name>                      first line, required
   - started: <ISO 8601 with offset>  required
   - budget: rounds=<int> hours=<int> required
   - approved: <free text>            required, non-empty while status: running
   - compactions-seen: <int>          required
   - status: running | stopped        required
   - stop-reason: <text or empty>     required line, value may be empty
   - next-proposal: <text or empty>   required line
   <blank line>
   | round | item | contract | state | task | dispatch | pr | sha | updated |
   |---|---|---|---|---|---|---|---|---|
   ```

   State vocabulary: `picked`, `contracted`, `dispatched`, `dispatched:
   relaunched`, `verifying`, `bot-round(<n>)`, `merge-ready`, `failed` or
   `failed: <text>`, `blocked` or `blocked: <text>`.
4. Commit that file to ops before the first round.

## 3. Each round

1. Run `scripts/loop-check <file> --ready-count <n>`, where `<n>` is the
   count of open `loop-ok` items the tracker reports for this run's
   repositories.
2. A `stop reason=...` line sends the master to section 5; the loop never
   picks past a `stop` line. When the line carries a trailing ` drain
   item=<id> state=<state>`, section 5 starts with that drain.
3. A `continue round=<n> pick` line (with or without ` ready=unknown`): take
   the eligible item with the lowest priority number first (`P0` before
   `P1`), then the oldest `created` date, then the lexically smallest id.
   `bd ready --json` is the source:
   `bd ready --limit 0 --json --label loop-ok --exclude-label blocked --exclude-label architectural | jq -r 'sort_by(.priority, .created_at, .id)[0].id'`
   Append a `picked` row for the item this selects.
4. A `continue round=<n> item=<id> state=<state>` line: resume that row from
   its own state, at the matching step below. A `dispatched` or `dispatched:
   relaunched` row resumes by waiting on its existing dispatch (the row's
   `task` and `dispatch` columns, with `orca orchestration dispatch-show
   --task <task>`) with [worker-wait](worker-wait.md), never with the manual
   [orca-wait](orca-wait.md) sequence alone: `orca-wait` only waits for a
   message and cannot detect a worker that dies without `worker_done`, while
   `worker-wait` reports `DEAD` and `STALL` from measured pid and pane state.
   A `DEAD` verdict is the worker-death case of section 4. Never resume by
   re-entering step 6's dispatch path; it relaunches, once, only on the
   worker-death case in section 4.
5. **picked → contracted.** Write the contract under `contracts/` per
   [contract conventions](contract-conventions.md) and commit it to ops. A
   contract that would add a new file to a product repository or change a
   design is not written; mark the row `blocked: needs-approval` instead and
   return to step 1 for the next item. A `blocked: needs-approval` row does
   not spend one of the run's rounds; `loop-check` excludes it from the
   round count (section 8, reason 1).
6. **contracted → dispatched.** Run the existing dispatch path, unchanged:
   worktree, pane, recording gate check, task creation, `scripts/dispatch`,
   register. Wait on the dispatch with
   [worker-wait](worker-wait.md) or the manual
   [orca-wait](orca-wait.md) sequence.
7. **dispatched → verifying**, on `worker_done`. Run the existing clone
   verification: scope, gates, hygiene, redaction, PR body, in the shape
   [dispatch-smoke](dispatch-smoke.md)'s localization table uses to name
   which layer a check belongs to. Then poll checks and threads.
8. **dispatched → dispatched: relaunched**, once, on a worker process gone
   with no `worker_done` (one relaunch on the same worktree); write the
   row's state as `dispatched: relaunched`, rewriting its `task` and
   `dispatch` columns to the new ids in the same edit, so the row never
   points back at the abandoned dispatch. A second death on a `dispatched:
   relaunched` row ends the item `failed: worker-died-twice`. `loop-check`
   treats both states as in flight; resume either state by waiting on its
   existing dispatch, not by creating another task. See section 4.
9. **dispatched → blocked**, on a worker `question` or `escalation`. The loop
   stops here (`stop reason=5`); it does not pick further while that is open.
10. **verifying → failed**, on a clone verification failure. No retry; name
    the failing check in the row.
11. **verifying → bot-round(n+1)**, when checks are green and threads are
    still open and `n < 3`; **verifying → blocked: bot-rounds-exhausted**
    when `n = 3` (section 8 of the spec, pinned in the plan's review focus).
    `loop-check` only reads the count carried in the state text; it does not
    decide this transition. Reply per thread per
    [review voice](review-voice.md) rules 1-11.
12. **bot-round → verifying**, on the worker's push. Return to step 7.
13. **verifying → merge-ready**, when checks are green, zero threads are
    unresolved, and no bot reply is unanswered. The item stays open with its
    PR number in the row; the loop does not merge it (section 5).
14. After every transition above: rewrite the row in place, commit the
    progress file to ops, and return to step 1.

## 4. Retries

Verbatim from the spec's retry limits:

1. A worker that dies without `worker_done` gets one relaunch on the same
   worktree, with edits preserved: fence the dead dispatch with
   `worker-abandon` first, then create a new task and dispatch into the same
   worktree, and write the row's state `dispatched: relaunched`, rewriting
   its `task` and `dispatch` columns to the new ids in the same edit. A
   second death on a `dispatched: relaunched` row ends the item `failed:
   worker-died-twice`.
2. Bot rounds: at most three per item; the third unresolved re-review ends
   the item `blocked`.
3. Clone verification failure: no retry; the item ends `failed` with the
   failing check named.
4. A network or API failure at launch counts as a worker death and follows
   step 1.

## 5. On stop

1. If the verdict line carries a trailing ` drain item=<id> state=<state>`
   (every stop reason can carry one, not only reason 6), finish that item to
   its next stable state before anything else: a `dispatched` or
   `dispatched: relaunched` row waits on its existing dispatch (section 3,
   step 4) for `worker_done` and is verified, relaunching only on the
   worker-death case in section 4; a `verifying` or `bot-round` row is
   verified to `merge-ready`, `failed`, or `blocked`. One exception: when the
   stop reason is `stop file present` and the row is `dispatched` or
   `dispatched: relaunched`, fence it with `worker-abandon` and write the
   row's state `blocked: owner-stopped` instead of waiting: the owner's stop
   file means stop now, not after one more wait. Only then continue to
   step 2.
2. Write `status: stopped`, the `stop-reason`, and a `next-proposal` line
   into the progress file.
3. Commit the file to ops.
4. Report to the owner with the list of merge-ready PRs and each one's
   verification summary.
5. The owner approves the merges in one answer; the master merges them in
   order, with the existing per-PR re-check
   ([contract conventions](contract-conventions.md) clause 6 and clause 7)
   before each merge. The loop itself never merges.

## 6. Compaction and resume

1. After compaction, or a resume, read the progress file and the tracker
   before any mutation.
2. Run `orca orchestration run-current`, since a resume can leave the
   coordinator terminal unbound.
3. If a compaction happened since the start line, increment
   `compactions-seen` in the header.
4. Run `scripts/loop-check` again.
5. On `stop reason=6: compaction passed; drain item=<id> state=<state>`,
   drain per section 5, step 1, then continue at section 5, step 2.
6. On `stop reason=6: compaction passed; nothing in flight`, go straight to
   section 5, step 2; there is nothing to drain.

## 7. Succession

1. The successor receives the progress file's path as an active track in the
   kickoff card.
2. It does not continue the run. It reports the file's current state and
   waits for a new owner approval before touching it.

## 8. Verdict table

| `loop-check` prints | Meaning | Go to |
|---|---|---|
| `continue round=<n> pick` | an eligible item exists; pick it | section 3, step 3 |
| `continue round=<n> pick ready=unknown` | `--ready-count` was not passed; pick as above | section 3, step 3 |
| `continue round=<n> item=<id> state=<state>` | a row is in flight; resume it | section 3, step 4 |
| `stop reason=stopped: <stop-reason>` | the header already says `stopped` | section 5 |
| `stop reason=1: round budget spent (<n>/<rounds>)` | the round budget is spent; `<n>` excludes `blocked: needs-approval` rows | section 5 |
| `stop reason=2: wall-clock budget spent (<h.h>h/<hours>h)` | the wall-clock budget is spent | section 5 |
| `stop reason=3: no eligible item` | `--ready-count 0` and nothing in flight | section 5 |
| `stop reason=4: two consecutive failures (<id>, <id>)` | the last two completed rows both failed | section 5 |
| `stop reason=5: worker question on <id>` | a row is `blocked: worker-question` | section 5 |
| `stop reason=5: escalation on <id>` | a row is `blocked: escalation` | section 5 |
| `stop reason=5: stop file present` | the owner's stop file exists | section 5 |
| `stop reason=6: compaction passed; drain item=<id> state=<state>` | one compaction has passed with an item in flight | section 6 |
| `stop reason=6: compaction passed; nothing in flight` | one compaction has passed with nothing in flight | section 6 |

Every stop line above except reason 3 (which requires nothing in flight by
definition) and reason 6 (which states draining in its own two message
variants) can carry a trailing ` drain item=<id> state=<state>` when a row is
in flight at the moment of the stop; section 5, step 1 is what to do with it.

Exit codes: `0` on every `continue` line, `3` on every `stop` line, `2` on a
malformed progress file (the line number on stderr, including a `--now`
earlier than `started`) or a malformed option (the option name on stderr).
The runbook forbids picking when `loop-check` says `stop`.
