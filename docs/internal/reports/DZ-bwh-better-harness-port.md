# better-harness Port Report

- **Job ID:** `DZ-bwh-mogui-bh-port`
- **Reference:** [`langchain-ai/deepagents`](https://github.com/langchain-ai/deepagents) `examples/better-harness/` (MIT), files `better_harness/{core,agent,patching,runners}.py`
- **Target:** this repository, `main`
- **Scope:** selective port of evaluation-loop patterns this harness lacked. Not a rewrite.

Language note: this report follows the repository convention of English docs
(`docs/planning/*`, `docs/architecture/*`); the work order itself was Korean.

Sections 1–7 record the initial port (`c4203ba`). Review remediation followed in r2;
where r2 changed a decision — notably the CLI argv table in §2.3 and the handling of a
candidate that declares no surface — the **r2 Supplement** at the end supersedes them.

## 1. Gap Analysis

The reference optimizes an *inner agent's harness surfaces* using evals. This repository
is a **workspace Master Runtime**: it decides whether a worker may be dispatched, tracks
roles/succession/lineage, and observes running jobs. Mapping the reference's five
patterns onto what already exists here:

| # | Pattern | Repository state before this port | Gap |
|---|---|---|---|
| 1 | Deterministic acceptance gate (`combined pass count` comparison, no model judgement) | `core/dispatch_gate.py` is deterministic but gates **dispatch** (budget, duplicate contract SHA, ticket, probe). `core/approval/registry.py` gates **intent** and requires `HUMAN` authority for G2/G3. Nothing deterministically gates the **deliverable** a worker returns; `verify_successor` in `core/succession.py` only checks master succession. | **Real, high value.** Acceptance of worker output was judgement-only. |
| 2 | train/holdout/scorecard split with a private holdout | No evaluation-case concept at all. A worker receives the whole contract, so every criterion it will be judged on is visible to it. | **Real.** Structural overfitting was unpreventable. |
| 3 | Single-seam LLM adapter, subscription CLI instead of an API-key SDK | Partially present: `core/adapter/dispatch.py` already isolates execution behind an injectable `Runner`, and `core/adapter/profile.py` defines a neutral `ToolProfile`. But the only profile is `CodexCompanionProfile` (node + companion `.mjs`, async job-id + probe), and `scripts/adapter` hard-restricts `--runtime` to `codex`. | **Partial.** The seam pattern exists; a synchronous subscription-CLI seam did not. |
| 4 | Auditable per-iteration `decision.json` | Append-only JSONL ledgers exist (`dispatch_gate`, `work_ledger`, `lineage`), but they record *dispatch* events. No per-iteration accept/reject record with reason and changed surface. | **Real, small.** |
| 5 | Failed case permanently enters the next round's eval set | No accumulation structure. | **Real.** Depends on #2 existing first. |

## 2. What Was Ported

All five, in a single new package `src/master_runtime/core/acceptance/`, adapted to this
repository's core/adapter boundary (core stays tool-name-free and testable with in-memory
fakes; `adapters/` deletion must not break core tests).

### 2.1 Deterministic acceptance gate (pattern 1)

`acceptance/verdict.py`. `decide()` is a pure comparison:

```
accepted  <=>  candidate.combined_passed() > current.combined_passed()
```

`combined_passed()` sums the `train` and `holdout` splits only — `scorecard` is excluded,
mirroring the reference, which runs the scorecard on baseline and final only. Three stable
reason codes: `PASS_COUNT_INCREASED`, `NO_PASS_COUNT_INCREASE`, `NO_CANDIDATE_CHANGE`.
No natural-language rationale, score heuristic, or model verdict participates.

Deliberately kept pure: no "holdout must not regress" veto was added. A veto would be a
different (stricter) policy than the reference contract, and mixing policies into the
comparison is exactly what makes an acceptance gate unauditable. A candidate that trades
one holdout pass for one train pass therefore lands on `delta == 0` and is rejected by the
strict-increase rule, which is the intended behaviour.

Two fail-closed additions the reference gets for free from pytest but this repository needs
explicitly, because the evaluator is an injected callable:

- `score_results()` treats a **missing** case result as a failure, so an evaluator that
  silently skips a case cannot raise a candidate's pass count.
