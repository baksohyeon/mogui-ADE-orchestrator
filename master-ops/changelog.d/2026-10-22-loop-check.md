Added `scripts/loop-check PROGRESS_FILE [--now ISO] [--ready-count N] [--compactions N] [--stop-file PATH]`, which reads a loop progress file and its own arguments only (no `orca`, `bd`, `gh`, or `git`).
It evaluates the six stop conditions in order: the round budget spent, the wall-clock budget spent, no eligible item open, two consecutive failures, a worker question or escalation or the owner's stop file, and a compaction passed since the start line.
It prints one `continue round=<n> ...` or `stop reason=<k>: ...` line and exits 0, 3, or 2 (a malformed file or invocation, with the line number on stderr).
`test-loop-check.sh` covers every case and a failability line per condition.
[`docs/runbooks/loop.md`](../docs/runbooks/loop.md) is the procedure the master follows around it, linked from `host-harness-inventory.md`.
