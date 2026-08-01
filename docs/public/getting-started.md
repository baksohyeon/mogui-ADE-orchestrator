The shortest path from a clone to a running master session. There is nothing to build and no test suite to run on the way.

# Getting Started

## What you need

- macOS. That is the only platform this has been built and run on. Other platforms are planned, not supported yet.
- [Orca](https://www.onorca.dev/download). The master lives in an Orca pane, which is what lets it outlive a window.
- A coding-agent CLI you already pay for: Claude Code, Codex, Grok CLI, or another one. Any single one is enough.

## Install and clone

```bash
brew install --cask stablyai/orca/orca      # or download: https://www.onorca.dev/download
git clone https://github.com/baksohyeon/mogui-ADE-orchestrator
```

## Wake the master

Open the cloned folder in Orca, start whichever coding agent you use, and say something like:

```
Wake the master.
```

That is the setup step. The words are yours to pick: the entry-point router keys on the absence of a task, not on a phrase. An agent that opens this folder with no specific instruction becomes your onboarding guide, and one that arrives carrying a contract, an issue, or a fix request gets on with that instead. Summon it however you want to.

The guide introduces the system in three sentences and then walks you through setup, asking rather than assuming.

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

For the command surface, see [Reference](reference.md), generated from the local `scripts/` help output.

Read next: [Concepts](concepts.md), [Master Lifecycle](master-lifecycle.md), or [Reference](reference.md).