- Split and stratum are taken from the case book, never from the evaluator's reply, so a
  result cannot relabel a holdout case as a train case.

### 2.2 Visible/private split (pattern 2)

`acceptance/casebook.py` and `acceptance/layout.py`.

- Splits `train` / `holdout` / `scorecard`, with the reference's aliases plus
  `visible`→`train`, `private`→`holdout`.
- `CaseBook.validate()` fails closed unless both `train` and `holdout` are non-empty and
  cover the **same strata** — the reference's guarantee that the holdout is representative.
  Strata comparison ignores `origin=regression` cases, which only ever land in `holdout`.
- `AcceptanceRunLayout` routes artifacts by visibility: `history/visible/**` for train
  results and iteration decisions, `history/private/**` for holdout and scorecard results.
- `build_proposer_workspace()` writes only visible artifacts, and the workspace is the only
  thing a proposer is handed.

A regression test asserts no holdout case id appears in any file of the proposer workspace.
The test was mutation-checked: reverting `casebook.visible_manifest()` to
`casebook.manifest()` makes it fail.

### 2.3 Single-seam subscription-CLI proposer (pattern 3)

`acceptance/proposer.py`. Every model call goes through `invoke_cli_proposer()`. It builds
argv for the three subscription CLIs and shells out — no SDK import, no API key:

| runtime | argv |
|---|---|
| `claude` | `claude -p <prompt> [--model M]` |
| `codex` | `codex exec [--model M] <prompt>` |
| `cursor-agent` | `cursor-agent -p --trust --force [--model M] <prompt>` |

The prompt is always a single argv element and never reaches a shell. Tests follow the
reference's seam-monkeypatch style
(`monkeypatch.setattr("…acceptance.loop.invoke_cli_proposer", fake)`), plus an injected
`runner` for the unit-level path.

The candidate contract is explicit and fail-closed: the proposer must write
`candidate.json` (`{"surfaces": [...], "summary": "..."}`) into its workspace; the task
prompt carries the absolute path. Missing, malformed, or empty-`surfaces` file, or a
non-zero CLI exit, all yield "no candidate" and stop the loop rather than producing a
silent no-op iteration.

### 2.4 Auditable decision records (pattern 4)

`AcceptanceRunLayout.write_iteration_decision()` writes
`history/visible/iterations/NNN/decision.{json,md}` per iteration with: decision,
reason code, changed surfaces, `current_combined` → `candidate_combined` and delta,
starting/candidate labels, candidate ref, pinned regressions, and the proposer summary.
The final `report.json` / `report.md` aggregate the run. Prior decisions are fed back into
the next proposer workspace as `history.json`, as the reference does.

### 2.5 Regression accumulation (pattern 5)

`RegressionLog` — append-only JSONL, deduplicated by `case_id`. Every failure observed in
any round is pinned. On the next run, `RegressionLog.apply(casebook)` merges pinned cases
back in:

- still configured → its configured split is preserved;
- **dropped from the config → re-admitted as a private `holdout` case** with
  `origin=regression`.

That second rule is the part worth keeping: a case a proposer pressured out of the book
comes back where the proposer cannot see it.

## 3. What Was Not Ported, and Why

| Reference feature | Decision | Reason |
|---|---|---|
| `patching.py` — `module_attr` / `workspace_file` surface patching, `sitecustomize` + `PYTHONPATH` injection | **Not ported** | Requires knowing the target repo's module layout and import graph. This repository's stated non-goals are "repository implementation knowledge" and source-tree coupling. A candidate here is an opaque `ref` the injected evaluator resolves. |
| `runners.py` — pytest and Harbor runners (nodeid rendering, junit.xml, `--evals-report-file`) | **Not ported** | Both are repo-local test-framework knowledge, i.e. mogui-agent-harness territory. Replaced by an injected `Evaluator` callable plus a generic `command_evaluator` (exit 0 = pass). |
| LangSmith trace fetch, `trace_refs.json`, URL scraping | **Not ported** | Network egress to a third-party service and an env-var API key, in a stdlib-only core. The repo already has `ctx` as its trace-archive adapter. |
| Outer Deep Agent (`create_deep_agent`, `FilesystemBackend`, `uv run --project` subprocess, `DEEPAGENTS_ROOT`) | **Not ported** | Replaced wholesale by the subscription-CLI seam, per the work order. |
| TOML config (`tomllib`) | **Substituted** | `tomllib` is 3.11+; this repo's stated prerequisite is Python 3.10+ and stdlib-only. Config is JSON. |
| `Variant` / surface-value materialization and `variants/*.json` | **Not ported** | Same reason as `patching.py`. `Candidate.surfaces` keeps only the *declared* changed-surface list, which is what the audit record needs. |
| Transient-error retry (`overloaded`, `529`, rate limit) with backoff | **Not ported** | The repo already owns liveness elsewhere (`core/watchdog.py`, `dispatch-gate watch`). Adding a second retry policy inside the loop would split that ownership. Noted as a follow-up. |

