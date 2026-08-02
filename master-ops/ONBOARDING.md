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

## Step 0. Pass The Required Preflight

**Position and action:** Step 0 starts after orientation, with no workspace state changed: run `bash scripts/onboarding-preflight.sh` from `{{RUNTIME_ROOT}}` and fix every FAIL before continuing.

**Why/caution:** Orca, orchestration, the Orca skills, Beads, and Python are required; do not offer a non-Orca fallback.

Ask whether the user is ready for local read-only checks and which agent CLI they expect to use, such as `claude`.

Run:

```console
$ cd "{{RUNTIME_ROOT}}"
$ bash scripts/onboarding-preflight.sh
$ command -v "<user-named agent CLI>"
$ command -v git
```

Use `bash scripts/onboarding-preflight.sh --fix` only with approval; it may add or refresh the global Orca skills, while application installs remain manual.

Verify:

- the preflight exits zero, Orca status was measured, orchestration RPC is reachable, required skills are present, `bd` is present and resolves to the ops repo when one exists, and Python is present
- the named agent CLI is measured or explicitly unresolved
- Git is measured

## Step 1. Collect Workspace Facts

**Position and action:** Step 1 begins after prerequisites pass: collect and measure the workspace facts before routing any work.

**Why/caution:** The master operates above repositories and needs a confirmed absolute root and inventory.

Before asking, say these plain definitions in the user's language:

- “Workspace (root)” is simply the folder that groups the repositories this master will manage—nothing more special than that.
- “Workspace name” is a display label; by default, it is that folder's name.
- “Monitor namespace” is a short tag that keeps this workspace's session artifacts separate from other workspaces.
- “Default model identifier” is the model the master session is expected to run as; it is measured at boot, not guessed.

Measure and offer numbered workspace-root candidates before asking: the parent directory of `{{RUNTIME_ROOT}}`, `{{RUNTIME_ROOT}}`'s grandparent when it groups repositories, and a user-named new folder. Make creating that new workspace folder and placing or cloning repositories into it a first-class option when no suitable folder exists; recommend the existing candidate that groups the intended repositories when available, otherwise recommend creating the new folder, and explain why. Then ask for the absolute workspace root, workspace name (default: confirmed root basename), monitor namespace, and default model identifier to measure at boot, with measured candidate values, a recommendation and reason, and a free-form option for each when available; explain why each is needed.

Run:

```console
$ test "${WORKSPACE_ROOT#/}" != "$WORKSPACE_ROOT" && test -d "$WORKSPACE_ROOT"
$ ls -la "$WORKSPACE_ROOT"
```

Read current files first, detect immediate child repositories, read the measured list back for confirmation or exclusions, and ask again rather than inventing uncertain values.

Verify:

- `{{WORKSPACE_ROOT}}` is absolute and exists
- `{{WORKSPACE_NAME}}` is explicit or is the confirmed root basename approved by the user
- `{{REPO_LIST}}` matches measured repositories after user confirmation

## Step 2. Choose The Ops Repository

**Position and action:** Step 2 begins with a confirmed workspace inventory: recommend and obtain approval for the ops repository.

**Why/caution:** Governance needs a visible ownership boundary that cannot be confused with product code.

Ask whether to create a new repository or reuse an existing operations repository, and whether local Git initialization is allowed for a new one.

Inspect the confirmed names; propose two or three candidates with pros and cons; recommend `<workspace>-ops`; evaluate governance clarity, separation from product scope, and shell-title ambiguity; use a structured choice when available.

Verify:

- `{{OPS_REPO}}` is an approved absolute path or repository name
- the selection was evaluated against the confirmed inventory
- no product repository name was reused

## Step 2.5. Register The Orca Workspace

**Position and action:** Step 2.5 begins with the ops repository selected: open `{{WORKSPACE_ROOT}}` in Orca, start a terminal there, and measure its runtime-issued handle.

**Why/caution:** A filesystem path is not a valid substitute for an Orca folder selector; guessed paths can fail with `selector_not_found`.

Ask the user to provide that Orca terminal handle, then run:

```console
$ ORCA terminal show --terminal <terminal handle> --json
```

Resolve `ORCA` exactly as Step 0's preflight does. Capture the returned folder/worktree selector only if the metadata proves it belongs to `{{WORKSPACE_ROOT}}`; otherwise repeat with the correct Orca folder. Keep the selector for Step 8 without adding a template placeholder.

Verify:

- `terminal show` measured the terminal metadata
- the selector points to the confirmed workspace folder context
- the selector is available before founding spawn

