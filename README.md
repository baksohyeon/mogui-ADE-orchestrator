# mogui-ADE-orchestrator

> A workspace-level **master runtime** for long-lived AI orchestrator sessions — verified succession between sessions, an append-only lineage ledger, contract-gated worker dispatch, and compaction-resilience probes. Python 3.10+, stdlib-only core.

## Which document do you want?

| You are | Start here |
| --- | --- |
| Reading about the system for the first time | [`docs/public/overview.md`](./docs/public/overview.md) |
| Installing it on your own workspace | [`master-ops/ONBOARDING.md`](./master-ops/ONBOARDING.md) |
| Looking for a specific document | [`docs/README.md`](./docs/README.md) — the document index |
| Reading the code | [Architecture](#architecture) below, then `src/master_runtime/core/` |

Documentation in this repository is English. `master-ops/` is a template that gets copied and substituted during onboarding, not documentation about this repository — see the index for why the two are separate.

## Why this exists

If you run a single long-lived AI agent session as the *orchestrator* ("master") of a multi-repository workspace, three failure modes show up that repo-level tooling doesn't cover:

1. **Sessions end, work doesn't.** Context windows fill up, sessions crash or get compacted. Handing off to a fresh session by pasting a summary loses role state, open work tracks, and standing decisions — and nobody notices what was lost until the successor repeats a question or reopens a settled decision.
2. **A master that can spawn workers can also waste them.** Delegating work to sub-agents (worker sessions) is cheap to trigger and expensive to run. Without a gate, duplicate dispatches, oversized inputs, and dispatches into the wrong directory tree go through silently.
3. **Context loss after compaction is invisible by default.** After a compaction event the session *feels* continuous but may have silently dropped state. If the boot sequence just re-feeds everything, you can never tell what the session actually still remembers.

This repo is a reference implementation of a runtime that treats these as first-class, testable problems: succession is a verified procedure with hard safety guards, lineage is an append-only ledger with a fixed schema, worker dispatch requires a readable contract file and passes through budget/routing checks, and the boot path deliberately withholds state after compaction to probe recall.

## Status

**Experimental, under active development.** Interfaces, CLI flags, and file formats change without notice. The core is exercised by a unit test suite (270 passing, 1 skipped as of 2026-07-31) and every unit listed below exists in `src/master_runtime/core/`. Nothing here should be treated as stable API — use it as a reference for the ideas, not as a dependency.

There is no model API in this repository. The runtime manages *sessions of* AI agents through their CLIs; it never calls a model endpoint and holds no API key.

## Core concepts

### Succession

`src/master_runtime/core/succession.py` implements master-to-master handoff as an explicit, guarded procedure rather than a copy-paste. `detect_trigger()` classifies signals into `IMMEDIATE` (explicit user instruction), `ADVISORY` (context usage ratio at or above the `0.60` default, or a natural milestone — advisory triggers **never** auto-start succession, they only propose it), or `NONE`. The flow then builds a handoff, spawns the successor, verifies the successor actually booted with the inherited state (`PASS` / `PARTIAL` / `FAILED`), checks for duplicate master instances, and retires the predecessor. Hard safety violations raise `SuccessionError` instead of proceeding.

The advisory ratio is a code default, not a claim about what any given workspace should use; an operating charter can set its own threshold.

### Lineage

`src/master_runtime/core/lineage.py` keeps an append-only markdown ledger of every succession: generation number, parent/successor session IDs, inherited role and open tracks, verification result, and honesty metrics such as `repeated_question_count`, `reopened_decision_count`, and a `context_loss_summary`. The schema is fixed (13 required fields), duplicate generations are rejected, and every write is re-verified as append-only. By design, lineage is observability metadata only — it never feeds runtime decisions.

### Contract-gated dispatch

`src/master_runtime/core/dispatch_gate.py` sits between the master and any worker dispatch. A `DispatchRequest` (runtime, contract file path, estimated input characters, agent count) is resolved to a `GateDecision` with a stable reason code: `OK`, `BUDGET_EXCEEDED` (defaults: 500k chars single / 1M batch), `DUPLICATE_CONTRACT` (same contract SHA within a 30-minute window), `ROUTING_VIOLATION`, `CONTRACT_UNREADABLE`, `HIGH_COST_RUNTIME`, `PATH_OUTSIDE_KNOWN_ROOTS`, `WORKTREE_AS_REPO_ROOT`, and others. Decisions are recorded in a JSONL ledger, so "what did the master dispatch, and why was it allowed" is always answerable.

### Acceptance loop

`src/master_runtime/core/acceptance/` runs candidate changes against a casebook and produces a scorecard instead of trusting a worker's completion report. Raw case results and aggregated scores are separate types, the casebook owns which split a case belongs to (an evaluator cannot relabel its own case), and holdout visibility is a single predicate so the private-holdout invariant cannot drift. Candidates that change nothing still produce a decision record.

### Compaction-resilience probe (E12)

`scripts/master-bootstrap-live` is a session-start hook that emits a small (~1KB budgeted) dynamic bootstrap block and is written to never fail the boot (any internal error degrades to a `[BOOTSTRAP-FALLBACK]` line with exit code 0). When the incoming session event reports `source == "compact"`, the hook deliberately **suppresses** the Role State and active-tracks sections from the block. The post-compaction session must recall that state from its own context first; the recalled version is then compared against the ledger. Silent context loss becomes a measurable event instead of an invisible one.

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
- **Vendor neutrality as a direction.** The master should be able to run under different AI agent hosts. Honestly stated: the reference adapter set is narrow — `adapter/profile.py` currently ships synchronous CLI profiles for `codex` and `cursor-agent`, `adapter doctor` probes a specific set of local tools, and some Korean-language operator strings are embedded. Broadening this is ongoing work.

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
