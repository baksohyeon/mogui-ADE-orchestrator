# 04 — Register The Ops Repository And Seat The Master (Step 3.5)

Load rule: read this file only when Step 3.5 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `05-placeholders.md`.

**Position and action:** Step 3.5 begins after Step 3: register `{{WORKSPACE_ROOT}}` and the already-Git `{{OPS_REPO}}` with Orca, then seat the master terminal at the workspace level: the folder workspace of `{{WORKSPACE_ROOT}}` when the root is a folder containing repositories, or the repository's primary worktree when the workspace is a single repository.

**Why/caution:** The master coordinates every repository, so its seat is the workspace-level workspace, never one repository's worktree inside a multi-repository workspace. A master seated in a repository worktree binds correctly (cwd, hooks, session files) yet hangs under that one repository in the owner's sidebar and occupies a seat shaped for a worker; exactly this shipped as a measured misplacement on 2026-08-03. The folder route is verified from the CLI with the `id:folder:<uuid>` selector form: precheck listing, terminal create, and spawn placement match all pass (measured 2026-08-03). Bare `folder:<uuid>` is accepted by `terminal create` but rejected by `terminal list` (a measured subcommand asymmetry), and `path:` selectors are rejected by the placement comparison, so the durable record must use the `id:` prefixed form, which every consumer accepts. [docs/public/orca-concepts.md](../../docs/public/orca-concepts.md) holds the object model.

## Owner script (3–6 sentences, adapt to the owner's language)

**Before any UI action, explain the whole short flow to the owner in plain language. Do not start mid-step.** Say, in substance:

1. We register the ops repository with Orca (so workers can get worktrees from it later).
2. You add `{{WORKSPACE_ROOT}}` as an Orca project if needed (Browse folder accepts a folder that holds many repositories), and open that folder workspace.
3. You open one **temporary plain terminal** there — not the master. We only need its seat id. It will feel like "open, we measure, then close."
4. You paste or send us that terminal's runtime handle so we can read where it sits.
5. We record the durable seat id in the ops repository.
6. **You close that temporary terminal** (or we close it if it is ours). Leaving it open means the spawn step would create a second terminal in the same seat. The real master is created only in the spawn step, and exactly one master may exist.

Only after the owner has heard that sequence, ask them to perform steps 2–4.

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
- the selector points at the workspace-level seat, never an individual repository worktree inside a multi-repository workspace
- the durable placement result exists in `id:` prefixed selector form before founding spawn
- the temporary seat-check terminal is closed, so the founding spawn will be the only terminal in that seat
