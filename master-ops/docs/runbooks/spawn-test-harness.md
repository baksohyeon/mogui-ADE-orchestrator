# Spawn-Test Harness

This document describes the sandbox spawn-test harness: an end-to-end verification that the onboarding installer produces a working master-ops layer in a fresh clone.

## Purpose

The onboarding installer has never been tested end-to-end with machine verification. This harness automates the full flow for each runtime and produces evidence:

- a. **Machine Assertion A**: Self-check passes in sandbox master-ops
- b. **Machine Assertion B**: At least one hook fires during onboarding
- c. **Machine Assertion C**: Round-trip - spawned master sends orca orchestration message back to coordinator

See AHE E11 (second-workspace transplant) - this is the standing instrument.

## Harness Location

```
scripts/spawn-test
```

## Usage

```bash
./scripts/spawn-test [SCENARIO]
```

### Required Prerequisites

- `orca` in PATH and running (checked at startup)
- Local clone of `mogui-ADE-orchestrator` at `{{WORKSPACE_ROOT}}`
- Writable temp directory (uses `$TMPDIR` or `/tmp`)

### Runtime Selection

The harness tests a matrix of runtimes:

| Runtime | Required | Status |
|---------|----------|--------|
| `claude` | **MUST PASS** | Primary floor |
| `codex` | **MUST PASS** | Fallback floor |
| `grok` | Best-effort | Experimental |
| `agy` | Blocked | Provider quota constraint in the authoring measurement |
| `cursor` | Blocked | Provider quota constraint in the authoring measurement |

## Sandbox Lifecycle

### Creation

```
1. Create temp directory under `$TMPDIR` or `/tmp`
2. Clone mogui-ADE-orchestrator into sandbox (local copy)
3. Record source commit: CLONE_SOURCE_COMMIT file
4. Setup sandbox-local fire-log: .fire-log/spawn-test-<runtime>.log
```

### Installer Run

```
1. orca terminal create --worktree <sandbox> --command <runtime>
2. Feed INSTALL-PROMPT.txt from sandbox ADE repo
3. Agent performs onboarding in sandbox isolation
```

### Machine Assertions

After installer completes:

**A. Self-Check**
- Run `mogui-ADE-orchestrator/master-ops/scripts/harness-selfcheck.sh` inside sandbox
- Verifies: skills discovery, hooks wiring, tracker resolution
- Output: command + stdout/stderr in report

**B. Hook Fires**
- Check sandbox-local fire-log for entries (`.fire-log/spawn-test-<runtime>.log`)
- At least one hook must fire during setup
- Output: fire-count + first 5 entries in report

**C. Round-Trip**
- Check for orca orchestration message from spawned master back to coordinator
- Message ID recorded in sandbox (ROUND_TRIP_MSG file)
- May arrive async; pending status is acceptable on first run

### Teardown

- **On Full Pass**: Sandbox deleted (evidence not needed if assertions pass)
- **On Failure**: Sandbox preserved with path recorded in report
  - Investigator can re-enter and debug: `cd <sandbox>/mogui-ADE-orchestrator`

## Report Output

Generated at: `docs/reports/spawn-test-<YYYY-MM-DD>.md`

### Report Structure

1. **Summary Table**: Per-runtime matrix with status, assertions, wall time
2. **Pass Summary**: Must-pass runtimes status
3. **Floor Status**: "FLOOR MET" vs "FLOOR NOT MET"
4. **Round-Trip Messages**: Message IDs from successful runs
5. **Kept Sandboxes**: Paths to failed-run sandboxes for investigation
6. **Details**: Full output per runtime

### Example Summary

```markdown
| Runtime | Status | Assertions | Wall Time | Notes |
|---------|--------|-----------|-----------|-------|
| claude  | PASS | A/B/C     | 127s      | Sandbox cleaned |
| codex   | PASS | A/B/C     | 95s       | Sandbox cleaned |
| grok    | PENDING | A/B      | 340s      | Waiting for msg |
| agy     | blocked: provider quota | - | - | authoring-instance measurement |
| cursor  | blocked: provider quota | - | - | authoring-instance measurement |
```

## Interpreting Results

### Floor Met
Both `claude` and `codex` return **PASS** for all three assertions.
- Sandboxes are cleaned up
- No manual intervention needed
- Exit code: 0

### Floor Not Met
One or both of `claude`, `codex` failed.
- Sandboxes preserved
- Investigator path: `cd <sandbox>/mogui-ADE-orchestrator`
- Run harness-selfcheck manually: `bash master-ops/scripts/harness-selfcheck.sh`
- Check fire-log: `cat .fire-log/spawn-test-<runtime>.log`
- Exit code: 1

### Grok / Blocked Runtimes
- **Grok**: Best-effort; may return PENDING if round-trip async
- **Agy/Cursor**: Blocked due to quota; recorded with reset time

## Fire-Log Instrumentation

The harness wires each sandbox to a sandbox-local fire-log:

```bash
export MOGUI_FIRE_LOG="/sandbox/.fire-log/spawn-test-<runtime>.log"
```

This keeps sandbox instance logs separate from the coordinator's fire-log.

### Fire-Log Format

```
[HH:MM:SS] <event>: <details>
[HH:MM:SS] <event>: <details>
```

Hook names, trigger times, and hook output are recorded here.

## Debugging Failed Runs

### Check Harness Exit Code
```bash
./scripts/spawn-test --runtime claude
echo $?  # 0 = pass, 1 = fail
```

### Re-Enter Failed Sandbox
```bash
cd "$TMPDIR/mogui-spawn-test/claude-<timestamp>/mogui-ADE-orchestrator"
bash master-ops/scripts/harness-selfcheck.sh
cat .fire-log/spawn-test-claude.log
```

### Check Round-Trip Message
```bash
# In coordinator terminal:
orca orchestration check | grep spawn-test-claude

# In sandbox terminal (if async):
cat .fire-log/spawn-test-claude.log | tail -20
```

## Constraints and Prohibitions

Per the worker contract:

- Modify `scripts/spawn-test` and this runbook as needed.
- Do not modify the product repository (`mogui-ADE-orchestrator`).
- Do not run onboarding against the real workspace.
- Do not push ops repo unless the owner explicitly asks.
- Do not delete a failed sandbox.
- Do not merge while tests are incomplete.

## First Execution

The initial run tests **claude and codex** (both must reach PASS). Grok is attempted as best-effort. Agy and cursor are recorded as blocked when provider quota prevents execution.

Report is committed with evidence appended to `docs/reports/spawn-test-<date>.md`.

## Related Documentation

- **Onboarding Flow**: `{{RUNTIME_ROOT}}/master-ops/ONBOARDING.md`
- **Self-Check**: `{{RUNTIME_ROOT}}/master-ops/scripts/harness-selfcheck.sh`
- **Master Operations**: `docs/MASTER-OPERATIONS.md`
- **Worker Contract**: `contracts/2026-08-04-spawn-test-harness.md`

---

**Last Updated**: 2026-08-04
**Harness Version**: 1.0
**Template Version**: v0.4.1
