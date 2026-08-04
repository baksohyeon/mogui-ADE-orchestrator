# §5. Dispatch Gate

Governs the supervised dispatch process and gate enforcement. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Supervised dispatch follows:

```text
check -> dispatch -> register
```

Use the workspace's approved dispatch gate command and ledger. The template form is:

```bash
G={{RUNTIME_ROOT}}/scripts/dispatch-gate
L=~/.mogui/dispatch-ledger.jsonl

"$G" --ledger "$L" check --runtime <runtime> --model <model-id> --contract <contract-file> --agents <n> --est-chars <n> --completion-channel orchestration
<supervised dispatch command>
"$G" --ledger "$L" register --job-id <job-id> --probe-cmd "<command proving the job-id appears in an artifact>" --orchestration-task <task-id> --declared-model <model-id> --model-probe-cmd "<command printing the worker's actual model id>"
```

Tier policy file selection: environment override named `DISPATCH_TIER_POLICY`, then instance `config/model-tier-policy.json` (written at onboarding after agent-inventory consent), then template `master-ops/model-tier-policy.json`.

The gate enforces that policy file. A version 2 policy gates on tier multiplied by fan-out rather than on identity, because the incident it exists for was a top tier spread across ten workers: each tier carries a cap on agents dispatched inside a window, an unlisted model falls in the `unknown` tier and is capped there rather than denied, and exceeding a cap requires `--tier-override "<reason>"`. The window counts accumulation, not concurrency, so ten sequential single-agent dispatches reach the same cap as one fan-out of ten; an override passes one request without refunding what the window already counted. Version 1 policies keep their identity-based behaviour unchanged. Model identifiers match casefolded, so a tier spelled in another case is the same tier. Each decision records the policy path, its `sha256`, and the tier that decided, because that path is caller-supplied; `dispatch-gate report` lists every policy a span was judged against and every tier it spent agents in, including `unknown`, and more than one policy row means the span was not judged against one policy.

The gate writes its verdict as JSON on stdout and human diagnostics on stderr. Do not merge them: `2>&1` piped into a JSON parser fails, and the failure reads like malformed output rather than like two streams. Use `2>/dev/null` for machine use, and read stderr separately when a person needs the reason.

`register` compares the model the dispatch declared with the model the worker actually ran. Declare the measurement per dispatch with `--model-probe-cmd`, because every runtime reports differently and this gate is agent-neutral; the command must read an artifact the agent itself produced, such as its session transcript, for which `{{RUNTIME_ROOT}}/scripts/model-identity-probe` is the reference implementation. Do not scrape a TUI status line: that measures what a renderer drew, and authenticating a model against it leaves a verification stamp with no verification behind it.

The verdict is graded. No declared model, or a probe that returns nothing, warns as `MODEL_UNVERIFIED` or `MODEL_PROBE_FAILED` and still registers, because a runtime with no way to report its model would otherwise be unable to dispatch at all and the check would simply be turned off. A measured model in a tier the policy watches more closely than the declared one denies with `MODEL_TIER_ESCALATION`. Running looser than declared warns as `MODEL_MISMATCH`. Every case records `model_declared`, `model_measured`, and `model_verified` in the ledger, so an unverified registration is distinguishable from a verified one instead of being assumed.

Before attaching a Codex worker, run `scripts/codex-worker-pretrust <worktree-path>` and confirm the summary is not `skipped`, so startup does not block on the trust prompt.

Before attaching a Cursor worker, run `scripts/cursor-worker-pretrust <worktree-path>` and require exit status 0 with a summary that reports `added`, `updated`, or `already trusted` (not `skipped`), so startup does not block on the trust prompt.

Measured on `cursor-agent 2026.07.23-e383d2b`: a fresh workspace with project-local `.cursor/hooks.json` started without any second trust prompt after pre-trust, hooks executed, and Cursor state showed no persisted `hooks.state` or `trusted_hash` key.

`register` without a prior successful `check` is invalid. Register only after the artifact exists, and before the final evidence report. Promote dispatch acceptance and verification results into the issue tracker.

The supervised dispatch command is vendor-neutral Orca orchestration: bind a Run, create the Task with `orca orchestration task-create`, attach the worker with `orca orchestration worker-start` (or `dispatch --inject`), then wait event-driven with `check --wait --types worker_done,escalation,question`. A coordinator clears each delivery with the acknowledgement flag before waiting again, and cross-master traffic addresses a standing Run rather than a transient handle. Raw terminal polling and vendor-direct CLIs bypass task and Dispatch provenance and `worker_done` authority and are non-compliant dispatch paths. Vendor plugins are allowed for non-dispatch uses such as second-opinion review. Record accidental work outside orchestration plainly as non-orchestrated; never relabel it orchestrated. (charter rule since template v5)

If the workspace uses a warning hook for direct worker invocations, it should warn on missing gate evidence and log suppressions. This document specifies the behavior only; hook implementation and deny lists belong to the security or operations owner.
