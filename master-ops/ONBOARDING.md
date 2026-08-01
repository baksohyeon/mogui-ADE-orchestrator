# Master-Ops Onboarding

This is the Stage 2 guide for turning the Stage 1 skeleton into a working workspace/orchestrator operations repository.

Stage 1 asks nothing. It lays down the skeleton and prints the remaining placeholders. Stage 2 is conversational: use a structured question tool when your host provides one; otherwise ask normal questions. At every step, explain why the information is needed before asking.

Use only these placeholders in the master-ops template:

- `{{WORKSPACE_NAME}}`
- `{{WORKSPACE_ROOT}}`
- `{{OPS_REPO}}`
- `{{MONITOR_NS}}`
- `{{MODEL_ID}}`
- `{{REPO_LIST}}`
- `{{RUNTIME_ROOT}}` — the absolute path of this orchestrator repository clone; the onboarding agent fills this itself (Step 4), no user question needed
- `{{TEMPLATE_VERSION}}` — the contents of `master-ops/TEMPLATE-VERSION`; the onboarding agent fills this itself (Step 4), no user question needed

## Step 0. Check Prerequisites

(a) Why: this onboarding flow depends on Orca ADE for terminal placement and founding spawn. Without Orca, the master cannot prove where it was created, so the flow must stop instead of offering a workaround.

(b) Ask the user:

- whether they are ready for a local prerequisite check
- which agent CLI they expect to use, such as `claude`

(c) Agent action:

- run `orca status`
- if `orca status` is unavailable or does not report a usable runtime, explain that this system assumes Orca ADE, guide the user to install and start Orca, and stop the onboarding flow until Orca is available
- do not offer a non-Orca fallback path
- verify the agent CLI, such as `claude`, is available when the user named one
- verify `git` is available

(d) Verification:

- Orca runtime status is measured, not guessed
- agent CLI availability is measured or marked unresolved
- `git` availability is measured

## Step 1. Collect Workspace Facts

(a) Why: the workspace is the integrated folder that contains the repositories the master will coordinate. The master layer operates above individual repositories, so it needs a measured workspace path and repo inventory before it can route work or verify placement.

(b) Ask the user:

- absolute workspace root
- workspace name, defaulting to the basename of the confirmed workspace root
- monitor namespace
- default model identifier to measure at boot

(c) Agent action:

- read the current files before changing them
- require an absolute path for the workspace root
- verify the path exists
- run `ls -la "$WORKSPACE_ROOT"` and detect immediate child repositories; do not invent missing repositories
- read back the discovered repository list to the user and ask for confirmation or exclusions
- leave uncertain values as placeholders and ask again

(d) Verification:

- `{{WORKSPACE_ROOT}}` is absolute and exists
- `{{WORKSPACE_NAME}}` is explicit or derived from the confirmed workspace root basename with user approval
- `{{REPO_LIST}}` matches measured repositories after user confirmation

## Step 2. Recommend The Ops Repository Name

(a) Why: product code and governance operations should not share ownership boundaries. The ops repository name must make the governance role clear without looking like another product repository in shell prompts, status lines, or terminal titles.

(b) Ask the user:

- whether they want a new ops repository or an existing operations repository
- whether local git initialization is allowed if a new repository is created

(c) Agent action:

- inspect the confirmed repository names and workspace structure from Step 1
- propose 2 or 3 candidate ops repository names with pros and cons
- use a structured question tool for the selection when the host provides one; otherwise ask in plain conversation
- make `<workspace>-ops` the default recommendation
- apply these criteria explicitly: the name reveals the governance role; the name does not mix with product scope; the name remains unambiguous when shown in a shell status line

(d) Verification:

- `{{OPS_REPO}}` is either an absolute path or a repo name the user explicitly approved
- the selected name was evaluated against the confirmed repo inventory
- the recommendation did not reuse a product repository name

## Step 2.5. Register The Orca Workspace

