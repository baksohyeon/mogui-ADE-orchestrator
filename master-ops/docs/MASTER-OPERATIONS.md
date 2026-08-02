---
status: active
---

# MASTER-OPERATIONS

This is the master operations source of truth for the `{{WORKSPACE_NAME}}` workspace. It contains only currently active operating rules. Narrative logs, incident raw material, and product-specific specs live in their own files and are linked when needed.

Change rule: do not change this document without explicit user approval or an accepted decision record. When this document changes, check the related issue-tracker memory pointers and hook paths in the same change.

## 0. Document Map

Orca is REQUIRED infrastructure. Supervised dispatch = orca orchestration only. (charter rule since template v5)

This document is the workspace master-operations SSOT.

- Template version: `{{TEMPLATE_VERSION}}` (source: `{{RUNTIME_ROOT}}/master-ops/CHANGELOG.md`)
- Operations repository: `{{OPS_REPO}}`
- Workspace root: `{{WORKSPACE_ROOT}}`
- Workspace repositories: `{{REPO_LIST}}`
- Append-only evidence: `docs/decisions/closed-decisions-and-facts.md`, `docs/lineage/MASTER-LINEAGE.md`
- Field cards: `docs/runbooks/succession-boot-card.md`
- Role state SSOT: `docs/runbooks/role-state.md`
- Observability suite: `docs/observability/README.md` — attribution legend, integrity rules, and the retro / travelog genres
- Execution state SSOT: the issue tracker selected during onboarding, reachable from `{{WORKSPACE_ROOT}}`
- Long-term planning and design SSOT: Git documents

Issue-tracker memory should contain only load-bearing rules and pointers. Keep it curated; do not turn it into a second copy of this document.

## 1. Role Constitution

The master's responsibility is orchestration. Implementation, large research, repetitive editing, test repair, and broad multi-file changes should be delegated to workers when the workspace has worker capacity.

The master's own responsibilities are planning, repository understanding, architecture judgment, task decomposition, delegation, independent verification, acceptance, document ownership, and release coordination.

Exactly one role is active at a time. The role-state source of truth is `docs/runbooks/role-state.md`. A UserPromptSubmit hook may inject the current role and lock line into every user turn, but the file remains the authoritative state.

A coordinated repository's agent instruction file does not declare the master's role. Repositories in the workspace carry their own `AGENTS.md`, `CLAUDE.md`, or equivalent, and those files describe the role of an agent working inside that repository. To the master they are knowledge about a coordination target. Reading one and obeying its conventions is correct. Adopting its role as an additional identity is not, and it breaks the one-active-role rule the moment it happens.

Treat this as a standing pull rather than an occasional slip. The master must understand its repositories, understanding them means reading those files, and those files are written in the second person.

Configure the host to keep repository-level instruction files out of the master's automatic context, for example through whatever ignore or exclude list the host provides for auto-loaded instruction files. Record the mechanism your host uses in section 7. That configuration weakens the pull; this rule is what holds when the configuration is absent or wrong.

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

The master is agent-host neutral. Neutrality covers artifact formats and agent swappability only; it is never an excuse to avoid required infrastructure. For dispatch and terminal or session operations, prefer Orca's stable IDs (handles, worktrees, RPC) over raw OS utilities. The process-cwd and session-artifact checks in §5 are placement evidence, not dispatch mechanisms. (charter rule since template v5) Measure the configured model flag and the actual session model field at boot. Default master model identifier: `{{MODEL_ID}}`.

A boot measurement is a snapshot of one moment, not a property of the session. Re-measure after resume, after continue, after compaction, at succession audit, and at session close. A probe that samples recent turns answers what the model is now; it cannot see a change that happened earlier and then settled. For that, audit the whole transcript with `{{RUNTIME_ROOT}}/scripts/model-drift-audit`, which exits 0 for no transition, 1 for a transition or an expectation mismatch, and 2 when it cannot decide. Do not read 2 as a pass.

Recommended worker lanes:

- Heavy implementation: an implementation-capable worker with isolated workspace state and explicit acceptance criteria
- Review, diagnosis, small fixes, and chores: a fast reviewer or maintenance worker
- External-network research: a worker lane whose environment explicitly permits that access
- Local code work: a worker lane bound to the relevant repository checkout
- Sensitive areas such as auth, permissions, secrets, credentials, production data, and incident material: a dedicated security or operations session

The installation-specific worker tier mapping lives in `model-tier-policy.json`, which groups installed model identifiers into tiers; use the lowest sufficient tier for each worker lane. Measure what this host actually offers before filling it in: a template default lists models a machine may not have, and a model the file has never heard of is not blocked, it is capped as `unknown`.

