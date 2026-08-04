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

Placement targets the workspace-level seat: the folder workspace of the workspace root (selector form `id:folder:<uuid>`) in a multi-repository workspace, or the primary worktree when the workspace is one repository. Repository worktrees inside a multi-repository workspace are worker seats. [orca-concepts.md](./orca-concepts.md) explains the object model and which selector forms are verified.

The actual spawn entry point is `scripts/master-succeed spawn`. A dry run is the safe way to inspect the host command before creating a terminal:

```bash
scripts/master-succeed spawn \
  --workspace-selector "id:folder:<uuid>" \
  --kickoff-text "Founding master boot" \
  --root . \
  --model example-model \
  --title "Founding master boot" \
  --json \
  --dry-run
```

When the host supports managed terminal creation, a non-dry-run spawn verifies that the returned worktree identifier matches the requested workspace selector. If it does not match, the code fails closed and closes the newly created terminal when possible.

The returned terminal handle is also verified as live, because the host may reissue handles between creation and first use. Spawn snapshots the terminal list before creating, re-queries it after, and trusts the reported handle only when it is live, new since the snapshot, and in the requested worktree. Otherwise it accepts a replacement handle only when exactly one new terminal in that worktree carries the requested pane title; the verification then reports `MATCH_REISSUED` instead of `MATCH` and the spawn report sets `handle_reissued`. Zero or multiple unresolvable candidates fail closed without touching any terminal. In that case the created terminal may still be running unmanaged, so reconcile against the host's terminal list before retrying.

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