(a) Why: founding spawn needs an Orca folder-context selector for the workspace folder. A plain path is not enough when the folder has not been registered with Orca.

(b) Ask the user:

- open the confirmed `{{WORKSPACE_ROOT}}` folder in the Orca app
- start one terminal inside that Orca workspace
- provide the runtime-issued terminal handle for that terminal

(c) Agent action:

- run `orca terminal show --terminal <terminal handle> --json`
- read the returned metadata and capture the folder/worktree selector for `{{WORKSPACE_ROOT}}`
- if the terminal metadata does not prove it belongs to `{{WORKSPACE_ROOT}}`, ask the user to open the correct folder in Orca and repeat this step
- record the captured selector for Step 8; do not add a new `{{...}}` template placeholder for it

(d) Verification:

- terminal metadata was measured with `orca terminal show`
- the captured selector points to the confirmed workspace folder context
- the selector is available before founding spawn

Operational note: in production, a path selector for an unregistered folder failed with `selector_not_found`; fail-closed spawn handling prevented an invalid placement. Keep this note here so future onboarding agents use the measured folder selector from Orca instead of guessing from the filesystem path.

## Step 3. Create The Ops Repository

(a) Why: the selected ops repository is where workspace governance documents, lineage, memory pointers, and issue-tracker state will live.

(b) Ask the user:

- confirmation to create or reuse the selected `{{OPS_REPO}}`
- confirmation before any local git initialization

(c) Agent action:

- if the repository does not exist and creation is approved, create it
- if the repository is new or empty, copy the Stage 1 skeleton from this repository's `master-ops/` directory into it
- do not copy `TEMPLATE-VERSION`, `CHANGELOG.md`, or `ONBOARDING.md`. Those describe the template, not the workspace. The version the first two record lands in section 0 of the generated operations document during Step 4. `ONBOARDING.md` is this guide: copying it puts a list of placeholder names into the ops repository, and Step 4 then substitutes that list into values, which destroys the document while passing every check
- if the repository already has files, read them first and merge deliberately; do not overwrite existing operations records without user approval
- do not push unless the user explicitly asks

(d) Verification:

- ops repository exists
- `CLAUDE.md` and `AGENTS.md` exist in the ops repository
- `docs/MASTER-OPERATIONS.md` exists
- the Stage 1 skeleton is present and still contains only the allowed remaining placeholders
- `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md` are absent from the ops repository

## Step 4. Replace Template Placeholders

(a) Why: the skeleton must become local enough to boot reliably, but still stay free of product-specific rules that belong inside product repositories.

(b) Ask the user:

- confirmation for each unresolved placeholder value
- whether any repository should be excluded from master coordination

(c) Agent action:

- replace the placeholders consistently across the ops repository
- fill `{{RUNTIME_ROOT}}` yourself with the absolute path of this orchestrator repository clone (your current repository root) — this one needs no user question
- fill `{{TEMPLATE_VERSION}}` yourself with the single line in `{{RUNTIME_ROOT}}/master-ops/TEMPLATE-VERSION`, trimmed — no user question either. The path is in the orchestrator clone because Step 3 keeps that file out of the ops repository. It records which version of the template this copy came from, which is the only way a later upgrade can tell what changed
- pass the ops repository's operations doc as the bootstrap charter pointer (`master-bootstrap-live --charter-pointer "Operations SSOT: {{OPS_REPO}}/docs/MASTER-OPERATIONS.md"`), so the boot block names this workspace instead of a neutral placeholder
- keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user explicitly accepts host-specific divergence
- do not introduce additional `{{...}}` placeholders

(d) Verification:

- no `{{...}}` placeholders remain after the user has provided values
- `CLAUDE.md` and `AGENTS.md` are identical
- no source workspace's private names were copied accidentally

## Step 5. Initialize The Issue Tracker

(a) Why: execution state changes more often than documents. The issue tracker is the working-state SSOT; Git is for accepted plans, designs, decisions, and runbooks.

