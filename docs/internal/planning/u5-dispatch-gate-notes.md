# U5 Dispatch Gate Notes

## Design Decisions

- Dispatch cost is enforced by a deterministic character proxy: `n_agents * est_input_chars`.
- High-cost runtime fan-out is blocked before dispatch; a single high-cost worker is allowed with a warning.
- Duplicate detection uses contract content SHA-256 within the configured ledger window.
- Job registration requires an independent probe; worker self-report alone never writes a registered job.
- The ledger is append-only JSONL so shell checks, later registration, and audits share one evidence trail.

## Incident Mapping

| Incident | Rule | Enforcement |
|---|---|---|
| Large-model fan-out ignored routing policy and spent about 930k tokens | R1/R2 | Budget proxy and high-cost multi-agent routing denial |
| Forwarder dispatched the same contract twice and reported a nonexistent job | R3/R4 | Recent contract SHA duplicate denial and probe-required registration |
| A large contract sat inactive for 17 minutes without early detection | Watchdog | `check_stall` detects old mtime or progress timestamp |
| Completion reports and counters were accepted without measurement | R4 | Registration depends on probe evidence, not worker text |
