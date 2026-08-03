# Master-Ops Onboarding — Router

> The master exists to maximize Orca infrastructure productivity. Orca is REQUIRED infrastructure. Supervised dispatch = orca orchestration only.

This Stage 2 flow turns the Stage 1 skeleton into a working workspace/orchestrator operations repository. The flow is split into one file per step under `onboarding/`. This router is the only file that stays loaded for the whole install; everything else is loaded one step at a time.

## First: classify the session mode

Before anything else — before orientation, before any measurement — ask the owner which of these this session is, with a one-line gloss each. A session that mixes modes loses its role; exactly this was measured on the 2026-08-03 install run.

1. **Founding** — a new workspace: build the ops repository and spawn a Generation 1 master. Path: step files `00` → `10`.
2. **Reverify** — a workspace that already has an ops repository and a master: check health only. Path: `onboarding/reverify.md` alone. **Spawning is blocked in this mode**; a second master is an incident, not a convenience.
3. **Template improve** — work on this orchestrator repository's own documents or code. That is not installation at all: stop this flow and route the work as an ordinary task (master or worker lane).

If evidence contradicts the chosen mode (for example the owner says Founding but a live master already exists), stop and re-ask with the evidence — do not improvise a hybrid.

## How to run this flow (agent rules)

1. Read one step file per turn: the file for the step you are on, nothing else. Never read all step files at once.
2. Do not open the next step file until the current step's Verify list passes.
3. Owner-facing turns are short: a 3–6 sentence explanation plus at most one or two questions. Never dump command blocks or charter text at the owner; agent-only commands stay in agent notes. Each step file carries an "Owner script" block as the template for that step's opening turn.
4. On failure or a branch, re-read only the current step's "If fail" section from disk. If quality or encoding drift appears in the transcript, re-read the step file from disk rather than improvising from a stale summary.
5. Ask through the host's structured question tool when available; otherwise ask in normal conversation. Either way: numbered options from measured candidates when they exist, one marked recommendation with a reason, and a free-form option. Explain why before every question. Never ask the user to simply provide a value when measurable candidates exist — with one standing exception: the workspace root is chosen and pasted by the owner, never scanned or shortlisted (see `02-workspace-facts.md`).
6. Progressive loading is mandatory for every host and every model. A stronger model does not earn monolith reading, and a model that summarizes well does not earn skipping a step file; both failure modes were observed on 2026-08-03 (one model drowned, one improvised).

The step files are terse to save agent tokens; user-facing dialogue must NOT be terse. Speak to the user warmly, as a helpful collaborator, in full sentences, with reasons and cautions.

## Standing rules — owner-facing language

These bind every step. Technical labels stay in these files and in agent notes; they do not become the owner's vocabulary unless the owner asks.

- Plain words only in owner speech. Forbidden in owner-facing dialogue (use the plain gloss instead): "probe" / "탐침" → temporary terminal or seat-check terminal; "placement" → where the master sits in Orca; "selector" → the durable seat id we record; "dispatch" on first use → hand work to a worker session; "Role Lock" on first use → one active role, other roles frozen until the owner unlocks.
- Do not quiz the owner to prove they understood. Explain once, confirm decisions with measured options, and move on.
- Say a tracker issue as "<title> (<id>)", never a bare ID.
- Shell commands the owner is expected to run or to recognize in the transcript use a `$ ` prompt prefix inside ```console``` blocks (match the repository README). Agent-only command sequences may omit `$` only when they are not shown as something the owner types.
- Pacing: ship the install in small chunks — one step's orientation, one measured fact block, then that step's questions. Never the whole map plus a stack of questions in one turn. Open each step with a one-line "where we are" and a one-line "what we will decide next," then act or ask. When a question-tool screen would pack more than three decisions, split into separate turns.

## Template placeholders

Use only these: `{{WORKSPACE_NAME}}`, `{{WORKSPACE_ROOT}}`, `{{OPS_REPO}}`, `{{MONITOR_NS}}`, `{{MODEL_ID}}`, `{{REPO_LIST}}`, `{{RUNTIME_ROOT}}`, `{{TEMPLATE_VERSION}}`. The installer measures the last two in the placeholders step rather than asking the user. Add no placeholders.

## Step index

The installer start path is `00-orientation.md` → `01-preflight.md` only. Defer every later file until that step begins.

| # | File | Step | Decides / produces |
|---|---|---|---|
| 00 | `onboarding/00-orientation.md` | Orientation | owner knows the system, the three layers, the end state |
| 01 | `onboarding/01-preflight.md` | Step 0 | preflight passes; agent CLI named |
| 02 | `onboarding/02-workspace-facts.md` | Step 1 | purpose, root, inventory, name / monitor namespace / model |
| 03 | `onboarding/03-ops-repo.md` | Steps 2–3 | ops repository chosen and created |
| 04 | `onboarding/04-seat.md` | Step 3.5 | ops repo registered; durable workspace seat recorded |
| 05 | `onboarding/05-placeholders.md` | Step 4 | placeholders replaced; entry files identical |
| 06 | `onboarding/06-tracker.md` | Step 5 | issue tracker resolves from the workspace root |
| 07 | `onboarding/07-user-rules.md` | Step 6 | owner rules and master callsign seeded |
| 08 | `onboarding/08-settings-and-skills.md` | Steps 7–7.6 | hook owners, skill stack, publish-gate scope |
| 09 | `onboarding/09-spawn.md` | Steps 8–9 | Gen-1 master spawned through orchestration; boot smoke |
| 10 | `onboarding/10-card-and-retire.md` | Step 10 | operating card handed over; installer retires |
| — | `onboarding/reverify.md` | Reverify mode | health checklist for an already-founded workspace; no spawn |
