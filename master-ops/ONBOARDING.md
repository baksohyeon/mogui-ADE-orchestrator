# Master-Ops Onboarding

> The master exists to maximize Orca infrastructure productivity. Orca is REQUIRED infrastructure. Supervised dispatch = orca orchestration only.

Use this Stage 2 guide to turn the Stage 1 skeleton into a working workspace/orchestrator operations repository. Ask through the host's structured question tool when available; otherwise ask in normal conversation. The prose fallback must match the structured path in quality: for every question, show measured candidate values as numbered options when available, mark one recommendation and explain why, and include a free-form option; never ask the user to simply provide a value when measurable candidates exist. Explain why before every question. This file is terse to save agent tokens; user-facing dialogue must NOT be terse — speak to the user warmly, in full sentences, with reasons and cautions.

## Orientation, Before Step 0

Tell the user, in their language and before asking anything:

1. This system runs one master session per workspace to coordinate its repositories; Orca spawns and placement-verifies it, and a dedicated ops repository keeps governance state.
2. Three layers are involved: this maintainer-owned orchestrator repository is the runtime and template; the new ops repository is the workspace's governance record; the master session is its operator. This installer session is none of them and retires after Step 8.
3. Steps 0 through 7.5 measure facts and build the ops repository; Step 8 spawns the master; Step 9 is the master's first-boot smoke in its own session.
4. The end state is an ops repository with a completed operations document, an issue tracker reachable from the workspace root, seeded user rules, and exactly one verified Generation 1 master.

Keep the user oriented with the opening line in every step. In owner-facing conversation, say a tracker issue as "<title> (<id>)", never a bare ID, and explain charter terms such as Role Lock in one plain clause on first use.

Use only these template placeholders: `{{WORKSPACE_NAME}}`, `{{WORKSPACE_ROOT}}`, `{{OPS_REPO}}`, `{{MONITOR_NS}}`, `{{MODEL_ID}}`, `{{REPO_LIST}}`, `{{RUNTIME_ROOT}}`, and `{{TEMPLATE_VERSION}}`. The installer measures the last two in Step 4 rather than asking the user.

## Map

