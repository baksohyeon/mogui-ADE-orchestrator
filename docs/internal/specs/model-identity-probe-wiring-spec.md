# Model Identity Probe Wiring Spec

Date: 2026-07-31

## Scope

`scripts/model-identity-probe` is an executable probe for session JSONL files.
Hook registration is outside this contract.

## Probe Contract

Command:

```bash
scripts/model-identity-probe --transcript <session.jsonl> --expect claude-fable-5
```

Arguments:

- `--transcript`: required path to the current session JSONL transcript.
- `--expect`: expected model id. Default: none; without `--expect` or
  `MODEL_IDENTITY_EXPECT`, the probe reports what it measured and asserts
  nothing.
- `--limit`: number of recent assistant turns to inspect. Default: `10`.

Exit behavior:

- `0`: all observed recent assistant model fields match `--expect`, or no
  expected model was supplied and nothing was asserted.
- `2`: no assistant model fields are observed, the transcript is unreadable,
  JSONL is malformed, the limit is invalid, or any observed model differs.

Output:

- Success: `MODEL-PROBE OK <model> n/n`
- Informational result with no assertion: `MODEL-PROBE INFO <observed model distribution> — no expected model supplied (--expect or MODEL_IDENTITY_EXPECT); nothing asserted`
- Drift: `MODEL-PROBE DRIFT: <observed model distribution> — propose a clean-spawn succession and review delegation state for sensitive areas`

## UserPromptSubmit Wiring

The UserPromptSubmit hook should run this probe periodically, with the current
session JSONL path supplied by the host harness. The exact environment variable
or argument that carries the transcript path is host-specific and must be
defined in the hook-registration lane.

Recommended injection policy:

- Inject the probe result before the user prompt when the exit code is `2`.
- Do not block ordinary turns on probe success.
- On drift, instruct the master to propose a fresh-session succession and to
  check whether sensitive work is already delegated to an appropriate worker.

## Non-Goals

This document does not register the hook, name a host-specific transcript
environment variable, or change `.claude/` or shell startup files.
