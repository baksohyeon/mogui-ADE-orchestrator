# 09 — Spawn The Founding Master, Then Its Boot Smoke (Steps 8–9)

Load rule: read this file only when Step 8 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `10-card-and-retire.md`.

## Step 8. Spawn the founding master through orchestration

**Position and action:** Step 8 begins with the workspace prepared: create a Run and Task, spawn exactly one placement-verified Generation 1 master, attach its worker Dispatch, and wait for `worker_done`.

**Why/caution:** Supervised dispatch is Orca orchestration only; raw terminal polling and vendor-direct CLIs are non-compliant, and failures remain closed.

### Owner script (kind ELI5, adapt to the owner's language)

Where we are: everything the Master needs is in place; the Herald has prepared the book, the seat, and the rules. What we decide next: whether to raise the Master now or defer. Explain in plain words: we will open one new Orca terminal in the workspace seat we recorded earlier, hand it a kickoff note, and wait until it reports its first boot went clean; the owner does not need to type anything during this. Keep the summoning frame grounded: raising the Master means creating one new verified terminal, not magic. Ask for confirmation to spawn now or defer.

### Agent-only preparation (not shown to the owner)

Reload the durable placement result from the seat step and confirm the selector still resolves on the host (`ORCA terminal list --worktree <selector> --json`). That listing is also the empty-seat gate: it must show **zero terminals in the seat**. Any existing terminal there — a leftover seat-check terminal, or a master from an earlier interrupted run of this step — is a hard stop: report it to the owner and do not spawn, because exactly one master may exist and a re-entered session cannot assume its earlier spawn failed. Only an empty seat proceeds; the spawn itself verifies placement against this selector again. Write a kickoff file in the Herald voice but with exact technical facts: Generation 1, this installer as faithful Herald and founding origin, the callsign from the user-rules step, the boot sequence (rehydrate ops docs, declare Role State, measure model and placement), the initial queue, and the requirement to report the orchestration Task complete. The kickoff should frame the Master as raised only beside the plain statement that a new Orca terminal has been created and verified.

The kickoff file also hands the newborn master the installer retirement switch: this installer's terminal handle, pty id when Orca exposes it, session id when Orca exposes it, and the exact close command form `ORCA terminal close --terminal <installer handle> --json`. Include a warm resume note before that kill switch, stating that the installation is complete once Step 10 verification passes, the operating card has been printed, the master terminal must remain running, and any later installer resume should treat itself as retired. If the master is proven absent later, do not rerun Founding; route recovery through `docs/runbooks/succession-boot-card.md`. If the installer handle, pty id, or session id cannot be measured, write `unavailable` for that field in the kickoff and do not invent it.

Before launching any worker, follow `docs/MASTER-OPERATIONS.md` §3: MEASURE the installed agent CLI's non-interactive approval flags from `--help` and never guess them.

Confirm `{{RUNTIME_ROOT}}/config/instance-runtime.json` still carries the onboarding answers (`master_host_runtime`, and `transcript_globs` when measured). Use that file (or `MOGUI_MASTER_HOST_RUNTIME` / `MOGUI_TRANSCRIPT_GLOB` env overrides) for launch and model-probe guidance; do not reintroduce a hardcoded host runtime or transcript path. When a value is missing, treat it as unconfigured and measure or ask rather than guessing.

Before attaching a Codex worker, run `{{RUNTIME_ROOT}}/scripts/codex-worker-pretrust <worktree-path>` as the pre-trust step.

### Agent-only command sequence (do not paste to the owner)

Run this supervised path with the resolved `ORCA` executable:

```bash
G={{RUNTIME_ROOT}}/scripts/dispatch-gate
L=~/.mogui/dispatch-ledger.jsonl
"$G" --ledger "$L" check \
    --runtime <runtime> \
    --model "{{MODEL_ID}}" \
    --contract <contract file> \
    --agents 1 \
    --est-chars <estimated input chars> \
    --completion-channel orchestration
ORCA orchestration run-create --objective "Found and verify the Generation 1 master" --json
ORCA orchestration task-create --spec "Run the byte-identical founding kickoff file and complete Step 9 boot smoke" --json
"{{RUNTIME_ROOT}}/scripts/master-succeed" spawn \
    --workspace-selector <durable placement selector from the seat step, id: prefixed> \
    --kickoff-file <kickoff file> \
    --root "{{WORKSPACE_ROOT}}" \
    --model "{{MODEL_ID}}" \
    --title "Gen-1 founding boot" \
    --json
ORCA terminal wait --terminal <verified live handle> --for tui-idle --timeout-ms 60000 --json
ORCA orchestration dispatch --task <task id> --to <verified live handle> --inject --json
"$G" --ledger "$L" register \
    --job-id <job id> \
    --probe-cmd "<command proving the job-id appears in an artifact>" \
    --orchestration-task <task id>
ORCA orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json
```

Require the gate `check` to return `allow: true` before spawning or attaching the worker. After the Dispatch artifact exists, run `register` with that exact orchestration Task ID before waiting for final completion evidence.

Require placement verification `MATCH` or `MATCH_REISSUED`; the latter must include `handle_reissued: true` and its adopted live handle.

### Verify (Step 8)

- the seat was measured empty before spawning (no pre-existing terminal in the selector's seat)
- a Run is bound, one Task exists, and its Dispatch is attached to the verified worker
- exactly one new master process/session exists
- placement is `MATCH` or valid `MATCH_REISSUED`
- kickoff content received by the master matches the kickoff file byte-for-byte
- the kickoff gives the master the installer kill switch and warm resume note
- the coordinator processes and acknowledges deliveries, answers questions through orchestration, and waits until that Task's `worker_done`

### If fail

- On any failure, do not retry with a filesystem path selector, do not boot the master in this installer, and do not create a second session. After settings changes, always spawn a fresh session.

## Step 9. The first master boot smoke (runs inside the new master session)

**Position and action:** Step 9 runs inside the new master session: declare its role, measure identity and placement, record lineage, and report completion. The installer does not perform this boot on the master's behalf; this section is the content the kickoff file points the master at.

**Why/caution:** Model identity is measured, unavailable, or unsupported, never guessed.

The master asks for the initial role or approval to start in Maintenance, plus permission for local read-only model and seat checks. It updates `docs/runbooks/role-state.md` for Generation 1, declares Role State in conversation (including the callsign), measures configured and actual model when exposed, captures placement evidence, appends Generation 1 to `docs/lineage/MASTER-LINEAGE.md`, keeps the installer kill switch and warm resume note for Step 10, then sends `worker_done` exactly once for the active Dispatch.

### Verify (Step 9)

- Role State has one active role and Role Lock is enabled
- model measurement is reported as measured, unavailable, or unsupported
- placement evidence includes the host pane/worktree selector, process cwd under `{{WORKSPACE_ROOT}}`, and session artifact/log namespace
- no placeholders remain unless the user intentionally deferred them
- the founding Task and Dispatch complete through `worker_done`