(b) Ask the user:

- which issue tracker to use, such as Beads (`bd`) or another local tracker
- whether the tracker database should be initialized now

(c) Agent action:

- initialize the selected tracker only in the ops repository
- reach the tracker from the workspace root, since that is where the master runs
- record active work there, not in markdown TODO files
- seed only load-bearing memory pointers and rules

Reaching the tracker from the workspace root is the step that gets missed. The master's working directory is
`{{WORKSPACE_ROOT}}`, or an orchestrator root the user approved instead. Either
way it is not the ops repository, and the ops repository sits below it.

Beads resolves from the current directory upward, and stops at a git repository
root. It never looks downward. Measured on 1.1.0:

| From | Result |
| --- | --- |
| two levels below a directory holding `.beads` | resolves to it |
| a workspace root whose ops repository holds `.beads` | finds nothing |
| a workspace root with `.beads` one level above it | resolves to the one above |
| below a git root that has no `.beads` | stops, finds nothing |

So the failure at the workspace root is an empty resolution, not a wrong one,
unless something above the workspace happens to hold a database. That second
case is the quiet one, because it answers.

Place a link at the workspace root pointing at the database inside the ops
repository, so the master resolves to the intended one from where it stands.
Expand `{{OPS_REPO}}` to an absolute path first; it may be a bare repository
name, and a relative link breaks as soon as the ops repository is not a direct
child of the workspace root.

```console
$ { [ -e "{{WORKSPACE_ROOT}}/.beads" ] || [ -L "{{WORKSPACE_ROOT}}/.beads" ]; } \
    && echo "already exists, inspect before linking" \
    || ln -s "$(cd "{{OPS_REPO}}" && pwd)/.beads" "{{WORKSPACE_ROOT}}/.beads"
```

The guard matters. `ln -s` against an existing directory succeeds silently and
creates the link inside it, so the resolution does not change and nothing says
so.

Adjust the name for the tracker in use, and confirm its own resolution rule
rather than assuming it matches this one. Ask the user before creating the link.

(d) Verification:

Run the checks from `{{WORKSPACE_ROOT}}`, not from the ops repository. Passing
from inside the ops repository proves nothing about where the master will look.

- `bd where`, or the selected equivalent, resolves to the ops repository
- the workspace tracker database is a different database from the one in any product repository
- no tracker database sits above `{{WORKSPACE_ROOT}}` on the path to the filesystem root, since an upward search would reach it first
- a global environment variable does not override the resolution. If your
  tracker reads one, print it from the same shell the agent's tool calls use.
  A value read in a different shell can be a different value, and the check
  passes while the real path is wrong

Warning: Beads and similar local trackers can keep per-repo databases. Do not
reuse a product repository's database for workspace-level orchestration.

The tracker itself does fail loudly. Beads returns `No active beads workspace
found.` and exits 1. What is quiet is the boot path, which does not read that
exit code, so boot continues on an empty tracker. Consider a session-start
check that prints a warning when the workspace root has no reachable tracker
database, or when an environment variable points outside the workspace.

## Step 6. Seed Universal User Rules

(a) Why: the master coordinates many repositories and sessions. Stable user preferences such as address form, language, approval discipline, and scope boundaries must survive compaction and handoff.

(b) Ask the user:

- preferred name or form of address
- primary response language
- approval rules before execution, dispatch, branch creation, commit, push, or deployment
- any standing "do not do" rules

(c) Agent action:

- write universal operating rules to the selected memory system
- keep private or sensitive details out of public documents
- keep product-specific conventions in each product repository, not the master layer

(d) Verification:

- memory lookup returns the seeded rules
- rules are short, actionable, and not duplicated as narrative in Git docs

## Step 7. Explain The Settings Layer

(a) Why: hooks and tool settings can enforce useful guarantees, but they also touch sensitive lanes. The master template should specify behavior without shipping hidden deny lists or environment-specific security implementation.

