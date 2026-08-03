# Getting Started

From a machine that has never opened Orca to watching one master hand a small job to a worker and accept the result. This page is for that first run only. It stops there on purpose.

If you already run a master and only need a script flag, go to [Reference](reference.md). If you need Orca object vocabulary after you hit a confusing label, go to [Orca Concepts](orca-concepts.md). The agent-executed install steps live in [`master-ops/ONBOARDING.md`](../../master-ops/ONBOARDING.md); this page is the human path that leads into that flow.

## What this is

You get one long-lived coordinating session per workspace, called the master while it holds the role. That session plans work, hands narrow jobs to worker sessions, checks the evidence those workers return, and can hand its own role to a successor when context runs out. Orca is the execution substrate: real terminals that keep a handle after you close a tab, worktree-scoped placement so "where did that run" has an answer, and supervised dispatch so completion is a mailbox message rather than a screen scrape. This repository is the runtime and the template for a separate operations repository that holds the rules, lineage, and workspace facts for your setup. The problem it solves is the one you hit when several coding-agent sessions need to share a multi-repository workspace without losing role state, routing work into the wrong checkout, or treating a worker's "done" as proof.

"Context engineering" in the abstract is not enough here. The durable facts live outside chat: an operations repository in git, an issue tracker for execution state, and contracts that name what a worker may touch. The master session is the operator of that system, not a longer chat with better prompts.

## Prerequisites, measured

Classifications below follow `scripts/onboarding-preflight.sh` as read on this branch: a FAIL prints `FAIL`, counts toward exit 1 with `BLOCKED`, and refuses founding until fixed or waived; a WARN prints `WARN`, does not exit 1 by itself, and is repeated when the label is essential. The table lists installable tools and files you can check before opening the installer session. It does not replace the preflight: the script also measures session state (a non-legacy orchestration Run bound to the current terminal, a writable dispatch-ledger path, and `ORCA_AGENT_CLI` once onboarding names it) that only exists in the right seat.

| Need | How you check | Preflight when absent |
| --- | --- | --- |
| Orca app and a reachable runtime | Install (next section), open the app, then `orca status`. Expect `appRunning: true` and `runtimeState: ready` (or `orca status --json` with `"ok": true`). | FAIL on `orca` when the CLI is missing, unsupported, or status is not ok. Without a ready runtime, founding has nowhere to put the master. |
| `orca` on `PATH` | `command -v orca` then `orca status`. Supported basenames: `orca`, `orca-dev`, `orca-ide`. | Same `orca` FAIL as above. App may be open while spawn and retire scripts still cannot call the host. Register the shell command in Orca settings (below). |
| Master agent CLI | `command -v` for the CLI you will run as master (`claude`, or another host you actually use). | FAIL on `agent-cli` when `ORCA_AGENT_CLI` is unset or not on `PATH`. Onboarding sets the variable; install the binary before then. |
| At least one worker runtime | `command -v codex` and/or `command -v cursor-agent`. | FAIL on `worker-runtime` when neither is on `PATH`. One present is enough; a missing second runtime is WARN only. |
| `git` | `git --version` | FAIL: `git is required; this repository is managed through pull requests`. |
| `gh` (GitHub CLI) | `gh --version` | FAIL: `gh is required; this repository is managed through pull requests`. Login is separate: when `gh` is present but not authenticated, preflight WARNs on `gh-auth` (and on missing `workflow` scope) rather than blocking. |
| `python3` on `PATH` | `python3 --version` | FAIL: entry points are `python3` scripts. No version floor; tools that need a newer interpreter locate one themselves or skip loudly ([Reference](reference.md)). |
| `bd` (Beads) | `command -v bd` | FAIL: `binary missing; install Beads before onboarding`. Later, `bd where` must resolve inside an ops repository; a marker without a working `bd where` is also FAIL. |
| Orca skills `orca-cli` and `orchestration` | Confirm both skill directories resolve under your agent skills roots, or that a skills package manager lists them globally. | FAIL on `skills` when neither the on-disk artifacts nor a successful global list shows both names. |
| Organization redaction rules file | Default path `~/.config/redaction-extra.txt`, or the path in `REDACTION_EXTRA_PATTERNS`. File must yield at least one compilable rule (three pipe-separated fields: id, description, regex). | FAIL on `redaction-extra`: two of the three publish gates refuse without a usable rules file. |