## 4. Files

New (all stdlib-only):

| File | Lines | Contents |
|---|---:|---|
| `src/master_runtime/core/acceptance/__init__.py` | 107 | package exports |
| `src/master_runtime/core/acceptance/casebook.py` | 378 | `CaseSplit`, `CaseOrigin`, `VerificationCase`, `CaseBook`, `RegressionLog`, split manifests |
| `src/master_runtime/core/acceptance/verdict.py` | 284 | `CaseResult`, `SplitScore`, `Scorecard`, `decide()`, `score_results()` |
| `src/master_runtime/core/acceptance/proposer.py` | 162 | CLI seam: `build_proposer_argv()`, `invoke_cli_proposer()` |
| `src/master_runtime/core/acceptance/models.py` | 90 | `Candidate`, `ProposerContext`, `AcceptanceConfig`, `Evaluator`/`Proposer` aliases |
| `src/master_runtime/core/acceptance/layout.py` | 171 | `AcceptanceRunLayout` (visible/private routing, `decision.json`) |
| `src/master_runtime/core/acceptance/report.py` | 151 | `IterationRecord`, `AcceptanceReport` |
| `src/master_runtime/core/acceptance/loop.py` | 357 | `build_proposer_workspace()`, `read_candidate()`, `cli_proposer()`, `run_acceptance_loop()` |
| `src/master_runtime/core/acceptance/config.py` | 104 | JSON config loading |
| `src/master_runtime/core/acceptance/evaluators.py` | 92 | `command_evaluator()` |
| `scripts/acceptance-loop` | 170 | CLI: `validate` / `split` / `run` / `inspect` |
| `tests/test_acceptance_casebook.py` | 225 | 20 tests |
| `tests/test_acceptance_verdict.py` | 155 | 12 tests |
| `tests/test_acceptance_proposer.py` | 144 | 13 tests |
| `tests/test_acceptance_config.py` | 182 | 10 tests |
| `tests/test_acceptance_loop.py` | 485 | 17 tests |

Modified: none. No existing module, script, or test was touched.

## 5. Tests

```
PYTHONPATH=src python3 -m pytest tests -q
241 passed, 1 skipped in 1.68s
```

Baseline before the port was `169 passed, 1 skipped`; the 72 new tests are all additions.

Coverage highlights, by pattern:

- **1** — accept on strict increase; reject on equal; reject when a train gain is paid for
  by a holdout loss; reject an unchanged candidate even when it scores higher; missing
  result counted as a failure; evaluator-supplied split/stratum ignored; scorecard excluded
  from the combined count.
- **2** — no holdout id in the proposer workspace (mutation-checked); `visible_manifest()`
  excludes private ids; artifacts routed to `history/private/**`; strata-equality validation.
- **3** — argv shape per runtime, model flag placement, prompt never shell-interpolated,
  unsupported runtime rejected, injected runner honoured, `loop.invoke_cli_proposer`
  monkeypatched end-to-end, CLI failure ⇒ no candidate, `candidate.json` fail-closed paths.
- **4** — every `decision.json` field asserted; `decision.md` written; report files written
  and `report.to_markdown()` matches the file on disk.
- **5** — each failure pinned exactly once; a case dropped from the config returns as a
  private holdout regression and is actually evaluated in the next run.