### Worker Launch Approval Posture

Workers launched into isolated worktrees must start with the agent's non-interactive approval flag, or the measured Codex pre-trust posture below, so allowlist or trust prompts cannot block them mid-task. Pre-trust holds only when `codex-worker-pretrust` reported edits; its skip path (no TOML-capable interpreter) leaves the trust prompt in place and says so on stdout, so read its summary line before relying on it. At every dispatch, the master MEASURES the installed CLI's `--help` output and uses only flags present there; it never guesses flags from memory.

MEASURED examples from 2026-08-02:

- Grok: `--always-approve`.
- Claude Code: `--dangerously-skip-permissions`.
- Cursor Agent: `--force` (also exposed as `--yolo`) to force-allow commands unless explicitly denied, plus `--trust` to trust the current workspace without prompting.
- Codex: run `scripts/codex-worker-pretrust <worktree-path>` and retain the account-wide hooks trust posture; Codex uses this pre-trust path instead of a launch approval flag.

Three-vote review is the default for non-trivial merges or direct-push changes. Split review lenses:

- general correctness
- regression disproof
- contract and scope

Use the majority verdict, but a minority P1 `FIX_FIRST` finding must be addressed or explicitly rejected with evidence.

PR review-bot threads are always worker-handled without per-round owner instruction: dispatch a fix worker on arrival, the master verifies, the worker replies and resolves, and the master judges rejections only. (charter rule since template v5)

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

