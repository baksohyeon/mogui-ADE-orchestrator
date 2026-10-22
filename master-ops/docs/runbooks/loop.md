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
3. Create `docs/loop/<YYYY-MM-DD>-<name>.md` in ops from the grammar section 7
   of the loop harness design spec (ops
   `docs/superpowers/specs/2026-10-18-loop-harness-design.md`) carries: the
   header bullets, `status: running`, an empty table.
4. Commit that file to ops before the first round.

## 3. Each round

1. Run `scripts/loop-check <file> --ready-count <n>`, where `<n>` is the
   count of open `loop-ok` items the tracker reports for this run's
   repositories.
2. A `stop reason=...` line sends the master to section 5; the loop never
   picks past a `stop` line.
3. A `continue round=<n> pick` line (with or without ` ready=unknown`): take
   the highest-priority eligible item (section 2's rule) and append a
   `picked` row for it.
4. A `continue round=<n> item=<id> state=<state>` line: resume that row from
   its own state, at the matching step below.
5. **picked → contracted.** Write the contract under `contracts/` per
   [contract conventions](contract-conventions.md) and commit it to ops. A
   contract that would add a new file to a product repository or change a
   design is not written; mark the row `blocked: needs-approval` instead and
   return to step 1 for the next item.
6. **contracted → dispatched.** Run the existing dispatch path, unchanged:
   worktree, pane, recording gate check, task creation, `scripts/dispatch`,
   register. Wait on the dispatch with
   [worker-wait](worker-wait.md) or the manual
   [orca-wait](orca-wait.md) sequence.
7. **dispatched → verifying**, on `worker_done`. Run the existing clone
   verification: scope, gates, hygiene, redaction, PR body, in the shape
   [dispatch-smoke](dispatch-smoke.md)'s localization table uses to name
   which layer a check belongs to. Then poll checks and threads.
8. **dispatched → dispatched** once, on a worker process gone with no
   `worker_done` (one relaunch on the same worktree); a second death ends the
   row `failed`. See section 4.
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
   worktree. A second death ends the item `failed`.
2. Bot rounds: at most three per item; the third unresolved re-review ends
   the item `blocked`.
3. Clone verification failure: no retry; the item ends `failed` with the
   failing check named.
4. A network or API failure at launch counts as a worker death and follows
   step 1.

## 5. On stop

1. Write `status: stopped`, the `stop-reason`, and a `next-proposal` line
   into the progress file.
2. Commit the file to ops.
3. Report to the owner with the list of merge-ready PRs and each one's
   verification summary.
4. The owner approves the merges in one answer; the master merges them in
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
4. Run `scripts/loop-check` again. A `compactions-seen` of 1 or more stops
   the run (`stop reason=6`) once the item in flight reaches its next stable
   state: a dispatched item waits for `worker_done`, a verifying item
   finishes verification.

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
| `stop reason=1: round budget spent (<n>/<rounds>)` | the round budget is spent | section 5 |
| `stop reason=2: wall-clock budget spent (<h.h>h/<hours>h)` | the wall-clock budget is spent | section 5 |
| `stop reason=3: no eligible item` | `--ready-count 0` and nothing in flight | section 5 |
| `stop reason=4: two consecutive failures (<id>, <id>)` | the last two completed rows both failed | section 5 |
| `stop reason=5: worker question on <id>` | a row is `blocked: worker-question` | section 5 |
| `stop reason=5: escalation on <id>` | a row is `blocked: escalation` | section 5 |
| `stop reason=5: stop file present` | the owner's stop file exists | section 5 |
| `stop reason=6: compaction passed; finish the item in flight and stop` | one compaction has passed | section 6 |

Exit codes: `0` on every `continue` line, `3` on every `stop` line, `2` on a
malformed progress file or a `--now` earlier than `started`, with the line
number on stderr. The runbook forbids picking when `loop-check` says `stop`.
