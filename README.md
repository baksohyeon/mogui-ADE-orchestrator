# mogui-ADE-orchestrator

> **Run one AI agent as the orchestrator of your whole workspace, on the subscription you already pay for.**
> No API key. No model endpoint. It drives the coding-agent CLIs you already use, across every repository in one folder, and it survives the session dying.

Point it at a folder that holds your product repositories. One master session plans, dispatches workers under contract, verifies their output before accepting it, and hands the role to a fresh session when the context fills up. macOS only for now, other platforms planned. Python 3.10+, stdlib-only core, MIT.

First, about the comparison below. This harness was not derived from deepagents. It was built for its own reasons, reached this shape on its own, and only afterward did its author come across deepagents and recognize the same system described from the other end. The comparison was written at publication time, looking back at two designs that had converged. The repository history shows it plainly: two weeks of commits with no mention of deepagents, then the comparison arriving on the same day as the public docs.

**If you are going to use an API key, use [LangChain deepagents](https://docs.langchain.com/oss/python/deepagents/overview).** It is well documented and it solves this problem inside your process. This project is for the other case: you already pay for coding-agent CLIs and you want one orchestrator driving all of them, with no key and no per-token bill.

| | LangChain deepagents | this |
| --- | --- | --- |
| Cost model | API key, billed per token | your existing CLI subscription |
| Subagent | an actor inside the process | a real CLI session under a contract |
| Filesystem | virtual, pluggable backend | a git worktree |
| Approval | a runtime callback | a gate a human holds |
| Orchestrator dies | the graph dies with it | the successor takes the role and proves it |

## Quickstart

```bash
brew install --cask stablyai/orca/orca      # or download: https://www.onorca.dev/download
git clone https://github.com/baksohyeon/mogui-ADE-orchestrator
```

Open the cloned folder in Orca, start any coding agent in it, and say something like:

```
Wake the master.
```

The words are yours to pick. The entry-point router keys on the absence of a task, not on a phrase. An agent that opens this folder with no specific instruction becomes your onboarding guide; one that arrives carrying a contract, an issue, or a fix request gets on with that instead. So summon it however you want to.

There is nothing to install and nothing to configure first. The guide introduces the system in three sentences and then walks you through setup, asking rather than assuming.

What it asks and does, in order: checks that Orca is usable, collects your workspace facts, proposes a name for your operations repository, registers the workspace folder with Orca, creates the ops repository, fills the template placeholders with your values, sets up an issue tracker, seeds the operating rules, explains which settings live where, and then performs the founding spawn: a fresh Generation 1 master session booted in your workspace root. The last step runs a boot smoke test so you see it come up.

Stage one asks nothing and scaffolds. Stage two is the conversation. You end with a master session running over your own repositories, not over this one.

<details><summary>Prefer to poke at it before installing anything</summary>

The core is stdlib-only, so you can call it without Orca and without setup. You will not get a master session this way, just the pure functions.

```bash
cd mogui-ADE-orchestrator
scripts/master-succeed detect "routine status update" --context-ratio 0.7 --json
scripts/dispatch-gate --ledger /tmp/gate.jsonl check \
  --runtime codex --contract README.md --agents 1 --est-chars 1000
scripts/adapter doctor
```

</details>

### Why Orca

A master that outlives one session needs somewhere to live. A terminal tab is not that place. [Orca](https://www.onorca.dev/download) is, and it is the one dependency this project does not abstract away.

- **Sessions outlive the window.** Close the tab, restart the app, come back tomorrow: the session is still there with a stable handle you can read, write to, and retire on purpose. Succession is only auditable because the predecessor is still addressable while you verify the successor.
- **Warm context is money.** A long-lived session keeps its prompt cache warm. Re-spawning a fresh agent for every task pays the context tax again every time.
- **Many agents, many accounts.** Run several CLI agents side by side, on different runtimes and different accounts, and switch when one runs out of credit. Your orchestrator does not have to die because a worker's quota did.
- **Placement is addressable.** Every pane carries a worktree identity, so "which folder did that worker actually run in" has an answer you can check instead of infer.
- **Reachable from anywhere.** Put it behind Tailscale and the same running sessions answer from another machine. Long jobs do not need you sitting in front of the laptop that started them.

Without this substrate you can still read the ideas here. You cannot run a master that survives its own session.

### The tools this actually runs on

Vendor-neutral here means the master is not tied to one *AI agent host*. It does not mean the tooling is a mystery. These are the real dependencies, by name.

| Tool | What it does here | Replaceable? |
| --- | --- | --- |
| [Orca](https://www.onorca.dev/download) | Execution substrate. Terminal sessions that outlive the window, worktree-scoped placement, dispatch and retirement of worker panes. | No. Everything about session lifetime assumes it. |
| [beads](https://github.com/gastownhall/beads) (`bd`) | Work ledger. Tracks, issues, dependencies, and the memory block the boot path audits. `master-bootstrap-live` shells out to `bd` for active-track lines. | Yes, through the adapter. Any tracker with a CLI that lists issues by status works. |
| [ctx](https://ctx.rs) | Session archive index. Lets a master search what an earlier session actually said instead of trusting a summary of it. | Yes, through the adapter. |
| Git | Long-term source of truth. Charters, decisions, runbooks, lineage. Worktrees are also the isolation primitive for workers. | No. |

The split matters: `core/` never learns these names, `adapter/` wires them, and swapping one means writing an adapter rather than editing the units. `adapter/profile.py` currently ships synchronous CLI profiles for `codex` and `cursor-agent`; that is the layer where an agent host gets named, and it is the only one.

### The skill layer it runs under

Recommended, not required. Orca is still the only hard dependency, and every script here runs with none of this installed. This section exists because the reference master does run under a specific skill stack, and vendor-neutral should not turn into "we won't say what we use."

Optimized for Claude Code. These are Claude Code plugins and skills. Workers can be Codex or another CLI, and the adapter ships a `codex` profile, but the orchestrator side assumes Claude Code.

| Layer | Tool | What it does in the harness |
| --- | --- | --- |
| Method | [superpowers](https://github.com/obra/superpowers) | Puts process ahead of code. A SessionStart hook injects a rule that a relevant skill must be invoked before any response, including clarifying questions. Ships brainstorming, plan writing and execution, TDD, systematic debugging, code review on both sides, and verification before completion. |
| Lifecycle | [GSD](https://github.com/open-gsd/gsd-core) | The largest harness footprint of the four. A spec to plan to execute to verify command set, plus around a dozen hooks: a statusline, a context monitor that warns the agent rather than only the user as the window fills, prompt-injection scanners over both written and read content, a guard that blocks writes outside the worktree root, and commit validation. |
| Commands | [gstack](https://github.com/garrytan/gstack) | Task commands rather than methodology: ship, review, QA, headless-browser dogfooding, plan review from CEO, engineering, and design angles, context save and restore. |
| State | [beads](https://github.com/gastownhall/beads) | Listed in the table above. The boot path already shells out to it. |

Install them yourself. Onboarding will explain each one and print the commands; it does not run them. GSD's installer edits `~/.claude/settings.json` and wires hooks across most lifecycle events, which is not something an agent should do to your configuration on your behalf.

```bash
claude plugin install superpowers@claude-plugins-official
```

GSD ships as `@opengsd/gsd-core` on npm, and gstack installs into `~/.claude/skills/gstack`. Follow their own install instructions rather than a copy of them here, which would go stale.

One integration note if you adopt GSD. Its context monitor warns the agent at 35% context remaining and escalates at 25%, which is well before the succession threshold this project recommends. Left alone, a master gets told to stop and save state while its own charter says to keep working. Either raise the thresholds in the monitor or record in your charter that the warning is advisory and not a succession trigger. The values live in `gsd-context-monitor.js`, and GSD's own `/gsd-update --reapply` flow carries local edits across updates.

## Which document do you want?

| You are | Start here |
| --- | --- |
| Reading about the system for the first time | [`docs/public/overview.md`](./docs/public/overview.md) |
| Installing it on your own workspace | [`master-ops/ONBOARDING.md`](./master-ops/ONBOARDING.md) |
| Looking for a specific document | [`docs/README.md`](./docs/README.md) (the document index) |
| Reading the code | [Architecture](#architecture) below, then `src/master_runtime/core/` |

Documentation in this repository is English. `master-ops/` is a template that gets copied and substituted during onboarding, not documentation about this repository. See the index for why the two are separate.

## Why this exists

If you run a single long-lived AI agent session as the *orchestrator* ("master") of a multi-repository workspace, three failure modes show up that repo-level tooling doesn't cover:

1. **Sessions end, work doesn't.** Context windows fill up, sessions crash or get compacted. Handing off to a fresh session by pasting a summary loses role state, open work tracks, and standing decisions. You find out when the successor repeats a question you already answered, or reopens a decision you already made.
2. **A master that can spawn workers can also waste them.** Delegating work to sub-agents (worker sessions) is cheap to trigger and expensive to run. Without a gate, duplicate dispatches, oversized inputs, and dispatches into the wrong directory tree all go through, and nothing tells you.
3. **Context loss after compaction is invisible by default.** After a compaction event the session reads as continuous while some state is gone. Re-feed everything at boot and you lose your only chance to find out what the session still holds.

This repo is a reference implementation of a runtime that treats these as first-class, testable problems: succession is a verified procedure with hard safety guards, lineage is an append-only ledger with a fixed schema, worker dispatch requires a readable contract file and passes through budget/routing checks, and the boot path withholds state after compaction to probe recall.

## Status

Working and exercised: 271 unit tests pass (1 skipped, as of 2026-08-01), every unit listed below exists in `src/master_runtime/core/`, and the succession, dispatch-gate, acceptance, and compaction paths have all run against real workspaces.

Moving fast: interfaces, CLI flags, and file formats still change without notice. Pin a commit if you build on it.

## Core concepts

### Succession

`src/master_runtime/core/succession.py` implements master-to-master handoff as an explicit, guarded procedure rather than a copy-paste. `detect_trigger()` classifies signals into `IMMEDIATE` (explicit user instruction), `ADVISORY` (context usage ratio at or above the `0.60` default, or a natural milestone; advisory triggers **never** auto-start succession, they only propose it), or `NONE`. The flow then builds a handoff, spawns the successor, verifies the successor booted with the inherited state (`PASS` / `PARTIAL` / `FAILED`), checks for duplicate master instances, and retires the predecessor. Hard safety violations raise `SuccessionError` instead of proceeding.

The advisory ratio is a code default, not a claim about what any given workspace should use; an operating charter can set its own threshold.

### Lineage

`src/master_runtime/core/lineage.py` keeps an append-only markdown ledger of every succession: generation number, parent/successor session IDs, inherited role and open tracks, verification result, and honesty metrics such as `repeated_question_count`, `reopened_decision_count`, and a `context_loss_summary`. The schema is fixed (13 required fields), duplicate generations are rejected, and every write is re-verified as append-only. By design, lineage is observability metadata only; it never feeds runtime decisions.

### Contract-gated dispatch

`src/master_runtime/core/dispatch_gate.py` sits between the master and any worker dispatch. A `DispatchRequest` (runtime, contract file path, estimated input characters, agent count) is resolved to a `GateDecision` with a stable reason code: `OK`, `BUDGET_EXCEEDED` (defaults: 500k chars single / 1M batch), `DUPLICATE_CONTRACT` (same contract SHA within a 30-minute window), `ROUTING_VIOLATION`, `CONTRACT_UNREADABLE`, `HIGH_COST_RUNTIME`, `PATH_OUTSIDE_KNOWN_ROOTS`, `WORKTREE_AS_REPO_ROOT`, and others. The gate writes each decision to a JSONL ledger, so you can answer what the master dispatched and why it was allowed.

### Acceptance loop

`src/master_runtime/core/acceptance/` runs candidate changes against a casebook and produces a scorecard instead of trusting a worker's completion report. Raw case results and aggregated scores are separate types, the casebook owns which split a case belongs to (an evaluator cannot relabel its own case), and holdout visibility is a single predicate so the private-holdout invariant cannot drift. Candidates that change nothing still produce a decision record.

### Compaction-resilience probe (E12)

`scripts/master-bootstrap-live` is a session-start hook that emits a small (~1KB budgeted) dynamic bootstrap block and is written to never fail the boot (any internal error degrades to a `[BOOTSTRAP-FALLBACK]` line with exit code 0). When the incoming session event reports `source == "compact"`, the hook **suppresses** the Role State and active-tracks sections. The post-compaction session has to recall that state from its own context first, and you compare what it recalled against the ledger. That turns silent context loss into a number you can read.

## Architecture

```
src/master_runtime/core/
├── bootstrap.py        # session boot: charter + handoff + role state, char-budgeted
├── bootstrap_live.py   # live boot block for session-start hooks (audits, dual-instance check)
├── succession.py       # trigger detection, handoff, spawn/verify/retire
├── lineage.py          # append-only succession ledger
├── dispatch_gate.py    # contract-gated worker dispatch decisions
├── recovery.py         # recovery flow after abnormal termination
├── watchdog.py         # stall detection for dispatched work
├── digest_loop.py      # read-only L1 digest loop for orchestrator observations
├── work_ledger.py      # workspace track ledger and session cache
├── context/            # pure filesystem context resolver (path -> ContextDescriptor)
├── approval/           # approval gates and registry
├── acceptance/         # casebook-driven acceptance loop and scorecards
└── adapter/            # adapter layer: dispatch, doctor, isolation, profile
```

Two principles shape the layout:

- **Core / adapter split.** `core/` modules avoid depending on any specific agent product; contact with the outside world (process spawning, ledgers, tool CLIs) goes through injected callables and the `adapter/` layer, so core logic is testable with in-memory fakes. Tool names live in `adapter/`, not in the units above it.
- **Vendor neutrality as a direction.** The master should be able to run under different AI agent hosts. The reference adapter set is narrow. `adapter/profile.py` currently ships synchronous CLI profiles for `codex` and `cursor-agent`, `adapter doctor` probes a specific set of local tools, and some Korean-language operator strings are embedded. Broadening this is ongoing work.

## Working on the harness

To use the system, the [Quickstart](#quickstart) above is the whole path. This section is for changing the harness itself.

Prerequisites: macOS and **Python 3.10+**. The runtime is stdlib-only; there is nothing to install.

All CLI entry points live in `scripts/` and are self-contained (they insert `src/` on `sys.path` themselves):

```bash
# Classify a succession trigger signal (pure function, safe to try)
scripts/master-succeed detect "routine status update" --context-ratio 0.7 --json
# → {"status": "ADVISORY", "reason": "context ratio threshold reached", ...}

# Ask the dispatch gate whether a worker dispatch may proceed
scripts/dispatch-gate --ledger ./gate-ledger.jsonl check \
  --runtime codex --contract ./job-contract.md --agents 1 --est-chars 1000
# → {"allow": true, "reason": "OK", "contract_sha": "...", "cost_proxy": 1000}

# Check which adapter-layer tools are present on this machine
scripts/adapter doctor

# Boot a master session from a charter document (add --handoff for a handoff file)
scripts/master-bootstrap --charter path/to/charter.md --json
```

Other entry points, briefly: `scripts/master-succeed` also provides `handoff`, `verify-successor`, `check-duplicates`, `retire`, and `spawn` subcommands; `scripts/master-recover` runs the recovery flow from a charter + handoff after abnormal termination; `scripts/master-bootstrap-live` is meant to be wired as a session-start hook rather than run by hand; `scripts/l1-digest tick` advances the read-only digest loop; `scripts/adapter dispatch` performs an adapter-level worker dispatch; `scripts/acceptance-loop` runs the acceptance casebook. Run any of them with `--help` for current flags.

Tests are the agent's job. Ask the agent working on the harness to run them and report, the same way you ask it for anything else. There is no test step here for a person to type.

Sibling product of [mogui-agent-harness](https://github.com/baksohyeon/mogui-agent-harness):

| | mogui-agent-harness | mogui-ADE-orchestrator (this repo) |
|---|---|---|
| Layer | Repository Harness (repo-local runtime) | Workspace Master Runtime |
| Unit of operation | one repository | a workspace of many repositories |
| Owns | repo-local rules, hooks, wiki, runbooks | orchestration state, roles, succession, lineage |

## What this is not

This repo owns workspace-level orchestration state only. Repo-local rules, hooks, wikis, and runbooks belong to a repository-harness layer (see the sibling project above); the connection between the two layers is contract-based, never source-tree coupling. Submodules only ever appear as pinned example fixtures, never as core dependencies.

## License

MIT