"$G" --ledger "$L" check --runtime <runtime> --model <model-id> --contract <contract-file> --agents <n> --est-chars <n> --completion-channel orchestration
<supervised dispatch command>
"$G" --ledger "$L" register --job-id <job-id> --probe-cmd "<command proving the job-id appears in an artifact>" --orchestration-task <task-id> --declared-model <model-id> --model-probe-cmd "<command printing the worker's actual model id>"
```

The gate enforces `model-tier-policy.json`. A version 2 policy gates on tier multiplied by fan-out rather than on identity, because the incident it exists for was a top tier spread across ten workers: each tier carries a cap on agents dispatched inside a window, an unlisted model falls in the `unknown` tier and is capped there rather than denied, and exceeding a cap requires `--tier-override "<reason>"`. The window counts accumulation, not concurrency, so ten sequential single-agent dispatches reach the same cap as one fan-out of ten; an override passes one request without refunding what the window already counted. Version 1 policies keep their identity-based behaviour unchanged. Model identifiers match casefolded, so a tier spelled in another case is the same tier. Each decision records the policy path, its `sha256`, and the tier that decided, because that path is caller-supplied; `dispatch-gate report` lists every policy a span was judged against and every tier it spent agents in, including `unknown`, and more than one policy row means the span was not judged against one policy.

The gate writes its verdict as JSON on stdout and human diagnostics on stderr. Do not merge them: `2>&1` piped into a JSON parser fails, and the failure reads like malformed output rather than like two streams. Use `2>/dev/null` for machine use, and read stderr separately when a person needs the reason.

`register` compares the model the dispatch declared with the model the worker actually ran. Declare the measurement per dispatch with `--model-probe-cmd`, because every runtime reports differently and this gate is agent-neutral; the command must read an artifact the agent itself produced, such as its session transcript, for which `{{RUNTIME_ROOT}}/scripts/model-identity-probe` is the reference implementation. Do not scrape a TUI status line: that measures what a renderer drew, and authenticating a model against it leaves a verification stamp with no verification behind it.

The verdict is graded. No declared model, or a probe that returns nothing, warns as `MODEL_UNVERIFIED` or `MODEL_PROBE_FAILED` and still registers, because a runtime with no way to report its model would otherwise be unable to dispatch at all and the check would simply be turned off. A measured model in a tier the policy watches more closely than the declared one denies with `MODEL_TIER_ESCALATION`. Running looser than declared warns as `MODEL_MISMATCH`. Every case records `model_declared`, `model_measured`, and `model_verified` in the ledger, so an unverified registration is distinguishable from a verified one instead of being assumed.

Before attaching a Codex worker, run `scripts/codex-worker-pretrust <worktree-path>` so startup never blocks on the trust prompt.

`register` without a prior successful `check` is invalid. Register only after the artifact exists, and before the final evidence report. Promote dispatch acceptance and verification results into the issue tracker.

The supervised dispatch command is vendor-neutral Orca orchestration: bind a Run, create the Task with `orca orchestration task-create`, attach the worker with `orca orchestration worker-start` (or `dispatch --inject`), then wait event-driven with `check --wait --types worker_done,escalation,question`. Raw terminal polling and vendor-direct CLIs bypass task and Dispatch provenance and `worker_done` authority and are non-compliant dispatch paths. Vendor plugins are allowed for non-dispatch uses such as second-opinion review. Record accidental work outside orchestration plainly as non-orchestrated; never relabel it orchestrated. (charter rule since template v5)

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

Orca command and orchestration references are grounded through `docs/orca-docs-grounding.md`; start there and never guess Orca flags.

Recommended hook spec:

- SessionStart: load master operations context, role state, and issue-tracker memory
- SessionStart on compact: run `scripts/compaction-probe.sh`
- PreCompact: reload or export issue-tracker memory
- UserPromptSubmit: inject the current role-state line from `docs/runbooks/role-state.md`
- PreToolUse: warn when supervised dispatch is bypassed
- PostToolUse: collect non-sensitive audit markers when locally approved
- SessionStart: warn when the issue tracker is not reachable from `{{WORKSPACE_ROOT}}`, or when an environment variable points its database outside the workspace

The last one covers a failure that is otherwise silent. The master runs at the
workspace root, and a tracker that resolves its database from the current
directory finds nothing there, or finds a product repository's database. Boot
continues either way. Measure the environment variable in the same shell the
agent's tool calls use; a login shell can define a different value, and reading
the wrong one turns the check into a pass.

Context-quality monitor namespace: `{{MONITOR_NS}}`

Lineage is append-only observability metadata. Do not use Lineage as the bootstrap source, priority source, or model-evaluation source.

Git history and the issue tracker record what happened but cannot record what shaped the master's behaviour, what it nearly did, or what it declined to do. Without that layer the owner's only observation channel is a post-incident report, which arrives only after something broke. The observability suite (`docs/observability/README.md`) fills it with voluntary standing records: the retro ledger answers why a decision took the shape it did, and the travelog answers what happened. Attribution tags, the falsifiability rule for judgment claims, freshness honesty after compaction, and the requirement to list what did not fire are specified once in that index and apply to every genre.

**Probe a tool with a subcommand it must have, not a flag you assume.**
Observed: a health check ran `orca --version`. That flag does not exist: on one host it printed the usage banner and exited 0, so the check passed while proving nothing, and a Linux user reported the same command launching the GUI application instead of answering.
Measure: run the probe and read its output, not just its exit code. A probe whose output does not contain the fact you wanted is not a probe. Prefer the documented subcommand, here `status --json`, which fails cleanly when the tool is unusable.

**Publish gates read repository content and nothing else.**
Observed: pull request bodies, review comments, release notes, and issue text are not in the repository, so no scanner in this template reads them. An audit of one day's outgoing text found none, which is the point: it took a separate grep to know.
Measure: before posting outgoing text, grep it for organization identifiers the way the scan greps files. A green publish gate says nothing about prose written into a forge.

### Tool Boundaries

Each tool has a role and an edge. The edge is the part that gets lost first.

- The execution substrate owns worktrees, terminals, sessions, and supervised dispatch. Placement checks read its state; they are not a dispatch mechanism.
- The tracker owns execution state across sessions. Its memory is a pointer cache toward Git, kept small and curated; it is not the knowledge source of truth, and it is not a second copy of this document.
- The history index is a trace archive. Query it when the handoff, the ledger, and Git together do not answer a question. It does not belong in routine boot context.
- The secret scanner is a matching engine. Scope, commit messages, and what the run covered stay with the wrapper, because those are decisions rather than matches.
- The review graph earns its place on token cost and impact radius, not on correctness. Nothing gates on it.
- Documentation stays plain Markdown in Git. No format lock means any tool can read it, including the next one.

## 8. Incident-Derived Rules

Every rule below was paid for. Each one names the observation that produced it and the measurement that settles it, because a rule without its evidence gets argued away by the next reader, and a rule without a measurement cannot be checked. Add to this section the same way: rule, what was observed, how to measure it. Do not add a rule you cannot measure.

**Reachability is not capability. A record is not an effect.**
Observed: an orchestration RPC answered reads normally while every write returned `effectsApplied: false`, because a coordinator retained across a state migration could not prove its original process identity. A dispatch was recorded as dispatched while the worker's heartbeat stayed absent and its terminal stayed empty.
Measure: `orca orchestration run-current --json`, with the CLI resolved the way Step 0's preflight resolves it, reports a bound non-legacy Run. Do not accept "the call returned" as evidence that anything landed.

**Silence is not a pass.**
Observed: three consecutive hook experiments produced no output, for three different reasons, and one of those silences was reported as "applied".
Measure: feed the instrument a case it must object to, and watch it object. Until you have seen it speak, its silence is unmeasured; after that, absence of output is a result. Prevention, which is to arrange that one such case exists before trusting any quiet run, follows from the measurement rather than replacing it.

**A declaration is not a measurement.**
Observed: the dispatch gate enforces the model identifier a caller declares at `check`, and `register` takes no model at all. The incident that motivated the tier policy was a worker default-inheriting a top-tier model, which a compliant declaration does not prevent.
Measure: `{{RUNTIME_ROOT}}/scripts/model-identity-probe` for what a session runs now, `{{RUNTIME_ROOT}}/scripts/model-drift-audit` for transitions across a whole transcript. Exit 2 means undecided; do not read it as a pass.

**Put the guard where the incident was.**
Observed: ten workers were fanned out at once and every one of them silently inherited the runtime's default top tier. That cost incident is why the tier policy exists. The policy encodes model identifiers, so it stops neither half of what happened: a single top-tier dispatch passes it, and `unknown_model: "deny"` blocks any model the file has not been hand-edited to name, including cheaper or stronger ones released later.
Measure: replay the incident's shape against the guard and read the verdict. Ten agents at a top tier must deny, and so must ten single-agent dispatches at that tier one after another; a guard that permits either is attached to the wrong variable however reasonable its condition reads. This gate already computes `n_agents × est_chars`, so a ceiling in those terms is measurable against both replays.

**Say whether a constraint came from availability or from policy.**
Observed: a worker reported that one model "is the only available model and matches the policy". The single option came from the CLI offering exactly one model, and the policy merely also allowed it; an earlier attempt failed because the requested identifier does not exist in this installation at all. Read quickly, that sentence blames the policy for a host fact.
Measure: read the output and try to answer, from it alone, which candidates the host lacks and which the policy forbids. If the two cannot be told apart without opening the policy file, the report does not distinguish them. A policy answers whether a model is permitted; it never answers which model fits, and it is not the reason a host has only one.

**Fix the pair, or the survivor lies.**
Observed: repeatedly, in one working day, code lost a claim its documentation still made, or documentation kept describing behaviour the code had dropped. Grepping a removed identifier finds the code and misses the prose, because prose names the same thing in different words.
Measure: after changing behaviour, grep the identifier and grep the words that describe it, then count the surviving mentions that still assert the old behaviour. That count must be zero. It is rarely zero on the first grep, because prose names the same thing in different words than code does.

**A green light must name its scope.**
Observed: a redaction scan reports success with organization-specific rules absent, covering generic patterns only, and the inventory silently drops rules that fail to compile. Both look identical to a clean result.
Measure: look at the green line and try to tell "checked everything and found nothing" from "checked almost nothing". If the output carries no scope, files scanned and rules loaded, the two are indistinguishable and the green is not a pass. A gate that can narrow its own coverage must print what it covered.

**A gate nobody can pass is a gate nobody runs.**
Observed: an onboarding preflight blocked a host the harness had been operating on all day, with two of three failures false. The pressure that creates is to skip the preflight, which discards every other check with it.
Measure: run the gate on a known-good host. If it cannot pass there, the check is wrong. Provide a waiver that is printed and counted rather than an escape that is silent.

**Do not read a blocker. Test it.**
Observed: deny lists and hook wiring that were documented as enforced turned out not to be, and two waiver behaviours that read correctly were only confirmed by breaking them.
Measure: mutate the check so it should fail, and watch the test fail. A check with no failing case has not been verified.

**A squash merge erases the base a stacked branch was built on.**
Observed: two stacked branches had to be rebased mid-flight after their base merged, because the squash commit shares no history with the branch's parent.
Measure: after the base merges, `git rebase --onto origin/main <old-base-sha>`, then confirm the branch is one commit and the expected file set before pushing.

**Reverting a file discards work that was never committed.**
Observed: `git checkout --` was used to undo a deliberate mutation during testing, and it also removed uncommitted work in the same file, which had to be reconstructed.
Measure: before reverting a path, run `git status --porcelain <path>` and read it. Every line there is work the revert will discard, so an empty result is the only state in which revert is safe. The same procedure was safe an hour earlier because that result was empty then; the safety belonged to the state, not to the procedure.

## 9. Closed Principles Pointer

Closed decisions and structural facts live in `docs/decisions/closed-decisions-and-facts.md`. Reopen them only by explicit user instruction.

Before proposing infrastructure, architecture, or scope options, search the issue-tracker memory and closed-decisions ledger.