(b) Ask the user:

- which host or hosts will run the master
- who owns hook installation and security-sensitive configuration
- whether dispatch warning, role-state injection, and compaction probe hooks should be enabled

(c) Agent action:

- present the hook wiring spec from `docs/MASTER-OPERATIONS.md`
- leave implementation to a human or dedicated security/operations session
- keep auth, permission, secret, production data, and credentials work in a separate sensitive lane

(d) Verification:

- hook spec is documented
- no hook implementation, deny list, credentials, or secret paths were added by the onboarding agent
- sensitive-lane owner is explicit or marked unresolved

## Step 7.5. Offer The Skill Layer

(a) Why: the master is born in the next step and inherits whatever skill layer is present at that moment. The runtime works without any of it, so this is an offer rather than a requirement. It comes before the spawn so the founding master starts under the stack the user chose instead of acquiring it later.

(b) Ask the user:

- whether to install the recommended skill stack, and which parts
- explain each one first, in a sentence, so the choice is informed rather than a yes to a list of names

The stack and what each part does in the harness is in the repository README under "The skill layer it runs under." Do not paste install commands without the explanation.

(c) Agent action:

- print the install commands and stop there
- do not run them, and do not edit the user's `settings.json`, hooks, or plugin configuration
- GSD in particular wires hooks across most lifecycle events through its own installer, which is a change the user should make deliberately

(d) Verification:

- the user was told what each tool does before being shown a command
- the agent installed nothing and modified no host configuration
- the user's answer is recorded, including a decision to install nothing

## Step 8. Founding Spawn

(a) Why: the master must be born as a clean, verifiably placed session — not as a continuation of the onboarding conversation. A founding spawn separates the installer from the operator, so the master starts with a clean context and an auditable placement record.

(b) Ask the user:

- confirmation to spawn the Generation 1 master now, or to defer
- confirmation that the Step 2.5 Orca folder selector is still valid

(c) Agent action:

- write a kickoff file containing: generation number 1, founding origin (this onboarding session), the boot sequence (rehydrate ops docs, declare Role State, measure model and placement), and the initial queue if any
- run the Orca-managed spawn with the folder selector captured in Step 2.5:
  `{{RUNTIME_ROOT}}/scripts/master-succeed spawn --workspace-selector <folder selector from Step 2.5> --kickoff-file <kickoff file> --root {{WORKSPACE_ROOT}} --model {{MODEL_ID}} --title "Gen-1 founding boot" --json`
- require the placement verification in the response to be MATCH before treating the spawn as valid
- if the command fails, keep the failure closed: do not retry with a filesystem path selector and do not boot the master inside this onboarding session
- note: settings layers load at session start — after any settings deployment, always spawn a fresh session

(d) Verification:

- exactly one new master process/session exists (no double boot)
- managed spawn path: placement verification reported MATCH
- the kickoff content the master received matches the kickoff file byte-for-byte

## Step 9. Run The First Master Boot Smoke

(a) Why: the first boot proves the master can declare role state, measure its actual model, and prove it is placed in the intended workspace before it coordinates work.

(b) Ask the user:

- initial role, or approval to start in Maintenance until a concrete track is selected
- permission to run local read-only probes for model and placement evidence

(c) Agent action:

- update `docs/runbooks/role-state.md` for Generation 1
- declare the Role State in the conversation
- measure configured model and actual session model when the host exposes that data
- capture the placement evidence three-set
- append Generation 1 to `docs/lineage/MASTER-LINEAGE.md`

(d) Verification:

- Role State has one active role and Role Lock is enabled
- model measurement is reported as measured, unavailable, or unsupported; never guessed
- placement evidence three-set is present:
  host pane or worktree selector, process cwd under `{{WORKSPACE_ROOT}}`, and session artifact or log namespace
- the first boot leaves no unresolved placeholders unless the user intentionally deferred them