Also verified manually, outside the repo tree, with a stub `claude` binary on `PATH`:
`acceptance-loop validate` / `split` / `run` / `inspect` all behave, the run directory has
the expected visible/private shape, and a no-op candidate is correctly rejected with
`NO_PASS_COUNT_INCREASE`. `scripts/redaction-scan.sh` reports 0 findings.

Optional `mypy` was not run — it is not installed in this environment.

## 6. Usage

```jsonc
// acceptance.json
{
  "name": "example",
  "workspace_root": "/abs/path/to/repo",
  "run_dir": "runs/example",
  "max_iterations": 3,
  "proposer": { "runtime": "claude", "model": null, "timeout_seconds": 1800 },
  "regression_log": ".mogui/acceptance-regressions.jsonl",
  "cases": [
    { "case_id": "t1", "split": "train",   "stratum": "unit", "command": ["pytest", "-q", "tests/test_a.py"] },
    { "case_id": "h1", "split": "holdout", "stratum": "unit", "command": ["pytest", "-q", "tests/test_b.py"] }
  ]
}
```

```bash
scripts/acceptance-loop validate --config acceptance.json
scripts/acceptance-loop split    --config acceptance.json
scripts/acceptance-loop run      --config acceptance.json --restore-cmd "git checkout -- ."
scripts/acceptance-loop inspect  --run-dir runs/example
```

`run` exits `0` only when every gated case passes, `1` otherwise, `2` on a config error.

**`--restore-cmd` is mandatory when `--max-iterations > 1`.** In CLI mode the proposer edits
the workspace in place, so iterating past a rejected candidate without rolling it back would
evaluate a dirty tree. Library callers that hand out isolated refs (worktree or git rev per
candidate) do not need it and can pass `on_reject=None`.

Library use keeps the core boundary intact — inject your own evaluator:

```python
report = run_acceptance_loop(
    config=config,
    casebook=casebook,
    baseline=Candidate(label="baseline", ref="HEAD"),
    proposer=cli_proposer(config),
    evaluator=my_worktree_evaluator,   # Callable[[Candidate, Sequence[VerificationCase]], Sequence[CaseResult]]
    regression_log=RegressionLog(".mogui/acceptance-regressions.jsonl"),
)
```

## 7. Follow-ups (not done, deliberately)

1. **Wire into dispatch.** `core/adapter/dispatch.py` returns a `job_id` after probe
   registration; nothing yet feeds the resulting deliverable into `run_acceptance_loop`.
   That wiring is a separate decision about who owns candidate refs.
2. **Transient-CLI-error retry.** Should reuse `core/watchdog.py` rather than growing a
   second retry policy inside the loop.
3. **Ledger unification.** The regression log is its own JSONL file. If acceptance events
   should live in the dispatch ledger or the work ledger, that is a schema decision for the
   master, not something to assume.
4. **`ToolProfile` for CLI runtimes.** Not added: `ToolProfile` is built around async
   dispatch + `job_id` + probe, which `claude -p` and `codex exec` (synchronous, no job id)
   do not have. Forcing them in would distort the existing contract.

---

# r2 Supplement — Review Remediation

- **Job ID:** `DZ-bwh-mogui-bh-port-r2`
- **Reviews addressed:** reuse / simplification / efficiency / altitude, against commit `c4203ba`
- **Out of scope by instruction** (queued separately by the requester): the four
  repo-wide core consolidations — a shared JSONL module across
  `work_ledger`/`dispatch_gate`/`digest_loop`, `_string_or_none`-family merging,
  a shared `_positive_int`, and folding config path resolution into `context/resolver`.

## P1 — Structure and Safety

### P1.1 Core boundary: vendor CLI policy moved out of core

`proposer.py` held a three-branch argv table naming `claude`, `codex exec`, and
`cursor-agent --trust --force`. That is vendor policy inside a core module the README
declares tool-name-free.

- New contract `SyncCliProfile` in `core/adapter/profile.py`, beside the existing
  `ToolProfile`: `build_argv(prompt, model) -> argv`. It is a separate contract, not a
  `ToolProfile` subclass, because `ToolProfile` models asynchronous dispatch with a job
  id and a probe, which a foreground one-shot CLI does not have.