- Orchestrator layer: this repository owns the runtime, template, and onboarding flow.
- Ops layer: the generated operations repository owns workspace governance records.
- Session layer: one Orca-hosted master operates the workspace and retires through succession.
- `docs/MASTER-OPERATIONS.md` owns durable rules as the master-operations SSOT.
- `docs/runbooks/role-state.md` owns the master's current role and Role Lock state.
- `docs/runbooks/succession-boot-card.md` owns boot and recovery order.
- `bd` owns execution state; follow the `bd prime` caution only after `bd where` proves the ops repository.
- `contracts/` owns bounded worker briefs; it is not the execution-state tracker.
- Agents: ground Orca claims in the [Orca documentation](https://www.onorca.dev/) before improvising; resolve the current snapshot agent index at onboarding rather than relying on a hash that may change.

## Orca Context Charter, Installer Scope

This charter binds the installer session only; it is not copied into the master's operating documents. Use the Orca docs snapshot as source-grounded context for every Orca claim made during onboarding:

- Agent index, read first: the snapshot's `llms.txt` page map (current link in the runtime repository README under "Why Orca is required").
- fetch the smallest relevant page from that index before loading the full Markdown, and load the full Markdown only when a task genuinely needs the whole documentation at once.
- Treat the snapshot as read-only and generated. Prefer source-grounded claims, cite the page or source file used, and check the live Orca repository when freshness or code changes matter.
- Keep provider assumptions out of plans; use whatever fetch, file, and shell tools this session provides.
- After reading, state in one line what was relied on, then proceed.

Two standing duties come with the charter. First, whenever the user signals they are new to Orca or asks what a project, workspace, worktree, or terminal is, answer in place from these sources and [docs/public/orca-concepts.md](../docs/public/orca-concepts.md) rather than deferring them to a link. Second, expected UI labels that look alarming (for example the "Unavailable worktree" chip on folder workspace sessions) get explained as normal before the user has to ask.

## Step 0. Pass The Required Preflight

**Position and action:** Step 0 starts after orientation, with no workspace state changed: run `bash scripts/onboarding-preflight.sh` from `{{RUNTIME_ROOT}}` and fix every FAIL before continuing.

**Why/caution:** Orca, an orchestration Run bound to this terminal, the Orca skills, Beads, Python, the named agent CLI, at least one worker runtime to dispatch to, Git, and the organization rules file are all required; do not offer a non-Orca fallback. A host that legitimately cannot satisfy one required check sets `PREFLIGHT_WAIVE=<check-label>`, which downgrades that FAIL to a printed and counted waiver; the summary then reads READY WITH WAIVERS and names them, because a required check that was waived was not satisfied. Never suggest skipping the preflight itself: that discards every other check with it. Orchestration is measured by capability rather than reachability. Two states measured on real hosts: a retained legacy coordinator answers reads and drops writes with `effectsApplied:false`, and an unbound coordinator fails the whole task family with `run_required`. A binding can also drop later without any signal, after which `check` returns `count:0`, so an empty mailbox and a missing binding look identical. If the preflight reports either state, bind a fresh Run with `orca orchestration run-create` and measure again; restarting the app does not clear the legacy one. Do not attribute a lost injection to binding state without a control: a lost task and a delivered task inside the same Run were measured on 2026-08-02, which rules binding out as that discriminator.

Ask whether the user is ready for local read-only checks and which agent CLI they expect to use, such as `claude`.

Run:

```console
cd "{{RUNTIME_ROOT}}"
ORCA_AGENT_CLI="<user-named agent CLI>" bash scripts/onboarding-preflight.sh
command -v "<user-named agent CLI>"
command -v git
```

Use `bash scripts/onboarding-preflight.sh --fix` only with approval; it may add or refresh the global Orca skills, while application installs remain manual.

Verify:

- the preflight exits zero, Orca status was measured, a non-legacy orchestration Run is bound to this terminal, required skills resolve, `bd` is present and resolves to the ops repo when one exists, and Python is present
- the named agent CLI is set and resolves on `PATH`; an unset selection is a FAIL, because it silently downgrades the agent-specific checks to INFO
- at least one of the worker runtimes this master dispatches to resolves on `PATH`; the others are reported as warnings, since routing every lane through one executor is a normal setup
- `gitleaks` was measured: present passes, absent warns without blocking, because publishing needs it (the redaction gate exits 2 without its engine) while running a master does not. Treat the warning as a real install item on any host that will publish
- `ctx` was measured: present with a reachable index passes, absent or unreachable warns without blocking, because the records practice cannot query cross-provider history without it while a master still runs. Ignore the warning only on a host that does no history work
- Git is present, and `gh` state was reported: a missing binary blocks, while unauthenticated or a missing `workflow` scope warns, because local-only work needs no forge credentials
- every waiver in the summary was intended, and `PREFLIGHT_WAIVE` entries that matched no check are corrected rather than left, since a misspelled waiver leaves the check enforced
- the organization rules file loads at least one rule and no rule is malformed; the preflight reports counts only and never the file's contents

## Step 1. Collect Workspace Facts

**Position and action:** Step 1 begins after prerequisites pass: collect and measure the workspace facts before routing any work.

**Why/caution:** The master operates above repositories and needs a confirmed absolute root and inventory.

Before asking, say these plain definitions in the user's language:

- “Workspace (root)” is simply the folder that groups the repositories this master will manage—nothing more special than that.
- “Workspace name” is a display label; by default, it is that folder's name.
- “Monitor namespace” is a short tag that keeps this workspace's session artifacts separate from other workspaces.
- “Default model identifier” is the model the master session is expected to run as; use the chosen agent CLI's table row below as the recommended candidate and measure the actual model at boot rather than guessing.

Master model criteria:

| Agent CLI | Master-session top-tier candidate |
| --- | --- |
| `claude` | `claude-fable-5` |
| `codex` | `gpt-5.6-sol` |
| `grok` | `grok-4.5` |
| `cursor-agent` | measured at boot; no fixed identifier yet |

The master session runs the top tier of its agent family. Worker and dispatch models use task-based tier selection instead: choose the lowest sufficient tier and state the exact model explicitly in every dispatch. For the `{{MODEL_ID}}` question, recommend the row for the chosen agent CLI; for `cursor-agent`, recommend measuring at boot and confirming the candidate with the owner.

Selection criteria for the workspace-root candidates, in plain language:

- If you are coordinating multiple product repositories, choose the folder that contains those repositories.
- If you are maintaining a single repository, choose that repository's parent folder.
- If this is an experiment or disposable work, choose a new temporary folder.
- When an existing grouping folder is present, it wins over a new or broader candidate.

Measure and offer numbered workspace-root candidates before asking: the parent directory of `{{RUNTIME_ROOT}}`, `{{RUNTIME_ROOT}}`'s grandparent when it groups repositories, and a user-named new folder. Make creating that new workspace folder and placing or cloning repositories into it a first-class option when no suitable folder exists; apply the criteria above, recommend the existing grouping candidate when present, and explain why. Then ask for the absolute workspace root, workspace name (default: confirmed root basename), monitor namespace, and default model identifier to measure at boot, with measured candidate values, a recommendation and reason, and a free-form option for each when available; explain why each is needed.

Run:

```console
test "${WORKSPACE_ROOT#/}" != "$WORKSPACE_ROOT" && test -d "$WORKSPACE_ROOT"
ls -la "$WORKSPACE_ROOT"
```

Read current files first, detect immediate child repositories, read the measured list back for confirmation or exclusions, and ask again rather than inventing uncertain values.

Verify:

- `{{WORKSPACE_ROOT}}` is absolute and exists
- `{{WORKSPACE_NAME}}` is explicit or is the confirmed root basename approved by the user
- `{{REPO_LIST}}` matches measured repositories after user confirmation

## Step 2. Choose The Ops Repository

**Position and action:** Step 2 begins with a confirmed workspace inventory: recommend and obtain approval for the ops repository.

**Why/caution:** Governance needs a visible ownership boundary that cannot be confused with product code.

Ask whether to create a new repository or reuse an existing operations repository, and whether local Git initialization is allowed for a new ops repository; this choice applies only to `{{OPS_REPO}}`, never to `{{WORKSPACE_ROOT}}`.

Inspect the confirmed names; propose two or three candidates with pros and cons; recommend `<workspace>-ops`; evaluate governance clarity, separation from product scope, and shell-title ambiguity; use a structured choice when available.

Verify:

- `{{OPS_REPO}}` is an approved absolute path or repository name
- the selection was evaluated against the confirmed inventory
- no product repository name was reused

## Step 3. Create The Ops Repository

**Position and action:** Step 3 begins with an approved name: create or deliberately reuse the ops repository before registering it in Orca.

**Why/caution:** Read and merge existing files; never overwrite operations records or initialize Git without approval.

Ask for confirmation to create or reuse `{{OPS_REPO}}` and separate confirmation before local Git initialization of that ops repository.

If new or empty, copy the Stage 1 skeleton from `{{RUNTIME_ROOT}}/master-ops/`, excluding `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md`; if existing, merge deliberately after reading it. Do not push unless explicitly asked.

Verify:

- the ops repository exists with `CLAUDE.md`, `AGENTS.md`, `docs/MASTER-OPERATIONS.md`, and the Stage 1 skeleton
- only the allowed remaining placeholders are present
- `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md` are absent from the generated repository

## Step 3.5. Register The Ops Repository And Seat The Master

**Position and action:** Step 3.5 begins after Step 3: register `{{WORKSPACE_ROOT}}` and the already-Git `{{OPS_REPO}}` with Orca, then seat the master terminal at the workspace level: the folder workspace of `{{WORKSPACE_ROOT}}` when the root is a folder containing repositories, or the repository's primary worktree when the workspace is a single repository.

**Why/caution:** The master coordinates every repository, so its seat is the workspace-level workspace, never one repository's worktree inside a multi-repository workspace. A master seated in a repository worktree binds correctly (cwd, hooks, session files) yet hangs under that one repository in the owner's sidebar and occupies a seat shaped for a worker; exactly this shipped as a measured misplacement on 2026-08-03. The folder route is verified from the CLI with the `id:folder:<uuid>` selector form: precheck listing, terminal create, and spawn placement match all pass (measured 2026-08-03). Bare `folder:<uuid>` is accepted by `terminal create` but rejected by `terminal list` (a measured subcommand asymmetry), and `path:` selectors are rejected by the placement comparison, so the durable record must use the `id:` prefixed form, which every consumer accepts. [docs/public/orca-concepts.md](../docs/public/orca-concepts.md) holds the object model.

Ask the user to add `{{WORKSPACE_ROOT}}` as an Orca project (the Add a project dialog's Browse folder accepts a folder with many repositories), create or open its folder workspace, start the master terminal there, and provide its runtime-issued terminal handle. Resolve `ORCA` exactly as Step 0's preflight does, then run:

```console
ORCA repo add --path "{{OPS_REPO}}" --json
ORCA terminal show --terminal <terminal handle> --json
```

Capture the returned selector only when the terminal metadata proves the workspace-level seat: a folder workspace reports `worktreeId` as `folder:<uuid>` with an empty `worktreePath`, and that emptiness is the expected shape, so judge by `worktreeId`. Before continuing, persist a durable placement result in an ops-repository file containing the selector in `id:` prefixed form, the terminal handle, `{{WORKSPACE_ROOT}}`, and the `terminal show` proof; do not rely on conversation state. Step 5 initializes the issue tracker independently and does not require a second placement copy; it may record a pointer to this result. Do not substitute a filesystem path for the measured selector, and do not infer the seat from a shell's cwd.

Verify:

- `orca repo add --path "{{OPS_REPO}}" --json` succeeds or confirms the ops repository is already registered (worker worktrees are created from this registration)
- `terminal show` measured the terminal metadata
- the selector points at the workspace-level seat, never an individual repository worktree inside a multi-repository workspace
- the durable placement result exists in `id:` prefixed selector form before founding spawn

## Step 4. Replace Template Placeholders

**Position and action:** Step 4 begins with the skeleton in place: replace every placeholder with confirmed or measured local facts.

**Why/caution:** Keep product-specific rules in product repositories and keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user accepts host-specific divergence.

Ask for each unresolved value and any coordination exclusions. Fill `{{RUNTIME_ROOT}}` from the current repository root and `{{TEMPLATE_VERSION}}` from its single-line `master-ops/TEMPLATE-VERSION`; do not ask for either. Pass `{{OPS_REPO}}/docs/MASTER-OPERATIONS.md` as `master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`. Add no placeholders.

Verify:

```console
! rg '\{\{[^}]+\}\}' "{{OPS_REPO}}"
cmp "{{OPS_REPO}}/CLAUDE.md" "{{OPS_REPO}}/AGENTS.md"
```

Also verify no source workspace's private names were copied accidentally.

## Step 5. Initialize The Issue Tracker

**Position and action:** Step 5 begins with a localized ops repository: initialize the chosen tracker there and make it resolve from `{{WORKSPACE_ROOT}}`.

**Why/caution:** Execution state belongs in the tracker, but upward resolution can silently select a database above the workspace or stop at the wrong Git root.

Explain that the tracker is working-state SSOT reloaded at boot and after compaction. Ask which tracker to use, whether to initialize it now, and which short issue prefix to use; propose a two- or three-character prefix beside the default and explain that IDs are spoken to the owner.

For Beads, run only after approval:

```console
cd "{{OPS_REPO}}" && bd init --prefix <approved prefix>
{ [ -e "{{WORKSPACE_ROOT}}/.beads" ] || [ -L "{{WORKSPACE_ROOT}}/.beads" ]; } \
    && echo "already exists, inspect before linking" \
    || ln -s "$(cd "{{OPS_REPO}}" && pwd)/.beads" "{{WORKSPACE_ROOT}}/.beads"
cd "{{WORKSPACE_ROOT}}" && bd where
```

Immediately after `bd init`, perform the byte/semantic comparison before continuing. If `CLAUDE.md` and `AGENTS.md` differ only at the byte level (whitespace or block order) while their semantic content is the same, normalize the shared blocks, write the same resulting common block to both files, and say once: `CLAUDE.md and AGENTS.md differed only byte-wise; re-unified automatically.` Do not ask the user in that case. If any substantive line or block is present in only one file, stop and ask the user whether to accept host-specific divergence before proceeding.

Ask before creating the link. If the prefix is wrong, `bd rename-prefix` rewrites database IDs and references but not Markdown. For another tracker, measure its resolution rules. Record active work in the tracker and seed only load-bearing memory pointers and rules.

Verify from `{{WORKSPACE_ROOT}}`, not inside the ops repository:

- `bd where` or its equivalent resolves to the ops repository
- this workspace database differs from every product repository database
- no tracker database exists above `{{WORKSPACE_ROOT}}` on the path to the filesystem root
- any tracker environment override printed from the agent's actual shell is empty or points inside the workspace

## Step 6. Seed Universal User Rules

**Position and action:** Step 6 begins with execution state reachable: store the user's durable, workspace-wide operating rules in the selected memory system.

**Why/caution:** Keep private details out of public documents and product conventions out of the master layer.

Ask for preferred address, primary response language, approval requirements before execution/dispatch/branch/commit/push/deploy, and standing prohibitions. Write short actionable rules without narrative duplication.

Verify that memory lookup returns the seeded rules and that the rules are concise and not duplicated in Git documents.

## Step 7. Explain The Settings Layer

**Position and action:** Step 7 begins with durable user rules seeded: identify the host and the owner of settings and sensitive configuration.

**Why/caution:** The template specifies hook behavior but does not ship hidden deny lists, credentials, secret paths, or environment-specific security implementation.

Ask which hosts run the master, who owns hooks/security-sensitive configuration, and whether dispatch warning, role-state injection, and compaction probe hooks should be enabled. Present the hook wiring spec from `docs/MASTER-OPERATIONS.md`; delegate auth, permission, secrets, credentials, and production-data work to a dedicated security/operations session.

Verify the hook spec is documented, no sensitive implementation was added, and its owner is explicit or unresolved.

## Step 7.5. Offer The Skill Layer

**Position and action:** Step 7.5 begins before the master is born: explain the optional stack in README, then ask which parts the user wants.

**Why/caution:** Skills load into the founding session; some installers, especially GSD, modify lifecycle hooks and require deliberate user choice.

Explain each component in one sentence before showing any command. Print approved install commands and stop; do not run them or edit `settings.json`, hooks, or plugin configuration.

These five questions decided what is in the stack, and they are worth repeating when a component is proposed later:

1. does it require an API key
2. does it force telemetry, or collect more than the job needs
3. does it add a management point
4. does it still work if the operation grows past one person
5. every tool claims to help with agent context. What else does this one actually resolve

A component that fails the first three is usually a subscription pretending to be a dependency. A component that passes them but answers nothing for the fifth is a preference, and should be labelled as one.

The stack this template was built against, with what each one is for and what it is deliberately not used for. Name the role before the install command, because a tool adopted without its boundary becomes the next thing to unwind:

| component | role here | not used for |
|---|---|---|
| Orca | execution substrate: worktrees, terminals, sessions, supervised dispatch | required infrastructure, not a swappable preference |
| tracker (Beads) | execution state that survives a session, as an issue graph | its memory is a short pointer cache toward Git, not the knowledge source of truth |
| `ctx` | trace archive: cross-provider session history, queryable when handoff, ledger, and Git do not answer | not part of routine boot context |
| `gitleaks` | matching engine for the publish gate | not the scope decision, which the wrapper keeps |
| methodology skills | how the master plans and verifies | without them the charter reads as advice rather than procedure |
| restraint skills | how much the master builds | pairs with the methodology layer rather than competing |
| review graph | impact radius and review context, locally parsed | optional; its value is token cost, not correctness |
| spec-driven framework | phase discipline from research through verification | installs lifecycle hooks, so it needs a deliberate yes |
| worker runtime plugin | lets the master delegate implementation from inside its own session | one wiring of the adapter layer, not a harness requirement |

Claude Code is the recommended host for the master, and a worker runtime such as Codex is a first-class executor rather than a fallback. Expect the preference to split hard between the two camps; the contracts hold either way, which is the point of an agent-neutral template.

One asymmetry to plan around rather than discover: an agent without an interactive query interface cannot run the steps of this document that ask the user a question. Onboarding is a conversation. Run it from an agent that can ask, or supply every answer in the dispatch contract up front and record that the questions were answered in advance rather than asked.

Install commands for the Claude Code case, printed and not run:

```console
$ /plugin marketplace add openai/codex-plugin-cc
$ /plugin install codex@openai-codex
$ /reload-plugins
$ /codex:setup
```

Say which of them are optional in name only. The template carries documents and scripts; it cannot carry the host layer that makes a master behave the way the documents describe, so a component listed here as recommended is often load-bearing. State the consequence of declining each one in a sentence, in the same breath as the offer, rather than leaving the user to discover it later:

- a methodology skill layer changes how the master plans and verifies; without it the master still runs, and reads the charter as advice rather than procedure
- a restraint skill layer keeps the master from over-building; without it, expect larger diffs and more speculative structure. It pairs with the methodology layer rather than competing with it: one decides how to approach work, the other decides how much to build
- a tracker skill layer is what makes execution state survive a session; without it, state lives only in the transcript
- a worker runtime is what makes delegation possible at all; without at least one, the master does every task itself

When the user declines a component the preflight treats as essential, ask once more. Not as a nag: restate the specific behaviour that changes, then ask whether to proceed without it. One re-ask, then take the answer as final.

The reason to ask twice is that the first no is usually answering a different question. A component list reads as preferences, so the first pass is "do I want this", while the question that matters is "am I accepting this behaviour". Restating the consequence is what turns one into the other.

Record the confirmed decline together with what is being accepted, in the user's own terms where possible. A declined component is a fact about the installation, and later behaviour that looks like a master defect is often a declined component instead.

Where the agent running onboarding has no interactive query interface, the re-ask cannot happen at all. In that case the dispatch contract carries the confirmed declines up front, and the record says they were confirmed in advance rather than asked.

Verify the explanation preceded commands, nothing was installed or configured by the agent, every essential decline was re-asked once with its consequence restated, and the user's choice—including no installation—is recorded with what it accepts.

## Step 7.6. State What The Publish Gates Do Not Cover

**Position and action:** Step 7.6 follows immediately, while the gates are fresh: tell the user what the redaction gates check and, more importantly, where they are silent.

**Why/caution:** A gate that is trusted beyond its scope is worse than no gate, because it converts an unchecked surface into a believed-clean one.

The gates read repository content. Name the surfaces they do not read, so nobody assumes coverage that does not exist:

- pull request titles, bodies, and review comments
- release notes and issue text
- anything typed into a forge web interface

None of those are in the repository, so no scanner in this template sees them. They are also where internal names most easily arrive, because they are written in prose rather than code. The habit that works is to grep your own outgoing text for organization identifiers before posting it, exactly as the scan does for files.

Tell the user that organization-specific patterns live in a file outside version control, that the gates fail closed without it, and that its format is one rule per line as `id|description|regex`. That file is what makes the gates able to catch a workspace name; the shipped rules only catch generic provider secrets.

Verify the user can state one surface the gates do not cover, and that the organization rules file exists or its absence is recorded as a known gap.

## Step 8. Spawn The Founding Master Through Orchestration

**Position and action:** Step 8 begins with the workspace prepared: create a Run and Task, spawn exactly one placement-verified Generation 1 master, attach its worker Dispatch, and wait for `worker_done`.

**Why/caution:** Supervised dispatch is Orca orchestration only; raw terminal polling and vendor-direct CLIs are non-compliant, and failures remain closed.

Ask for confirmation to spawn now or defer, reload the durable placement result from Step 3.5, re-run `terminal show`, and confirm that the selector, live handle, and workspace-level seat proof still match. Write a kickoff file containing Generation 1, this installer as founding origin, the boot sequence (rehydrate ops docs, declare Role State, measure model and placement), the initial queue, and the requirement to report the orchestration Task complete.

Before launching any worker, follow `docs/MASTER-OPERATIONS.md` §3: MEASURE the installed agent CLI's non-interactive approval flags from `--help` and never guess them.

Before attaching a Codex worker, run `{{RUNTIME_ROOT}}/scripts/codex-worker-pretrust <worktree-path>` as the pre-trust step.

Run this supervised path with the resolved `ORCA` executable:

```console
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
    --workspace-selector <durable placement selector from Step 3.5, id: prefixed> \
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

Require placement verification `MATCH` or `MATCH_REISSUED`; the latter must include `handle_reissued: true` and its adopted live handle. On any failure, do not retry with a filesystem path selector, do not boot the master in this installer, and do not create a second session. After settings changes, always spawn a fresh session.

Verify:

- a Run is bound, one Task exists, and its Dispatch is attached to the verified worker
- exactly one new master process/session exists
- placement is `MATCH` or valid `MATCH_REISSUED`
- kickoff content received by the master matches the kickoff file byte-for-byte
- the coordinator processes and acknowledges deliveries, answers questions through orchestration, and waits until that Task's `worker_done`

## Step 9. Run The First Master Boot Smoke

**Position and action:** Step 9 runs inside the new master session: declare its role, measure identity and placement, record lineage, and report completion.

**Why/caution:** Model identity is measured, unavailable, or unsupported—never guessed—and the installer does not perform this boot on the master's behalf.

Ask for the initial role or approval to start in Maintenance, plus permission for local read-only model and placement probes. Update `docs/runbooks/role-state.md` for Generation 1, declare Role State in conversation, measure configured and actual model when exposed, capture placement evidence, append Generation 1 to `docs/lineage/MASTER-LINEAGE.md`, then send `worker_done` exactly once for the active Dispatch.

Verify:

- Role State has one active role and Role Lock is enabled
- model measurement is reported as measured, unavailable, or unsupported
- placement evidence includes the host pane/worktree selector, process cwd under `{{WORKSPACE_ROOT}}`, and session artifact/log namespace
- no placeholders remain unless the user intentionally deferred them
- the founding Task and Dispatch complete through `worker_done`

## Step 10. Hand The Human A Card, Then Close The Installer

**Position and action:** Step 10 runs after the master reports a clean boot: verify the conversation actually happened, hand the user something portable, and ask them to close the installer terminal.

**Why/caution:** Everything installed here is worthless if the user does not know the four or five sentences that operate it, and an installer session left running is a second agent holding the same repository.

First verify the conversation, not just the artifacts. The steps above ask questions; a run that produced files without answers is a run that guessed. Check that the workspace facts were confirmed rather than inferred, that the component choices are recorded including declines, and that each essential decline was re-asked once. If any answer is missing, ask now rather than recording an assumption as a decision.

Then write the operating card. Print it, and tell the user to keep it wherever they keep notes, as plain text under a name they will find again, such as `llm.txt`. It is written to be pasted into any agent, so it must not depend on this session existing:

```text
# Operating this workspace

Master lives in: {{WORKSPACE_ROOT}}          Ops repository: {{OPS_REPO}}
State: the issue tracker in the ops repository. Long-term decisions: Git.

To start work, tell the master:
  "Role State?"                     it reports its active role and lock
  "Propose <goal>"                  it plans, then waits for your approval
  "Approved, execute"               it executes only what you approved

To delegate, tell the master:
  "Dispatch <task> to a worker"     it runs the gate, dispatches, and verifies
                                     the result before accepting it

Before publishing anything, the master runs:
  the test suite, the redaction scan, the redaction inventory
  A green scan covers repository content only. Pull request text,
  release notes, and issue prose are not scanned by anything.

When a session gets long:
  "Propose succession"              it audits, spawns a clean successor,
                                     and freezes itself

If the master behaves unlike the documents, check what was declined at
onboarding before assuming a defect. Declined at install:
  <declined components, or the word none>

New to Orca? Concepts, and labels that look alarming but are normal:
  {{RUNTIME_ROOT}}/docs/public/orca-concepts.md
```

Fill the last line from the recorded choices. If nothing was declined, write the word none rather than leaving it blank, because a blank line reads as unknown. The angle-bracket slots in the card are filled by hand at print time; do not introduce a new `{{...}}` placeholder for them, since Step 4 verifies that only the eight allowed placeholders remain anywhere in this document.

Finally, ask the user to close this installer terminal now that the master is running. Say why in one sentence: two agents holding one repository is how uncommitted work gets lost, and the installer has no further role. Do not close it yourself, and do not close the master's terminal.

If the user lingers with Orca questions instead of closing, answer them here under the Orca Context Charter (grounded in the docs snapshot and the concepts guide) before retiring; a user who leaves onboarding still confused about workspaces will misplace the next master by hand.

Verify:

- the card was printed in full, with placeholders replaced and the declined line filled or explicitly none
- the user was told where to keep it and that it works when pasted into any agent
- the user was asked to close the installer terminal, with the reason given
- the master's terminal was left running