The same rule covers agents these tools cannot read. The transcript walkers parse the session record schema they were built against (Claude Code's JSONL under its projects directory); Codex, for one, stores sessions under its own directory in a different shape. An agent whose transcript the tool cannot parse comes back as exit 2, undecidable, the same refusal the tools give any unreadable input; the master then reports the agent as unsupported instead of guessing, which is the operating rule the Step 9 wording (measured, unavailable, or unsupported) already sets for humans. Across agents the portable session key is the session id in process argv, which is what the revival check in the succession card relies on, not any one CLI's transcript format.

That probe samples recent turns, so it answers what the model is now. It does not answer whether the model changed earlier in the session, and a tail sample reads clean whenever the tail is homogeneous. For that question, walk the whole transcript:

```bash
scripts/model-drift-audit \
  --transcript ./sessions/example-session.jsonl \
  --expect example-model
```

Exit 0 means no transition, 1 means a transition or an expectation mismatch, 2 means undecidable. The third is deliberately not folded into the first. A checker that reports "could not check" and "checked and fine" the same way is worse than one that refuses to answer.

A boot measurement is a snapshot of one moment rather than a property of the session. The operating rule for when to re-measure belongs to the workspace master-operations document, which this page does not replace. What is worth recording here is why the rule exists: the observed causes were not only an unpropagated launch flag. A session reaching its quota and a credit exhaustion both changed the model mid-session, and neither announced itself.

The model field is an operational measurement, not just configuration. In field use, declared model identity and measured model identity were separated because a session could drift after launch. One first-generation master ran 319 turns on the model it declared and 164 on a different one, and the change was found at the succession audit rather than when it happened. The safe response is to record the measured value, route sensitive lanes away from the master when needed, and start a clean successor when the current session cannot be trusted to stay in the intended lane.

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

Role identity erodes from a direction that looks like diligence. A first-generation master read a product repository's own agent instruction file and then reported itself as both the workspace master and that repository's paired developer. A human caught it. The pull is structural: the master has to understand its repositories, understanding them means reading those files, and those files are written in the second person. A coordinated repository's instruction file is knowledge about a coordination target, and obeying its conventions is correct; adopting its role is not. The operating rule belongs in the workspace master-operations document.

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

Only after successor verification should the predecessor be retired. Freezing is not retirement. The tool that closes the predecessor is `scripts/master-succeed retire`; call it by that name. It resolves exactly one predecessor candidate, refuses a self-handle match, refuses ambiguous matches, dry-runs unless `--execute`, and refuses when the pane survives the close. On its own the close is an abortive path (TCP's `RST`): it does not talk to the agent inside the pane. Using it without consent is how a predecessor loses unflushed work.

## Retirement Is A Handshake

Retirement is a connection teardown between two live agents, so it is run as one.

| TCP | Master retirement | Actor |
|---|---|---|
| `FIN →` | successor tells the predecessor to stop accepting work and flush | successor |
| `← ACK` | predecessor acknowledges and enters CLOSE_WAIT | predecessor |
| half-close | predecessor's send side stays open: it may still commit and report | predecessor |
| `← FIN` | predecessor declares itself flushed with one exact line | predecessor |
| `ACK →` | successor acknowledges | successor |
| TIME_WAIT | successor measures a quiet window before closing anything | successor |
| CLOSED | `master-succeed retire --execute`, then three disappearances | successor |
| `RST` | abortive close with no consent — owner approval required | successor |

CLOSE_WAIT means these six things (an unstated convention is not a convention):

1. no new dispatches
2. no peer-mailbox acks the successor is expected to drain (or both drain twice)
3. send nothing further to orchestration; let CLOSED drop the Run binding by closing the pane. Do not invent a detach verb — the binding is per terminal and keyed to the pane, so the close is the release. Until then the predecessor's silence prevents a double ack.
4. commit uncommitted state, or report its path and content when it cannot
5. list the live workers it owns and every unfinished track by name
6. emit the agreed FIN line and nothing after it

Send the FIN into the predecessor's live prompt when it is idle; a mailbox the idle agent never reads is not delivery. Send-success is not consumption — verify by reading the pane. Choose a FIN marker the predecessor must produce that does not appear verbatim in the successor's own FIN text, or count occurrences and require at least two; quoting the marker inside the instruction string can put it on screen before the predecessor has answered.

TIME_WAIT is not ceremony. A handle can rotate without a restart, and a session can hold two processes at once (one replaying the other's transcript). Closing the instant a FIN lands can close a pane whose incarnation is being recreated — the same hazard TIME_WAIT exists for in TCP. Wait for measured quiet on both the host's last-output timestamp and a pane read, then close.

Carry the predecessor's pid and tty yourself. Host terminal lists often report `process_id: null` for the folder-workspace panes a master seat occupies, so the tool cannot invent those checks from the record. Pass what you measured:

```bash
scripts/master-succeed retire \
  --self-handle "$ORCA_TERMINAL_HANDLE" \
  --target-handle predecessor-handle \
  --target-pid <measured-pid> \
  --target-tty <measured-tty> \
  --json \
  --execute
```

Each disappearance is reported separately under `disappearances`. `pane` is `measured` or `still_present` only. `process` and `tty` may also be `skipped:<why>` when the caller did not supply a usable target. Full `CLOSED` requires all three `measured` and none `still_present`. When process or tty was skipped, status is `CLOSED_PARTIAL` so a skip cannot read as a full pass. A survivor is a refusal. Without `--execute` the command dry-runs.

Sweep the predecessor's scratchpad before CLOSED. It dies with the session and is often the only place uncommitted work had to live. Copy the tree somewhere durable that is not a git repository, then diff each file against the trunk branch and record the verdict — including when salvage value is zero.

`RST` is the only path that skips consent, and it needs owner approval. Before reaching for it, classify the pane by reading it: a limit condition, a start-screen gate, and a dead process are three different things with three different answers.

## Retirement Completion And Revival

Full `CLOSED` requires three measured disappearances, never a close command's return value alone: process (pid gone), host pane (no live handle in the host's terminal list), and tty (device and login chain gone). When process or tty could not be measured and was skipped, the tool reports `CLOSED_PARTIAL` instead — pane-only absence is not a full close. Close command return values have been wrong in both directions on real hosts; the measurement decides.

A frozen session also stays resumable forever from any terminal its agent CLI runs in, phones and remote machines included, so the boot card adds a revival check: scan running agent processes for lineage session ids (the session id is the portable key; resume flags differ per CLI), recover any unanswered owner instruction from a revived session, then take the revival through the same three disappearances. Four retired masters revived at once by a mobile resume is the measured incident behind the rule (2026-08-03).

Early planned successions changed the procedure. One handoff described the predecessor as gone while the process was still alive, so runtime state is now checked separately from handoff text. Later successions added command-line and session-path matching before retirement, plus explicit cleanup and restart of monitors under the successor's ownership. A clean succession is therefore not only "the successor read the handoff"; it is a measured transfer of role, track, process ownership, and verification responsibility.

## Lineage

Lineage is append-only observability metadata. It records the generation, parent and successor sessions, inherited role, recovery sources, inherited open tracks, verification result, and context-loss notes. It is not a bootstrap source and it is not used for runtime decisions.

The public rule is straightforward: append lineage after verification, and never use lineage as the authority for what the master should do next.

Read next: [Delegation and Review](delegation-and-review.md).