- `ClaudeCliProfile`, `CodexExecProfile`, `CursorAgentProfile` moved behind it, with a
  `SYNC_CLI_PROFILES` registry, `resolve_sync_cli_profile()`, and `sync_cli_runtimes()`.
- `build_proposer_argv()` is now a registry lookup plus delegation.
- `SUPPORTED_RUNTIMES` is gone. `require_sync_cli_profile()` is the **single** rejection
  site; `config.py` calls it and re-raises as `AcceptanceConfigError` rather than
  keeping its own list.
- Also removed, though not in the review list: the default `proposer_runtime = "claude"`
  in `AcceptanceConfig` and in `config.py`. A vendor name as a core default would have
  defeated the whole item. The runtime is now required in config, and an unset runtime
  fails with the list of known profiles.

Regression tests: a new profile registered at runtime is usable without touching the
core (`test_a_new_profile_is_usable_without_touching_the_core`), and a structural test
asserts no `claude` / `codex` / `cursor` / `--trust` token appears anywhere in
`core/acceptance/*.py`. Mutation-checked: adding `FALLBACK_RUNTIME = "claude"` back into
`proposer.py` fails that test.

### P1.2 One visibility predicate

Visibility was decided in three places at three depths. `VISIBLE_SPLITS` could be
widened while `Scorecard.visible_failures()` and `visible_manifest()` kept their `TRAIN`
literals — a leak with green tests.

- `is_visible_split(split)` in `casebook.py` is now the only reader of `VISIBLE_SPLITS`.
- `VerificationCase.is_visible`, the new `CaseResult.is_visible`,
  `Scorecard.visible_failures()`, `render_split_markdown()`, and
  `AcceptanceRunLayout.split_dir()` all call it.
- `CaseBook.visible_manifest()` is derived by grouping `visible_cases()` by split
  instead of naming `TRAIN`.

Regression test: `test_widening_the_visible_splits_moves_every_site_at_once` patches
`VISIBLE_SPLITS` to include `HOLDOUT` and asserts that layout routing, the visible
manifest, and the visible failure list all move together. Mutation-checked: restoring
the hardcoded `TRAIN` key in `visible_manifest()` fails it.

### P1.3 No-change gate has one owner

The "candidate declared nothing" rule lived in `read_candidate()`, in the loop's break
condition, and in `decide()`. A proposer that wrote `candidate.json` with an empty
`surfaces` list vanished as `IterationRecord(candidate=None)` — no `decision.json`, no
label, no summary — and `NO_CANDIDATE_CHANGE` was unreachable in any run artifact.

`decide()` now owns it:

- `read_candidate()` returns a real `Candidate` for an empty surface list. It still
  returns `None` only when there is no usable declaration (absent file, invalid JSON,
  `surfaces` not a list).
- The loop breaks on `candidate is None` only. An unchanged candidate is passed to
  `decide()`, gets `NO_CANDIDATE_CHANGE`, is written to `decision.json` with its label
  and summary, is recorded as an `IterationRecord`, and only then ends the run.
- An unchanged candidate is not evaluated: its score is the current score by
  definition, so the loop skips the evaluator call entirely.

Regression test: `test_an_unchanged_candidate_is_rejected_on_the_record_not_dropped`
asserts the verdict, the `decision.json` contents, and that exactly one evaluation
(the baseline) ran.

### P1.4 Restore guard moved into the library

The `--max-iterations > 1 requires --restore-cmd` rule lived only in the CLI argument
parser, so the same combination assembled in Python silently evaluated a dirty tree.

In-place mutation is now a declared property of the proposer/evaluator contract:
`mark_in_place()` / `mutates_workspace_in_place()` in `models.py`. `cli_proposer()` and
`command_evaluator()` both declare it. `run_acceptance_loop()` raises `ValueError` when
`max_iterations > 1`, something declares in-place mutation, and no `on_reject` hook was
given. The CLI now only supplies the hook and turns the library error into exit 2.

Regression tests: the guard fires for an in-place proposer and for `command_evaluator`,
stays silent with a restore hook, and stays silent at `max_iterations == 1`.

## P2 — Efficiency and Duplication

