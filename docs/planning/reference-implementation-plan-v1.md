# Reference Implementation Plan v1

> Status: Accepted plan (2026-07-16). Architecture is FROZEN upstream — this plan decomposes it into implementable components and adds nothing.

## Implementation Units

| Unit | Responsibility |
|---|---|
| U1 Bootstrap | Load charter + role state; budget-bounded L0/L1 injection |
| U2 Context Resolver | `resolve(path, manifest) -> ContextDescriptor` (kind, identity, capabilities) |
| U3 Workspace Runtime | Track L1 cache (SSOT = Work Ledger), release coordination state |
| U4 Repository Runtime Loader | Lazy per-repo harness bootstrap for workers |
| U5 Worker Scheduler | dispatch / lease / reap, budget enforcement |
| U6 Approval Manager | Gate classification (G0–G3), proposal registry, PAE enforcement |
| U7 Role Runtime | Role state, lock, switch procedure |
| U8 Recovery Manager | Recovery flow 0–6 executor |
| U9 Succession Manager | Trigger detection (immediate/advisory), freeze, thin handoff, successor verification, retirement |
| U10 Lineage Recorder | Append-only writer, 13-field schema validation, **no read API** (lineage never feeds runtime) |
| U11 Observability | Deterministic probes, monitors, acceptance log, baselines |
| U12 Adapter Layer | Only pathway to external tools |

## Invariants carried from the frozen architecture

- Master reads/inspects/verifies; workers write implementations; humans gate shared/irreversible writes.
- Proposal → Approval → Execution. Worker self-reports are never evidence.
- Track SSOT split: active-track execution state = Work Ledger / long-term plans = Git specs / thin handoff = one-shot pointer bundle / in-session registry = L1 cache.
- Succession replaces only the master session; monitors/probes/leases are re-armed, never inherited.
- Recovery order: charter+role → handoff+ledger → workspace Git SSOT → lazy repo runtimes → trace archive on miss only → re-arm → verify → retire predecessor.
- Runtime state is never documented; generated views are never stored; operational logs never feed runtime.

## Implementation order

U2 → U6 → U12(git) → U1 → U10 → U11(minimal probe+acceptance log) → U12(work-ledger)+U3 → U12(substrate/executor)+U5 → U8 → U9 (succession scenario = the integration test of everything).

## MVP acceptance (evidence-based)

(a) bootstrap loads charter+role state within budget; (b) one full delegation loop: dispatch → artifact → independent verification → acceptance log; (c) succession scenario test: handoff → successor recovery → verification checklist → lineage entry. All judged by deterministic probes.
