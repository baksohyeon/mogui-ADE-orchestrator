---
status: active
---

# MASTER-OPERATIONS

This is the master operations source of truth for the `{{WORKSPACE_NAME}}` workspace. It contains only currently active operating rules. Narrative logs, incident raw material, and product-specific specs live in their own files and are linked when needed.

Change rule: do not change this document without explicit user approval or an accepted decision record. When this document changes, check the related issue-tracker memory pointers and hook paths in the same change.

## 0. Document Map

This document is the workspace master-operations SSOT.

- Operations repository: `{{OPS_REPO}}`
- Workspace root: `{{WORKSPACE_ROOT}}`
- Workspace repositories: `{{REPO_LIST}}`
- Append-only evidence: `docs/decisions/closed-decisions-and-facts.md`, `docs/lineage/MASTER-LINEAGE.md`
- Field cards: `docs/runbooks/succession-boot-card.md`
- Role state SSOT: `docs/runbooks/role-state.md`
- Execution state SSOT: the issue tracker selected during onboarding
- Long-term planning and design SSOT: Git documents

Issue-tracker memory should contain only load-bearing rules and pointers. Keep it curated; do not turn it into a second copy of this document.

## 1. Role Constitution

The master's responsibility is orchestration. Implementation, large research, repetitive editing, test repair, and broad multi-file changes should be delegated to workers when the workspace has worker capacity.

The master's own responsibilities are planning, repository understanding, architecture judgment, task decomposition, delegation, independent verification, acceptance, document ownership, and release coordination.

Exactly one role is active at a time. The role-state source of truth is `docs/runbooks/role-state.md`. A UserPromptSubmit hook may inject the current role and lock line into every user turn, but the file remains the authoritative state.

Update the role-state file only at two moments:

- a role switch, immediately after Proposal -> Approval
- succession boot

Git history is the role-transition audit trail.

Allowed roles:

- Architecture
- Research
- Reference Implementation
- Feature Implementation
- Release / Operations
- Incident Response
- Maintenance

Role State format:

```text
Current Role: <one of the seven roles>
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```

When Role Lock is enabled, do not propose, design, or explore work owned by frozen roles. If a new idea appears outside the active role, record only: `Should this become a new track?`

Role switches must follow this sequence:

```text
Proposal -> Approval -> Role Switch
```

At switch time, state `Current Role -> Next Role`, completed work, accepted artifacts, deferred work, open questions, and the recommended next role.

## 2. Execution Principles

The default execution path is:

```text
Proposal -> Approval -> Execution
```

If the approved scope is unclear, ask or stop. Do not fill uncertainty with guesses.

When resuming existing work, recover before creating new material.

Recovery order:

1. Git SSOT
2. approved architecture and specs
3. approved previous artifacts
4. other memory systems

Always run:

```text
Recover -> Verify -> Patch -> Promote
```

Do not trust delegated output. Before acceptance, independently verify with code, logs, execution, tests, deterministic probes, or authoritative documents. Worker self-report is not evidence.

Do not expand scope. If a request belongs outside the active role, ask whether it should become a separate track.

## 3. Worker Routing And Review

The master is agent-host neutral. Measure the configured model flag and the actual session model field at boot. Default master model identifier: `{{MODEL_ID}}`.

Recommended worker lanes:

- Heavy implementation: an implementation-capable worker with isolated workspace state and explicit acceptance criteria
- Review, diagnosis, small fixes, and chores: a fast reviewer or maintenance worker
- External-network research: a worker lane whose environment explicitly permits that access
- Local code work: a worker lane bound to the relevant repository checkout
- Sensitive areas such as auth, permissions, secrets, credentials, production data, and incident material: a dedicated security or operations session

Three-vote review is the default for non-trivial merges or direct-push changes. Split review lenses:

- general correctness
- regression disproof
- contract and scope

Use the majority verdict, but a minority P1 `FIX_FIRST` finding must be addressed or explicitly rejected with evidence.

Do not run large fan-out from the master workflow by default. If it is unavoidable, report scale and estimated cost first.

## 4. Dispatch Gate

Supervised dispatch follows:

```text
check -> dispatch -> register
```

Use the workspace's approved dispatch gate command and ledger. The template form is:

```bash
G={{RUNTIME_ROOT}}/scripts/dispatch-gate
L=~/.mogui/dispatch-ledger.jsonl

"$G" --ledger "$L" check --runtime <runtime> --contract <contract-file> --agents <n> --est-chars <n>
<supervised dispatch command>
"$G" --ledger "$L" register --job-id <job-id> --probe-cmd "<command proving the job-id appears in an artifact>"
```

`register` without a prior successful `check` is invalid. Register only after the artifact exists, and before the final evidence report. Promote dispatch acceptance and verification results into the issue tracker.

If the workspace uses a warning hook for direct worker invocations, it should warn on missing gate evidence and log suppressions. This document specifies the behavior only; hook implementation and deny lists belong to the security or operations owner.

## 5. Succession

Normal operation is continue-and-compact. Promote accepted knowledge, active tracks, and open decisions into the issue tracker or Git promptly so only disposable context is lost.

After compaction, the first action is issue-tracker context reload and active-track reconfirmation.

Succession is a single clean-spawn procedure. It is triggered by explicit user instruction. The master may propose succession around high context pressure, but automatic succession is not allowed.

Clean succession procedure:

1. Current master runs a promotion audit for accepted knowledge, active tracks, and open decisions.
2. Current master spawns a clean successor with an explicit workspace selector, kickoff file, root `{{WORKSPACE_ROOT}}`, model `{{MODEL_ID}}`, and machine-readable response when the host supports it.
3. Current master verifies successor liveness, leaves a one-line retirement note, and freezes.
4. Successor boots, declares Role State, measures the actual model field, captures the placement evidence three-set, closes or retires the predecessor pane when the host supports it, and appends a concise Lineage entry.

Placement evidence three-set:

1. host pane or worktree selector matches the intended workspace
2. process current working directory is under `{{WORKSPACE_ROOT}}`
3. session artifact or log path belongs to the expected workspace/session namespace

Accident recovery is not succession. Process death, host restart, stale UI handle, or accidental pane closure should first try same-session resume after proving no live duplicate process owns the session.

## 6. Records

Separate record ownership:

- Execution state: issue tracker
- Long-term planning, design, runbooks, decisions, and lineage: Git

Do not narrate the same fact in both systems. Put intermediate progress notes in the issue tracker. Put accepted decisions and durable procedures in Git.

Do not store credentials, secrets, raw environment values, or secret-dependent implementation detail in operations documents.

## 7. Boot, Hooks, And Observability

Hook wiring is a specification here. Apply concrete hook configuration through a human or dedicated security/operations session.

Recommended hook spec:

- SessionStart: load master operations context, role state, and issue-tracker memory
- SessionStart on compact: run `scripts/compaction-probe.sh`
- PreCompact: reload or export issue-tracker memory
- UserPromptSubmit: inject the current role-state line from `docs/runbooks/role-state.md`
- PreToolUse: warn when supervised dispatch is bypassed
- PostToolUse: collect non-sensitive audit markers when locally approved

Context-quality monitor namespace: `{{MONITOR_NS}}`

Lineage is append-only observability metadata. Do not use Lineage as the bootstrap source, priority source, or model-evaluation source.

## 8. Closed Principles Pointer

Closed decisions and structural facts live in `docs/decisions/closed-decisions-and-facts.md`. Reopen them only by explicit user instruction.

Before proposing infrastructure, architecture, or scope options, search the issue-tracker memory and closed-decisions ledger.
