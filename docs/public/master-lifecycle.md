The master lifecycle is a measured loop: found a clean session, boot it with durable context, operate through promotion rules, and succeed it with verification.

# Master Lifecycle

A master session is long-lived, but it is not immortal. This runtime treats a master as a generation in an operational lineage. Each generation boots, coordinates work, promotes accepted state, and eventually hands control to a clean successor.

## Lifecycle At A Glance

```text
founding spawn -> boot measurement -> steady state -> clean succession -> lineage record
```

## Founding Spawn

The onboarding guide owns the full first-run procedure. It separates the installer conversation from the Generation 1 master session so the master starts with clean context and auditable placement.

Use the repository onboarding guide as the source of truth:

- [master-ops/ONBOARDING.md](../../master-ops/ONBOARDING.md)

The actual spawn entry point is `scripts/master-succeed spawn`. A dry run is the safe way to inspect the host command before creating a terminal:

```bash
scripts/master-succeed spawn \
  --workspace-selector polsia \
  --kickoff-text "Founding master boot" \
  --root . \
  --model example-model \
  --title "Founding master boot" \
  --json \
  --dry-run
```

When the host supports managed terminal creation, a non-dry-run spawn verifies that the returned worktree identifier matches the requested workspace selector. If it does not match, the code fails closed and closes the newly created terminal when possible.

## Boot Measurement

Boot is a measurement step, not a guess. The bootstrap command reads the charter, optional handoff, role state, budget usage, and duplicate-session warnings.

```bash
scripts/master-bootstrap \
  --charter master-ops/docs/MASTER-OPERATIONS.md \
  --handoff ./handoffs/latest.md \
  --session-id example-session \
  --json
```

When a session transcript is available, model identity can be checked from recent assistant events:

```bash
scripts/model-identity-probe \
  --transcript ./sessions/example-session.jsonl \
  --expect example-model
```

If the host cannot expose a measured model field, report that as unavailable. Do not infer the actual model from a launch flag.

The model field is an operational measurement, not just configuration. In field use, declared model identity and measured model identity were separated because a session could drift after launch. The safe response is to record the measured value, route sensitive lanes away from the master when needed, and start a clean successor when the current session cannot be trusted to stay in the intended lane.

## Steady State

Normal operation is continue-and-compact. The master should promote accepted knowledge, active tracks, and open decisions into durable stores before context pressure becomes urgent.

The live bootstrap entry point is intended for session-start wiring. It is designed to emit a bounded block and degrade to a fallback line instead of killing boot:

```bash
scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

The read-only L1 digest loop observes configured repositories, ledger tails, job logs, and process patterns, then writes a digest according to its config:

```bash
scripts/l1-digest tick --config ./ops/l1-digest.json
```

> Note: The digest loop observes and records. Work and acceptance remain outside the digest module.

Long-running sessions should be treated as finite. In an intentional context-limit exercise, the master kept coordinating work near the visible limit, but the next compacted turn exposed a recall and hook-coverage gap. The lesson is not that a full context window is safe. The lesson is that context pressure should be measured, accepted state must already be in durable stores, and compaction or succession should be chosen from evidence rather than from optimism.

## Clean Succession

Succession is explicit. The current master may propose succession when context pressure is high or a natural milestone is reached, but advisory signals do not automatically spawn a successor.

You can classify a trigger with:

```bash
scripts/master-succeed detect \
  "succession now" \
  --context-ratio 0.65 \
  --json
```

The current master builds a thin handoff from structured state:

```bash
scripts/master-succeed handoff \
  --spec ./ops/handoff-spec.json \
  --json
```

The successor then proves recovery through a report shape consumed by:

```bash
scripts/master-succeed verify-successor \
  --report ./ops/recovery-report.json \
  --json
```

Only after successor verification should the predecessor be retired. The retire command resolves exactly one predecessor candidate and refuses ambiguous matches:

```bash
scripts/master-succeed retire \
  --self-handle successor-handle \
  --target-handle predecessor-handle \
  --json
```

Add `--execute` only when the operator intends to close the predecessor terminal.

Early planned successions changed the procedure. One handoff described the predecessor as gone while the process was still alive, so runtime state is now checked separately from handoff text. Later successions added command-line and session-path matching before retirement, plus explicit cleanup and restart of monitors under the successor's ownership. A clean succession is therefore not only "the successor read the handoff"; it is a measured transfer of role, track, process ownership, and verification responsibility.

## Lineage

Lineage is append-only observability metadata. It records the generation, parent and successor sessions, inherited role, recovery sources, inherited open tracks, verification result, and context-loss notes. It is not a bootstrap source and it is not used for runtime decisions.

The public rule is straightforward: append lineage after verification, and never use lineage as the authority for what the master should do next.

Read next: [Delegation and Review](delegation-and-review.md).