WARN (does not exit 1 alone; still called out when labelled essential):

| Tool | Preflight behavior | Check |
| --- | --- | --- |
| [`gitleaks`](https://gitleaks.io) | WARN if missing; redaction scan exits 2 without it when publishing. | `gitleaks version` (on macOS, `brew install gitleaks`) |
| [`ctx`](https://ctx.rs) | WARN if missing or if `ctx status` fails; records practice needs the index. | `ctx status` |
| Methodology / restraint skill packs (`superpowers`, `ponytail`) | WARN on `skill-stack` per missing pack; master runs without them but with different behaviour. | Skill directory under a known skills root, or the agent plugin manifest |
| `gh` authentication | WARN on `gh-auth` when `gh` is present but not logged in, or logged in without `workflow` scope. | `gh auth status`; `gh auth login` or `gh auth refresh -h github.com -s workflow` as the message directs |

From the clone of this repository, one command measures the full set including session state:

```console
$ bash scripts/onboarding-preflight.sh
```

Any FAIL exits 1 with `BLOCKED`. WARNs do not exit 1 by themselves and, when essential, are repeated in the closing summary. `PREFLIGHT_WAIVE` can downgrade a named check from FAIL to a printed waiver; the summary says that out loud rather than pretending the tool is present. Onboarding runs this as Step 0, so you do not have to keep the table in your head.

Verified on the authoring host against the preflight script and live checks: `orca status` / `orca status --json`, `bash scripts/onboarding-preflight.sh`, `git --version`, `gh --version`, `python3 --version`, and the agent CLIs that resolve on `PATH`. Platform notes below that this host cannot open (Linux package names, Windows installer UI) are marked as such.

## Installing and opening Orca

Orca is required infrastructure for this system. Without it the harness degrades to screen-polling and unsupervised agents; a real incident of that shape is why Step 0 refuses to proceed without a reachable runtime.

### Install

macOS (verified: Homebrew cask `stablyai/orca/orca` resolves and installs the app plus a bundled CLI binary):

```console
$ brew install --cask stablyai/orca/orca
```

Linux and Windows: use the [download page](https://www.onorca.dev/download). Maintainer-reported routes also include an AppImage or `.deb` from releases, and on Arch `yay -S stably-orca-bin`. Homebrew `--cask` is macOS-only. On Linux the binary name may be `orca-ide` rather than `orca`, to avoid colliding with the GNOME screen reader of the same name. **Not re-verified on this host:** the exact Linux package contents and the Windows `orca-windows-setup.exe` first-run screens. Treat those lines as maintainer-reported until someone measures them again.

### First launch and the shell command

Open the Orca application. On first launch you will see an empty or nearly empty project sidebar; that is normal. You do not need a project yet.

Register the shell command before anything else that depends on `orca` from a terminal:

1. Open **Settings → Orca CLI**.
2. Turn on **Shell command**.

What that does, measured after it works: the app writes a launcher for the CLI it already bundles. On macOS that is typically a symlink under a directory already on `PATH` (the app may ask for admin). After registration:

```console
$ orca status
```

You want a ready runtime. If the app is closed, `orca open` launches it and waits until the runtime is reachable (verified: `orca open --help` documents that behavior).

**UI label caveat:** the Settings path and the "Shell command" label come from the existing install docs and from hosts that already registered the CLI. A first-launch screen that renames those controls is the part a maintainer should confirm against the current Orca build; the measurable success condition is still `command -v orca` plus `orca status` reporting a ready runtime.

### Words you need at this moment

Orca tracks three layers. You only need the first one until you add a folder:

- **Project.** A folder you registered with Orca. A single git repository, a plain folder that contains several repositories, or even an empty folder can all become projects.
- **Workspace (seat).** Where terminals and agents live inside a project. A *folder workspace* is the seat for a plain folder project (the folder itself, with no git checkout of its own). A *worktree* is the seat for a git repository project (one checked-out branch).
- **Terminal.** A live session inside a workspace. Agents, including masters, are terminals.

The master of a multi-repository workspace sits in the folder workspace of the workspace root, not inside one repository's worktree. Workers sit in repository worktrees. Full vocabulary and the misplacement incidents that paid for it: [Orca Concepts](orca-concepts.md).

## Getting the repository in front of the agent

You need two different things in place, and they are easy to confuse.

1. **A folder workspace root** is the directory that groups the repositories you care about. It is often not itself a git repository. The master will live here.
2. **A checkout of this orchestrator repository** is a git clone. Onboarding copies a template out of it into a new operations repository. The master does not stay forever inside this clone; the clone is the installer and the runtime source.

### Clone this repository

```console
$ git clone https://github.com/baksohyeon/mogui-ADE-orchestrator
$ cd mogui-ADE-orchestrator
```

Put the clone somewhere under the folder you intend as the workspace root, or treat the clone itself as a temporary install seat if you are still choosing a root. Onboarding will ask you to paste the absolute path of the workspace root later; relative paths and a bare `~` are not enough.

### Register the folder with Orca

In the Orca UI: add a project and browse to the folder you want (the workspace root, or this clone if that is where you are starting). From a terminal you can also add by path (verified: `orca repo add --path <path>`):

```console
$ orca repo add --path <path-to-folder>
```

Then open a terminal **inside that project** in Orca. The shell's working directory should be the checkout where you will start the agent (this clone for the installer session). Confirm with `pwd` in that pane.

If you open a terminal in a random directory outside the project, later placement and spawn steps measure the wrong seat. That is a measured failure mode, not a style preference.

## The first sentence

In the Orca terminal that is sitting in this clone, start the agent CLI you already pay for:

```console
$ claude
```

`claude` is the host that has been run hard as master. Other CLIs work as workers; Codex as master is untested rather than forbidden. Use whichever binary you actually have, as long as it is the one you will keep using for this installer session.

Then give the agent no task, only a wake-up. Any short phrase works. Examples people have used:

```text
Wake the master.
```

```text
Arise, my master.
```

What actually keys the router is the absence of a concrete task, not the ceremony of the phrase. An agent that opens this repository without an instruction becomes the onboarding guide and reads [`master-ops/ONBOARDING.md`](../../master-ops/ONBOARDING.md).

Expect an interview, not a silent install. The agent asks one or two decisions at a time, measures tools, and only then builds the operations repository and spawns Generation 1. Answering carefully matters more than answering fast; a wrong workspace root or a second founding on a half-finished install corrupts lineage.

Rough duration: long enough that you will make several decisions and watch a preflight and a spawn. Budget focused attention for the whole interview rather than leaving the agent unattended on the first run.

## What onboarding will ask, and why

Before tools and paths, the agent asks which **session mode** this is:

1. **Founding.** A genuinely new workspace: build the ops repository and spawn Generation 1.
2. **Reverify.** A workspace that already has an ops repository and a master: health check only. Spawning is blocked.
3. **Template improve.** You are changing this orchestrator repository itself: stop onboarding and treat the work as an ordinary task.

Pick Founding only when you are actually founding. An existing ops repository or lineage file means you are not Founding; recovery and succession live in the ops repository's succession card, not in a second install.

After mode classification, Founding walks decisions you should already have half-formed answers for:

| Decision | Why it exists |
| --- | --- |
| Workspace root (absolute path you paste) | Every later measurement and the master's seat hang off this path. The agent will not scan your home directory for candidates. |
| What the workspace is for, and which repositories belong in it | Becomes the inventory the master is allowed to coordinate. |
| Operations repository name and location | A separate git repository for governance: rules, lineage, runbooks. Not the product code. |
| Callsign for the living master session | "Master" is a temporary role label in the documents. The session you talk to gets a short name you will say out loud. |
| Issue tracker and optional skill stack | Execution state and optional methodology plugins. Declining optional skills is a normal answer. |
| Confirm spawn of Generation 1 | Creates one new terminal in the recorded workspace seat, hands it a kickoff, and waits for boot smoke. You should not type into that pane during the smoke. |

The installer session that interviews you is not the master. It retires after the founding spawn. The master is a new session in the workspace seat.

## Proof it worked

When founding finishes, you should be able to check these yourself without trusting a single "done" line.

1. **A master pane exists in the workspace seat.** In Orca, the Generation 1 session sits under the folder workspace of the workspace root (or under the primary worktree if the whole workspace is one repository). It should not hang only under one product repository in a multi-repository workspace.
2. **Boot smoke facts appear in that session's transcript.** Role State is declared (including the callsign). Configured model and measured model are reported as separate facts when measurement is possible. Placement evidence matches the intended workspace seat.
3. **The seat is not empty and not doubled.** Exactly one master for that workspace. A second master is an incident. The empty-seat gate before spawn and `scripts/master-succeed check-duplicates` exist because duplicate masters have already happened in the field.
4. **CLI view (optional).** From a machine with `orca` registered:

```console
$ orca terminal list
```

You should see the master terminal among the live sessions. Folder-workspace masters can show an empty worktree path and an "Unavailable worktree" chip in history; that label means "this seat is not a git worktree," which is normal for a folder workspace. Details: [Orca Concepts](orca-concepts.md).

If the installer claimed success but you cannot find the pane, or the pane is under the wrong project, stop and treat it as misplacement rather than starting a second founding.

## The first real task

Installation without a supervised handoff still feels like a longer chat. The point of the system shows up when the master proposes work, you approve, a worker runs under a contract, and the master accepts only on evidence.

Keep the first task small and concrete. Example shape (adapt names to your workspace):

```text
In the repository <repo-name>, open README.md and list the top-level section headings.
Do not edit any file. Return the heading list as the artifact.
```

What you should see, in order:

1. **Proposal.** The master restates the job as a narrow contract: target repository and checkout, allowed surface, acceptance criteria, evidence required, commit rules (for this example: no edits, no commit).
2. **Your approval.** Non-trivial work follows proposal then approval then execution. Say yes only when the contract matches what you meant.
3. **Dispatch.** The master opens a worker session (usually in a repository worktree on its own branch), hands it the contract, and waits on the orchestration mailbox rather than scraping the worker's screen.
4. **Result and acceptance.** The worker returns an artifact plus evidence. The master checks the evidence itself. "Done" from the worker is a claim; acceptance is the master's decision.

You can watch the worker pane while it runs. You can also stay in the master pane and wait for the completion message. Either way, the supervised path is Orca orchestration (`worker_done` and related message types), not a human copying text between tabs.

When the master has accepted that first small result, this guide is finished. Pull requests, succession, multi-repository tracks, and review lenses are separate documents: [Delegation and Review](delegation-and-review.md), [Master Lifecycle](master-lifecycle.md), [Concepts](concepts.md).

## What to do when something looks wrong

Each row is a shape first-timers actually hit. Run the check before changing random settings.

| What you see | Check | Likely fix |
| --- | --- | --- |
| Onboarding reads fine, then spawn cannot call the host | `command -v orca`; `orca status` | Register **Settings → Orca CLI → Shell command**. Skipping this is the failure that looks like a bug much later. |
| Preflight ends with `BLOCKED` | Read the `FAIL` lines from `bash scripts/onboarding-preflight.sh` | Install or repair each required gap. Waive only with `PREFLIGHT_WAIVE` when you understand the behaviour you are accepting. |
| Master pane sits under one product repo in a multi-repo workspace | Compare sidebar placement to the workspace root folder project | Misplacement. Do not found a second master. Use the ops repository succession / recovery path and [Orca Concepts](orca-concepts.md). Measured 2026-08-03. |
| Agent runs without Orca and keeps going on errors | Was Orca status ready before the session started? | Stop. Orca is required for live masters. Without it, completion detection falls back to screen polling and supervision is gone. Recorded as a real incident in the README. |
| "Unavailable worktree" on a master session | Is the master in a folder workspace? | Expected for folder seats. Not a crash. |
| Second session claims to be master | `orca terminal list`; ops lineage / duplicate check | Treat as an incident. Reverify mode never spawns. Do not re-run Founding against an existing ops repository. |
| Installer or master asks for a path and you gave a relative one | Does the path resolve the same from the agent's cwd? | Paste an absolute workspace root. Onboarding prefers an Orca "Copy path" action from the project UI. |

## If you are working on the harness itself

Tests are the agent's job. Ask it to run them and report back. Nothing on this page expects you to type a test command to complete first-run setup.

Command surface for scripts in this repository: [Reference](reference.md), pinned to local `scripts/` help output by a drift test.

Read next after a successful first worker: [Concepts](concepts.md), [Master Lifecycle](master-lifecycle.md), [Delegation and Review](delegation-and-review.md), or [Orca Concepts](orca-concepts.md).
