Delegation is accepted only when a worker contract passes the gate, the worker job is registered, and the master independently verifies the result.

# Delegation And Review

The master coordinates work, but it does not need to perform every implementation or review itself. Delegation is useful only if it stays accountable. This repository uses a contract gate, job registration, evidence requirements, and independent acceptance.

## Worker Dispatch Gate

The supervised flow is:

```text
check -> dispatch -> register
```

`check` reads the worker contract and records a decision in the dispatch ledger. `dispatch` is the launch itself: the master starts the worker on the runtime the contract names, and the harness does not wrap that step; the typed adapter path that once did was removed. `register` is valid only after a probe proves that the worker job id appears in an expected artifact.

The gate exists because policy without wiring is easy to bypass. A worker launch path once ran outside the expected warning path; the absence of a warning was incorrectly treated as permission. The fix was to treat every worker launch surface as part of the dispatch boundary and to record missing or unverifiable dispatches as violations rather than retroactively accepting them.

Example check:

```bash
scripts/dispatch-gate \
  --ledger ./.dispatch-ledger.jsonl \
  check \
  --runtime codex \
  --contract ./contracts/job.md \
  --agents 1 \
  --est-chars 2000
```

Example registration:

```bash
scripts/dispatch-gate \
  --ledger ./.dispatch-ledger.jsonl \
  register \
  --job-id job-123 \
  --probe-cmd 'grep job-123 ./worker.log' \
  --runtime codex \
  --contract-sha abc123abc123
```

> Note: The public documentation does not list local routing or warning rules. Treat the gate as a recorded permission boundary, and inspect the local CLI help for current flags.

## Worker Contract Discipline

A worker contract should be narrow enough that another session can execute it without guessing.

Write the contract around observable facts:

- target repository and checkout
- allowed work surface
- acceptance criteria
- required evidence
- commit, push, and branch rules
- known exclusions and forbidden edits

Worker self-report is not evidence. Evidence should be something the master can inspect: diffs, tests, logs, generated files, deterministic probes, or authoritative documents.

If a worker interprets the contract differently from the master, the answer is not to accept a partial result. The master should correct the lease, record the revision reason, redispatch or request changes, and keep acceptance separate from worker completion.

## Commit Rules

Commit authority belongs in the contract. A worker should not infer whether it may commit, push, deploy, or edit shared files.

Useful contract language is concrete:

```text
Local commit allowed. Push forbidden. Commit only files changed for this job.
Evidence file stays uncommitted.
```

If commit authority is absent, the conservative behavior is to leave changes uncommitted and report the exact state.

## Review Lenses

For non-trivial work, the operating guide recommends a three-lens review:

```text
general correctness
regression disproof
contract and scope
```

The point is not ceremony. The point is to separate failure modes. One reviewer asks whether the code works. Another tries to disprove that behavior stayed stable. Another checks whether the worker obeyed the contract.

The master should use the majority verdict, but a serious minority finding must be addressed or explicitly rejected with evidence.

This is a lens split, not a popularity contest. A three-vote review is useful because one path can focus on whether the result works, another on disproving regression, and another on contract compliance. If the contract or regression lens finds a blocking issue, the master should handle it before acceptance even when the other reviews are positive.

## Acceptance Gate

Acceptance is a master decision, not a worker decision.

Before acceptance, the master independently verifies the worker artifact against the contract. A narrow documentation task may need link checks and redaction scans. A code task may need targeted tests, broad tests, and direct source inspection. A cross-repository task may need evidence from each repository.

The acceptance gate is deliberately skeptical of self-report. "Done" means only that the worker claims it is done. Acceptance starts when the master can connect the worker artifact to the lease, inspect the changed surface, rerun or verify the required checks, and name any gap that remains.

The acceptance report should state what passed, what was not run, and which risks remain. If a result cannot be verified, it is not accepted yet.

Read next: [Master Lifecycle](master-lifecycle.md) or [Reference](reference.md).
