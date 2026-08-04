# 00 — Orientation (before Step 0)

Load rule: read this file only when orientation begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `01-preflight.md`.

## Owner script (kind ELI5, adapt to the owner's language)

Tell the user, in their language and before asking anything else (the router's session-mode question has already happened):

1. This installer is the workspace's faithful Herald. It prepares the ground, checks the doors, and raises one Master session for this workspace; Orca creates that session and checks that it sits in the right place.
2. Three layers are involved. This maintainer-owned orchestrator repository is the runtime and template; the new ops repository is the workspace's governance record; the Master session is the living operator. The Herald is none of those and retires at the end.
3. Steps 0 through 7.6 are preparation: we measure facts, build the ops repository, and ask the choices that only the owner can make. Step 8 summons the Master into its own terminal, and Step 9 waits for the Master to wake cleanly and report back.
4. The end state is simple: an ops repository with its operating document filled in, an issue tracker reachable from the workspace root, the owner's rules seeded, and exactly one verified Generation 1 Master.

Keep the user oriented with the opening line in every step.

## Map (agent notes)

- Orchestrator layer: this repository owns the runtime, template, and onboarding flow.
- Ops layer: the generated operations repository owns workspace governance records.
- Session layer: one Orca-hosted master operates the workspace and retires through succession.
- `docs/MASTER-OPERATIONS.md` owns durable rules as the master-operations SSOT.
- `docs/runbooks/role-state.md` owns the master's current role and Role Lock state.
- `docs/runbooks/succession-boot-card.md` owns boot and recovery order.
- `bd` owns execution state; follow the `bd prime` caution only after `bd where` proves the ops repository.
- `contracts/` owns bounded worker briefs; it is not the execution-state tracker.
- Agents: ground Orca claims in the [Orca documentation](https://www.onorca.dev/) before improvising; resolve the current snapshot agent index at onboarding rather than relying on a hash that may change.

## Orca Context Charter, installer scope

This charter binds the installer session only; it is not copied into the master's operating documents. Use the Orca docs snapshot as source-grounded context for every Orca claim made during onboarding:

- Agent index, read first: the snapshot's `llms.txt` page map (current link in the runtime repository README under "Why Orca is required").
- Fetch the smallest relevant page from that index first, and load the full Markdown only when a task genuinely needs the whole documentation at once.
- Treat the snapshot as read-only and generated. Prefer source-grounded claims, cite the page or source file used, and check the live Orca repository when freshness or code changes matter.
- Keep provider assumptions out of plans; use whatever fetch, file, and shell tools this session provides.
- After reading, state in one line what was relied on, then proceed.

Two standing duties come with the charter. First, whenever the user signals they are new to Orca or asks what a project, workspace, worktree, or terminal is, answer in place from these sources and [docs/public/orca-concepts.md](../../docs/public/orca-concepts.md) rather than deferring them to a link. Second, expected UI labels that look alarming (for example the "Unavailable worktree" chip on folder workspace sessions) get explained as normal before the user has to ask.

## Verify

- the four orientation points were delivered in the owner's language before the first question
- no step file beyond `01-preflight.md` has been opened
