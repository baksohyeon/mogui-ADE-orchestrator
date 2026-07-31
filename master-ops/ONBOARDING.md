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
- `{{RUNTIME_ROOT}}` — the absolute path of this orchestrator repository clone; the onboarding agent fills this itself (Step 3), no user question needed

## Step 1. Collect Workspace Facts

(a) Why: the master layer operates above individual repositories, so it needs stable names, paths, and repo inventory before it can route work or verify placement.

(b) Ask the user:

- workspace name
- absolute workspace root
- list of repositories the master will coordinate
- preferred operations repository path
- monitor namespace
- default model identifier to measure at boot

(c) Agent action:

- read the current files before changing them
- normalize paths without inventing missing repositories
- leave uncertain values as placeholders and ask again

(d) Verification:

- `{{WORKSPACE_ROOT}}` is absolute
- `{{OPS_REPO}}` is either an absolute path or a repo name the user explicitly approved
- `{{REPO_LIST}}` matches user-provided repositories

## Step 2. Create The Ops Repository

(a) Why: product code and governance operations should not share ownership boundaries. The recommended name is `<workspace>-ops` because it keeps the orchestration layer separate from product repositories and makes dispatch, memory, and lineage records easy to locate.

(b) Ask the user:

- whether to create a new `<workspace>-ops` repository or use an existing operations repository
- whether local git initialization is allowed

(c) Agent action:

- if the repository does not exist and creation is approved, create it
- run Stage 1 from the harness source:
  `bash scripts/setup-master-ops.sh <ops-repo-path>`
- do not push unless the user explicitly asks

(d) Verification:

- ops repository exists
- `CLAUDE.md` and `AGENTS.md` exist in the ops repository
- `docs/MASTER-OPERATIONS.md` exists
- Stage 1 printed remaining placeholders and asked no questions

## Step 3. Replace Template Placeholders

(a) Why: the skeleton must become local enough to boot reliably, but still stay free of product-specific rules that belong inside product repositories.

(b) Ask the user:

- confirmation for each unresolved placeholder value
- whether any repository should be excluded from master coordination

(c) Agent action:

- replace the placeholders consistently across the ops repository
- fill `{{RUNTIME_ROOT}}` yourself with the absolute path of this orchestrator repository clone (your current repository root) — this one needs no user question
- keep `CLAUDE.md` and `AGENTS.md` byte-identical unless the user explicitly accepts host-specific divergence
- do not introduce additional `{{...}}` placeholders

(d) Verification:

- no `{{...}}` placeholders remain after the user has provided values
- `CLAUDE.md` and `AGENTS.md` are identical
- no source workspace's private names were copied accidentally

## Step 4. Initialize The Issue Tracker

(a) Why: execution state changes more often than documents. The issue tracker is the working-state SSOT; Git is for accepted plans, designs, decisions, and runbooks.

(b) Ask the user:

- which issue tracker to use, such as Beads (`bd`) or another local tracker
- whether the tracker database should be initialized now

(c) Agent action:

- initialize the selected tracker only in the ops repository
- record active work there, not in markdown TODO files
- seed only load-bearing memory pointers and rules

(d) Verification:

- tracker commands run from `{{OPS_REPO}}`
- the workspace tracker database is separate from every product repository tracker database
- `bd where` or the selected equivalent points to the ops repository, not a product repo

Warning: Beads and similar local trackers can keep per-repo databases. Do not reuse a product repository's database for workspace-level orchestration.

## Step 5. Seed Universal User Rules

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

## Step 6. Explain The Settings Layer

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

## Step 7. Founding Spawn

(a) Why: the master must be born as a clean, verifiably placed session — not as a continuation of the onboarding conversation. A founding spawn separates the installer (you) from the operator (the new master), so the master starts with a clean context and an auditable placement record.

(b) Ask the user:

- confirmation to spawn the Generation 1 master now, or to defer
- which terminal environment hosts the master (if the host exposes managed terminals, offer them; otherwise a plain new session works)

(c) Agent action:

- write a kickoff file containing: generation number 1, founding origin (this onboarding session), the boot sequence (rehydrate ops docs, declare Role State, measure model and placement), and the initial queue if any
- if the runtime's managed spawn is available, run:
  `{{RUNTIME_ROOT}}/scripts/master-succeed spawn --workspace-selector <workspace selector> --kickoff-file <kickoff file> --root {{WORKSPACE_ROOT}} --model {{MODEL_ID}} --title "Gen-1 founding boot" --json`
  and require the placement verification in the response to be MATCH before treating the spawn as valid
- if managed spawn is not available on this host, open a new agent session with cwd `{{WORKSPACE_ROOT}}` and paste the kickoff file content as the first message — then verify placement manually in Step 8
- never boot the master inside this onboarding session
- note: settings layers load at session start — after any settings deployment, always spawn a fresh session

(d) Verification:

- exactly one new master process/session exists (no double boot)
- managed spawn path: placement verification reported MATCH
- the kickoff content the master received matches the kickoff file byte-for-byte

## Step 8. Run The First Master Boot Smoke

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