| # | Item | Change |
|---|---|---|
| 5 | Scorecard run twice on a zero-acceptance run | `final_scorecard` reuses `baseline_scorecard` when `current is baseline`. Test asserts one scorecard evaluation and object identity. |
| 6 | CLI `_split` reimplemented `write_manifest` | Both `split` and `run` go through `AcceptanceRunLayout.write_manifest()`, so `split` now emits `manifest.json` too — the drift the review found. `_inspect` uses the new `layout.report_path`; the subcommand is kept because it is the only read path that does not require the caller to know the run layout. |
| 7 | Two near-identical subprocess runners | New `acceptance/process.py` with one `ProcessResult` + `run_process()`. `ProposerResult` is deleted; the proposer seam returns `ProcessResult`. The CLI restore hook runs through `run_process` too and therefore has a timeout (it had none). |
| 8 | Non-atomic artifact writes | `write_json()` and the new `write_text()` write to `.<name>.<pid>.tmp` then `os.replace`, matching `dispatch_gate`'s ticket write. Every artifact goes through them. Test asserts no `.tmp` residue. |
| 9 | `strip() + splitlines()[-1]` copied whole outputs | `ProcessResult.tail()` scans backwards from the end and slices only the last line — no full-buffer copy, and it also skips trailing blank lines. |
| 10 | `history.json` rebuilt by re-reading `decision.json` from disk | Serialized from the loop's in-memory `IterationRecord` list. `layout.read_decisions()` is kept and documented as the cold audit path, with a test. |

## P3 — Dead Code and Surface

Applied: `PRIVATE_SPLITS` deleted; `has_split()` deleted; `strata_for_split(origin=…)`
collapsed into `seed_strata(split)`; the `"final_eval"` alias deleted; verdict
relabeling in `score_results()` now uses `dataclasses.replace`; the boilerplate
`proposal.md` template is no longer pre-written (it was being read back as a candidate's
"summary"); `_with_max_iterations` inlined to `dataclasses.replace`; `command_evaluator`
lost its unwired `clock` knob; layout's manual `SplitScore` serialization is now
`{**score.to_dict(), …}`; `__init__` exports cut from 47 to 36.

Kept, with reasons:

- **`ProposerContext.current`.** `visible_cases` and `visible_failures` are gone — they
  duplicate files already in the workspace. `current` stays: a library proposer needs
  the base ref to derive its candidate ref, and nothing else carries it.
- **`command_evaluator(runner=…)`.** Not unwired — it is the seam that lets a caller run
  cases inside a sandbox or container, and it is now the shared `ProcessRunner` type.
  Only `clock` was removed.
- **`AcceptanceVerdict` and `LoadedConfig` exports.** Nothing imports them today, but
  they are the return types of exported `decide()` and `load_acceptance_config()`;
  callers need to be able to name them.
- **`ProposerResult.detail()`.** Not merely deleted — the whole type is gone, and the
  method survives as `ProcessResult.tail()`, which is now load-bearing (it produces the
  per-case failure detail) and is where P2.9 was fixed.

## r2 Tests

```
PYTHONPATH=src python3 -m pytest tests -q
270 passed, 1 skipped in 1.86s
```

Up from `241 passed, 1 skipped` at `c4203ba`; 29 new tests, no test deleted for
convenience. Two structural guards were mutation-checked (see P1.1 and P1.2).
New file `tests/test_acceptance_process.py` covers the shared runner: clean exit,
non-zero exit, missing binary → 127, timeout → 124, `tail()` semantics, runner
injection.

Also re-verified end to end with a stub CLI on `PATH`: `split` now writes
`manifest.json`, the library guard surfaces through `acceptance-loop run` as exit 2 with
the library's message, a rejected candidate still records `decision.json`, and the run
directory contains no `.tmp` residue. `scripts/redaction-scan.sh` reports 0 findings.

## Files Touched in r2

New: `src/master_runtime/core/acceptance/process.py`,
`tests/test_acceptance_process.py`.

Modified: `core/adapter/profile.py` (CLI profile contract + three reference profiles),
the whole `core/acceptance/` package, `scripts/acceptance-loop`, and the four existing
acceptance test modules. No other repository module was touched.