## Step 3. Create The Ops Repository

**Position and action:** Step 3 begins with an approved name and measured Orca context: create or deliberately reuse the ops repository.

**Why/caution:** Read and merge existing files; never overwrite operations records or initialize Git without approval.

Ask for confirmation to create or reuse `{{OPS_REPO}}` and separate confirmation before local Git initialization.

If new or empty, copy the Stage 1 skeleton from `{{RUNTIME_ROOT}}/master-ops/`, excluding `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md`; if existing, merge deliberately after reading it. Do not push unless explicitly asked.

Verify:

- the ops repository exists with `CLAUDE.md`, `AGENTS.md`, `docs/MASTER-OPERATIONS.md`, and the Stage 1 skeleton
- only the allowed remaining placeholders are present
- `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md` are absent from the generated repository

## Step 4. Replace Template Placeholders

**Position and action:** Step 4 begins with the skeleton in place: replace every placeholder with confirmed or measured local facts.

**Why/caution:** Keep product-specific rules in product repositories and keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user accepts host-specific divergence.

Ask for each unresolved value and any coordination exclusions. Fill `{{RUNTIME_ROOT}}` from the current repository root and `{{TEMPLATE_VERSION}}` from its single-line `master-ops/TEMPLATE-VERSION`; do not ask for either. Pass `{{OPS_REPO}}/docs/MASTER-OPERATIONS.md` as `master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`. Add no placeholders.

Verify:

```console
$ ! rg '\{\{[^}]+\}\}' "{{OPS_REPO}}"
$ cmp "{{OPS_REPO}}/CLAUDE.md" "{{OPS_REPO}}/AGENTS.md"
```

Also verify no source workspace's private names were copied accidentally.

## Step 5. Initialize The Issue Tracker

**Position and action:** Step 5 begins with a localized ops repository: initialize the chosen tracker there and make it resolve from `{{WORKSPACE_ROOT}}`.

**Why/caution:** Execution state belongs in the tracker, but upward resolution can silently select a database above the workspace or stop at the wrong Git root.

Explain that the tracker is working-state SSOT reloaded at boot and after compaction. Ask which tracker to use, whether to initialize it now, and which short issue prefix to use; propose a two- or three-character prefix beside the default and explain that IDs are spoken to the owner.

For Beads, run only after approval:

```console
$ cd "{{OPS_REPO}}" && bd init --prefix <approved prefix>
$ { [ -e "{{WORKSPACE_ROOT}}/.beads" ] || [ -L "{{WORKSPACE_ROOT}}/.beads" ]; } \
    && echo "already exists, inspect before linking" \
    || ln -s "$(cd "{{OPS_REPO}}" && pwd)/.beads" "{{WORKSPACE_ROOT}}/.beads"
$ cd "{{WORKSPACE_ROOT}}" && bd where
```

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

Verify the explanation preceded commands, nothing was installed or configured by the agent, and the user's choice—including no installation—is recorded.

## Step 8. Spawn The Founding Master Through Orchestration

**Position and action:** Step 8 begins with the workspace prepared: create a Run and Task, spawn exactly one placement-verified Generation 1 master, attach its worker Dispatch, and wait for `worker_done`.

**Why/caution:** Supervised dispatch is Orca orchestration only; raw terminal polling and vendor-direct CLIs are non-compliant, and failures remain closed.

Ask for confirmation to spawn now or defer, and confirm the Step 2.5 Orca selector is still valid. Write a kickoff file containing Generation 1, this installer as founding origin, the boot sequence (rehydrate ops docs, declare Role State, measure model and placement), the initial queue, and the requirement to report the orchestration Task complete.

Run this supervised path with the resolved `ORCA` executable:

```console
$ ORCA orchestration run-create --objective "Found and verify the Generation 1 master" --json
$ ORCA orchestration task-create --spec "Run the byte-identical founding kickoff file and complete Step 9 boot smoke" --json
$ "{{RUNTIME_ROOT}}/scripts/master-succeed" spawn \
    --workspace-selector <measured folder selector> \
    --kickoff-file <kickoff file> \
    --root "{{WORKSPACE_ROOT}}" \
    --model "{{MODEL_ID}}" \
    --title "Gen-1 founding boot" \
    --json
$ ORCA terminal wait --terminal <verified live handle> --for tui-idle --timeout-ms 60000 --json
$ ORCA orchestration dispatch --task <task id> --to <verified live handle> --inject --json
$ ORCA orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json
```

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
