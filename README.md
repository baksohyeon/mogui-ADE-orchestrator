# mogui-ADE-orchestrator

> **Run one AI agent as the orchestrator of your whole workspace, on the subscription you already pay for.**
> No API key. No model endpoint. It drives the coding-agent CLIs you already use, across every repository in one folder, and it survives the session dying.

Point it at a folder that holds your product repositories. One master session plans, dispatches workers under contract, verifies their output before accepting it, and hands the role to a fresh session when the context fills up. Python 3.10+, stdlib-only core, MIT.

**What makes it different from an in-process agent framework**

| | in-process framework | this |
| --- | --- | --- |
| Cost model | API key, billed per token | your existing CLI subscription |
| Subagent | an actor inside the process | a real CLI session under a contract |
| Filesystem | virtual, pluggable backend | a git worktree |
| Approval | a runtime callback | a gate a human holds |
| Orchestrator dies | the graph dies with it | the successor takes the role and proves it |

## Quickstart

```bash
# Orca is the execution substrate. Install it first.
brew install --cask stablyai/orca/orca      # or download: https://www.onorca.dev/download

git clone https://github.com/baksohyeon/mogui-ADE-orchestrator
cd mogui-ADE-orchestrator

# nothing else to install. stdlib only.
PYTHONPATH=src python3 -m unittest discover -s tests -q

# try the pure functions, no setup needed
scripts/master-succeed detect "routine status update" --context-ratio 0.7 --json
scripts/dispatch-gate --ledger /tmp/gate.jsonl check \
  --runtime codex --contract README.md --agents 1 --est-chars 1000
scripts/adapter doctor
```

Then set it up on your own workspace: open the cloned folder in a coding agent and it routes into [`master-ops/ONBOARDING.md`](./master-ops/ONBOARDING.md), a two-stage flow that scaffolds an operations repository and boots your first master session.

### Why Orca

A master that outlives one session needs somewhere to live. A terminal tab is not that place. [Orca](https://www.onorca.dev/download) is, and it is the one dependency this project does not abstract away.

- **Sessions outlive the window.** Close the tab, restart the app, come back tomorrow: the session is still there with a stable handle you can read, write to, and retire on purpose. Succession is only auditable because the predecessor is still addressable while you verify the successor.
- **Warm context is money.** A long-lived session keeps its prompt cache warm. Re-spawning a fresh agent for every task pays the context tax again every time.
- **Many agents, many accounts.** Run several CLI agents side by side, on different runtimes and different accounts, and switch when one runs out of credit. Your orchestrator does not have to die because a worker's quota did.
- **Placement is addressable.** Every pane carries a worktree identity, so "which folder did that worker actually run in" has an answer you can check instead of infer.
- **Reachable from anywhere.** Put it behind Tailscale and the same running sessions answer from another machine. Long jobs do not need you sitting in front of the laptop that started them.

Without this substrate you can still read the ideas here. You cannot run a master that survives its own session.

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

## Getting started

Prerequisites: **Python 3.10+**. The runtime is stdlib-only; there is nothing to install.

Run the test suite (fastest way to see every unit exercised):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

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
