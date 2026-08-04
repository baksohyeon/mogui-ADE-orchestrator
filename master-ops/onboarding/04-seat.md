# 04 — Register The Ops Repository And Seat The Master (Step 3.5)

Load rule: read this file only when Step 3.5 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `05-placeholders.md`.

**Position and action:** Step 3.5 begins after Step 3: register `{{WORKSPACE_ROOT}}` and the already-Git `{{OPS_REPO}}` with Orca, then seat the master terminal at the workspace level: the folder workspace of `{{WORKSPACE_ROOT}}`. In a single-repository workspace, `{{WORKSPACE_ROOT}}` is the selected parent folder for that repository, not the repository's product worktree.

**Why/caution:** The master coordinates every repository, so its seat is the workspace-level workspace, never one repository's worktree inside a multi-repository workspace. A master seated in a repository worktree binds correctly (cwd, hooks, session files) yet hangs under that one repository in the owner's sidebar and occupies a seat shaped for a worker; exactly this shipped as a measured misplacement on 2026-08-03. The folder route is verified from the CLI with the `id:folder:<uuid>` selector form: precheck listing, terminal create, and spawn placement match all pass (measured 2026-08-03). Bare `folder:<uuid>` is accepted by `terminal create` but rejected by `terminal list` (a measured subcommand asymmetry), and `path:` selectors are rejected by the placement comparison, so the durable record must use the `id:` prefixed form, which every consumer accepts. [docs/public/orca-concepts.md](../../docs/public/orca-concepts.md) holds the object model.

## Owner script (kind ELI5, adapt to the owner's language)

**Before any UI action, explain the whole flow to the owner in plain language. Do not start mid-step.** The plain framing is: before the Master is raised, the Herald must find the correct chair. Say, in substance:

1. We register the ops repository with Orca (so workers can get worktrees from it later).
2. Add `{{WORKSPACE_ROOT}}` as an Orca project if needed and open that folder workspace. For a single-repository workspace, this still means the selected parent folder for that repository, not the repository's product worktree.
3. You open one **temporary plain terminal** there — not the Master. We only need its seat id. It will feel like "open, we measure, then close."
4. You paste or send us that terminal's handle so we can read where it sits.
5. We record the durable seat id in the ops repository.
6. **You close that temporary terminal** (or we close it if it is ours). Leaving it open means the Master's chair is still occupied, so the spawn step must stop until the chair is empty. The real Master is created only in the spawn step, and exactly one Master may exist.

Only after the owner has heard that sequence, ask them to perform steps 2–4.

## Worker Placement

The master's seat is workspace-level because the master coordinates every repository and must not hang under one of them. A worker that runs git needs a repository worktree, because that is where a checkout exists. Placing a worker at a folder seat is allowed only when its first command changes directory into a checkout; otherwise the worker starts outside every repository and fails on its first git call. After delivery, read the terminal and confirm the agent is at its prompt in the intended directory, because a created terminal is not a working one.

## Run

Resolve `ORCA` exactly as Step 0's preflight does, then run:

```console
$ ORCA repo add --path "{{OPS_REPO}}" --json
$ ORCA terminal show --terminal <terminal handle> --json
```

Capture the returned selector only when the terminal metadata proves the workspace-level seat: a folder workspace reports `worktreeId` as `folder:<uuid>` with an empty `worktreePath`, and that emptiness is the expected shape, so judge by `worktreeId`. Before continuing, persist a durable placement result in an ops-repository file containing the selector in `id:` prefixed form, `{{WORKSPACE_ROOT}}`, and the `terminal show` proof; do not rely on conversation state, and do not treat the temporary terminal's handle as durable, because handles are scoped to the app runtime and die with restarts. The durable identity is the selector. After persisting, ask the user to close the temporary seat-check terminal (or close it yourself if it is yours). The tracker step initializes the issue tracker independently and does not require a second placement copy; it may record a pointer to this result. Do not substitute a filesystem path for the measured selector, and do not infer the seat from a shell's cwd.

## Verify

- the full open-measure-close sequence was explained before any temporary terminal was requested
- `orca repo add --path "{{OPS_REPO}}" --json` succeeds or confirms the ops repository is already registered (worker worktrees are created from this registration)
- `terminal show` measured the terminal metadata
- the selector points at the workspace-level seat, never an individual repository product worktree
- the durable placement result exists in `id:` prefixed selector form before founding spawn
- the temporary seat-check terminal is closed, so the founding spawn will be the only terminal in that seat

## If fail

- `terminal list` rejects the captured selector: the record is probably in the bare `folder:<uuid>` form — re-capture and persist the `id:` prefixed form, which every consumer accepts (the subcommand asymmetry above is measured behavior, not an error to work around).
- The placement comparison rejects the selector: it is probably a `path:` form or a filesystem path — never substitute a path for the measured selector; re-run `terminal show` and capture `worktreeId`.
- The terminal metadata shows a repository worktree instead of the workspace-level seat: the owner opened the temporary terminal in the wrong place; explain, ask them to open it in the folder workspace, and measure again.
