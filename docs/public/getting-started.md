The shortest path from a clone to a running master session. There is nothing to build and no test suite to run on the way.

# Getting Started

## What you need

Everything in this list serves one goal, a running master session. The core library itself stays callable with none of it: stdlib-only imports, no Orca, no setup, and it imports on a stock macOS Python 3.9. That path gives you the pure functions and nothing else, as the README says, and nothing below walks it back.

- [Orca](https://www.onorca.dev/download). The master lives in an Orca pane, which is what lets it outlive a window. Orca ships macOS, Linux, and Windows builds.
- The `orca` shell command. The runtime calls it to spawn, list, and retire master sessions, so succession does not work without it. Registering it is a step in Orca's settings, covered below.
- A coding-agent CLI you already pay for: Claude Code, Codex, Grok CLI, or another one. Any single one is enough.
- `python3` on `PATH` — whichever one the machine already has. The core is stdlib-only and no version floor is enforced: the preflight measures presence, not version. A tool that needs a more capable interpreter locates one itself at runtime and skips loudly when the host has none; the [Reference](reference.md) table states each tool's behavior in its own row.
- macOS is what this project has been developed and run on. One user has reported the install working on Linux. Windows is untested.

Two more tools are recommended rather than required, and the preflight warns on their absence instead of blocking:

- [`gitleaks`](https://gitleaks.io). The redaction gate uses it as its matching engine and exits 2 without it, so a host that publishes anything needs it. `brew install gitleaks` on macOS.
- [`ctx`](https://ctx.rs), with `ctx status` answering. The records practice queries agent history across providers through it. A host that does no history work loses nothing by skipping it.

`bash scripts/onboarding-preflight.sh` checks every item on this page. A missing required one exits 1 with `BLOCKED`, a missing recommended one warns and is repeated in the closing summary, and a `PREFLIGHT_WAIVE` entry downgrades a check rather than satisfying it, which the summary says out loud. Onboarding runs this as Step 0, so you do not have to audit the list by hand.

## Install and clone

macOS:

```console
$ brew install --cask stablyai/orca/orca
```

Linux: an AppImage or `.deb` from Orca's releases, or `yay -S stably-orca-bin` on Arch. Homebrew does not help here, because `--cask` only works on macOS. Note the executable is named `orca-ide` rather than `orca`, to avoid colliding with the GNOME screen reader of the same name.

Windows: `orca-windows-setup.exe` from releases.

All three are also on the [download page](https://www.onorca.dev/download).

Then clone:

```console
$ git clone https://github.com/baksohyeon/mogui-ADE-orchestrator
$ cd mogui-ADE-orchestrator
```

## Register the shell command

Open Orca, go to **Settings → Orca CLI**, and turn on **Shell command**. The app writes a launcher for the CLI it already bundles: a symlink under `/usr/local/bin` on macOS (it may ask for admin), a symlink under `~/.local/bin` on Linux, a batch wrapper plus a PATH entry on Windows.

Check it before going further:

```console
$ orca status
appRunning: true
runtimeState: ready
```

Skipping this is the failure that looks like a bug much later: onboarding reads fine, and then the founding spawn has nothing to call.

## Wake the master

Open that directory in Orca, start whichever coding agent you use inside it, and tell it to boot the master:

```text
Wake the master.
```

Any words work. The router keys on the absence of a task, not on a phrase, so an agent that opens this repository without an instruction becomes your onboarding guide. That is the whole setup step.

## What happens from there

It checks that Orca is usable, collects your workspace facts, proposes a name for your operations repository, registers the workspace folder with Orca, creates the ops repository, fills the template placeholders with your values, sets up an issue tracker, seeds the operating rules, and performs the founding spawn: a Generation 1 master session booted in your workspace root.

The last step is a boot smoke test, so you watch the first master come up. Three facts should appear:

```text
Role State is declared.
The configured model and measured model are reported separately.
Placement evidence matches the intended workspace.
```

You end with a master session running over your own repositories, not over this one.

The detailed flow lives in [master-ops/ONBOARDING.md](../../master-ops/ONBOARDING.md). The founding spawn uses `scripts/master-succeed spawn`, which fail-closes unless placement verification matches.

## If you are working on the harness itself

Tests are the agent's job. Ask it to run them and report back, the same way you ask it for anything else. Nothing here expects you to type a test command.

For the command surface, see [Reference](reference.md), written from the local `scripts/` help output and pinned to it by a test that fails on drift in either direction.

Read next: [Concepts](concepts.md), [Master Lifecycle](master-lifecycle.md), or [Reference](reference.md).
