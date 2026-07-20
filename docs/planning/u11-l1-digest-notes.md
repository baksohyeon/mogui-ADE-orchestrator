# U11 L1 Digest Notes

## Design Decisions

1. L1 implements only SENSE, TRIAGE, RECORD, and PACE; WORK and VERIFY remain outside this module.
2. Collectors are thin local probes, while triage and rendering accept injected observations for deterministic tests.
3. Repo drift is classified as echo only when the dispatch ledger tail explicitly references the repo.
4. Baseline JSON is updated only for expected repo drift, including first-run bootstrap.
5. The CLI is a one-shot tick command; it prints and writes one markdown digest, then exits 4 on unexplained drift.

## Duty Cycle Mapping

| Duty cycle | Implementation |
|---|---|
| SENSE | `collect_observations()` reads git state, dispatch ledger tail, watchdog log status, and pgrep liveness. |
| TRIAGE | `triage_snapshot()` compares injected observations with baseline JSON and ledger evidence. |
| RECORD | `render_digest()` emits markdown in unexplained, job status, repo drift, ledger summary, pace order. |
| PACE | `suggest_next_interval_seconds()` returns 600 seconds when work is active, otherwise 1800 seconds. |
