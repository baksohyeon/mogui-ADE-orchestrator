# Orca Concepts For This Runtime

This runtime seats every agent inside Orca, and two real misplacement incidents came from misreading Orca's object model rather than from broken code. This page is the vocabulary those incidents were missing: what a project, a workspace, and a worktree are to Orca, where a master belongs and why, which selector forms are verified, and which UI labels that look wrong are actually normal.

## The Object Model

Orca tracks three layers.

**Project.** A folder you registered with Orca (Add a project). Three shapes all become projects: a single Git repository, a plain folder that contains several repositories (a typical workspace root), and an empty folder. The sidebar groups above projects are display grouping, not objects.

**Workspace.** A seat inside a project where terminals and agents live. There are two kinds, and the project's shape decides which you get:

- A *repository worktree* belongs to a Git repository project: one checked-out branch, created from the Create worktree dialog. A terminal opened there starts inside the checkout and git works immediately. This is where workers sit when they need to run git commands.
- A *folder workspace* belongs to a folder project: the folder itself is the seat, with no Git checkout of its own, created from the Create Folder Workspace dialog. A terminal opened there starts outside any checkout. An empty `worktreePath` is the expected shape for this kind; judge placement by `worktreeId`, which reads as `folder:<uuid>`.

The kind determines what a session can do on its first command, not merely where it appears in the sidebar.

**Terminal.** A live session inside a workspace. Agents, including masters, are terminals.

**Run.** A durable orchestration context bound to a terminal that holds its tasks, dispatches, and mailbox across individual sessions.

## Where The Master Sits, And Why

The master coordinates every repository in the workspace, so its seat is the workspace-level workspace:

- When the workspace root is a folder project containing the repositories, the master sits in that project's **folder workspace**. Its process cwd is the workspace root, which is what the harness and hooks bind to; execution state lives in the tracker inside the ops repository, reachable from that root.
- When the whole workspace is a single repository, the repository's primary worktree is the workspace level, and the master sits there.

Seating a master inside one repository's worktree in a multi-repository workspace is a misplacement even when cwd, hooks, and session files all bind correctly: the pane hangs under that one repository in the sidebar, the owner's mental model breaks, and the master occupies a seat shaped for a worker. A measured incident of exactly this shape (2026-08-03) is why this page exists.

Workers are the opposite: each worker gets its own repository worktree on its own branch, never the folder workspace and never a shared checkout.

## Selector Forms, Measured

Placement commands (`orca terminal create --worktree`, `master-succeed spawn --workspace-selector`) take a selector. Verified behavior, measured 2026-08-03 on a live host:

| Selector form | Verified behavior |
| --- | --- |
| `id:<repoId>::<path>` | Works end to end for repository worktrees. Copy the full `id` from `orca worktree list --json`; the repo id alone is not an address. |
| `id:folder:<uuid>` | Works end to end for folder workspaces: precheck listing, terminal create, and spawn placement match all pass. |
| `folder:<uuid>` (bare) | Split behavior: `orca terminal create --worktree` accepts it, `orca terminal list --worktree` rejects it with `selector_not_found`. Measured identically on two independent hosts, so it is a subcommand asymmetry, not a host quirk. Prefer the `id:` form when one string must work everywhere. |
| `path:/abs/dir` | Orca resolves it to `<repoId>::<path>`, so the spawn validator's comparison rejects it even when placement is correct. Prefer the `id:` forms. |

Two rules fall out:

1. **Measure the selector, never infer it.** Read it from `orca terminal show` on a pane already seated in the target workspace, or from `orca worktree list --json`. Omitting `--worktree` makes Orca infer the workspace from the shell's cwd, which is a measured misplacement cause.
2. **A placement match answers "did I get what I requested", not "did I request the right place".** A validator pass obtained by editing the request until it goes green is how the 2026-08-03 misplacement shipped. Compare the request itself against the placement your lineage records expect.

## Labels That Look Wrong But Are Not

**"Unavailable worktree"** in Agent Session History means the session ran in a workspace that is not a Git worktree. Folder workspaces have no Git checkout, so every master session seated in one carries this chip.

**Empty `worktreePath`** in `orca terminal list --json` output is the same fact from the CLI side: folder workspaces report a `worktreeId` of `folder:<uuid>` and an empty path. Judge placement by `worktreeId`, not by the path field or by the repository name shown in a pane's status line, which only reflects the shell's cwd.

**"Not a valid worktree folder"** (or similar) on the plain workspace root is also expected. The workspace root is intentionally a plain folder that groups member repositories as siblings. It is not a git repository and must never become a submodule parent: parent-pins-child-SHA coupling is the opposite of an overseeing master, and the version management is misery. Orca still registers that folder as a project and seats the master in its folder workspace; the warning names "this folder is not a git worktree," not "this install is broken."

## Workspace Descriptor (No Submodules)

The declarative inventory of those sibling repositories lives in the instance file `config/workspace-descriptor.json` (template example only: `config/workspace-descriptor.example.json`). Onboarding writes it from the measured repository list: each entry carries `name`, workspace-root-relative `path`, canonical `remote`, `role` (`product` or `ops`), `capabilities`, and `prohibited` actions. Workspace-level fields record `workspace_root_is_plain_folder: true` and `master_seat`. Consumers such as worker routing and `scripts/workspace-descriptor-check` read `prohibited` from that file (environment override → file → unconfigured) instead of a hardcoded product-path list. Submodules are not a supported shape.

## Beyond This Machine

Orca sessions are not bound to the desk they started on: the docs snapshot covers SSH remote worktrees (remote repo registration, relay grace periods, remote PTY leases), headless `orca serve` with pairing to a remote runtime, and a mobile companion app. Two consequences matter for this runtime. A frozen master session can be reopened from a phone, which is why retirement is only complete when process, pane, and tty are all measured gone and why boot includes a revival check. And a repository on a remote machine is observable only through its git remote and forge state, so claims about it need their own measurement.

## Where To Learn More

Agents should ground further Orca claims in the Orca docs snapshot (agent index first) linked from the README rather than improvising. Humans can start at the [Orca site](https://www.onorca.dev/); the onboarding flow in `master-ops/ONBOARDING.md` also answers Orca questions in place during installation.
