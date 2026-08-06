# Spawn-Test Harness

This document describes the sandbox spawn-test harness: an end-to-end verification that the onboarding installer produces a working master-ops layer in a fresh clone.

## Purpose

The onboarding installer has never been tested end-to-end with machine verification. This harness automates the full flow for each runtime and produces evidence:

- a. **Machine Assertion A**: Spawned agent generated an operations repository with `docs/MASTER-OPERATIONS.md`
- b. **Machine Assertion B**: At least one hook fire-log entry is written from the sandbox during onboarding
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
- `SPAWN_TEST_COORDINATOR_TERMINAL` or `SPAWN_TEST_COORDINATOR_RUN` set so the
  spawned agent can send the round-trip message to the coordinator

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
3. Record source commit as the `source-commit` evidence entry
4. Setup sandbox-local fire-log: `../.fire-log/spawn-test-<runtime>.jsonl` relative to the sandbox clone
```

### Installer Run

```
1. `orca terminal create --worktree active --command 'cd <sandbox-clone> && exec <runtime>'`
2. Feed INSTALL-PROMPT.txt from sandbox ADE repo
3. Agent performs onboarding in sandbox isolation
```

### Machine Assertions

After installer completes:

**A. Structure Check**
- Verify the spawned agent generated an operations repository with `docs/MASTER-OPERATIONS.md`.
- Output: PASS or FAIL in the report.

**B. Hook Fires**
- Check the hook fire-log line count before and after the spawned agent runs.
- At least one new hook fire-log entry with `cwd` under the sandbox must appear during setup.
- Output: fire-log path plus before/after counts in report.

**C. Round-Trip**
- Check for orca orchestration message from spawned master back to coordinator
- Message ID recorded as the `msg-id-<runtime>` results entry
- A missing round-trip fails Assertion C

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
5. **Kept Sandboxes**: Failed-run sandbox identifiers for investigation
6. **Details**: Full output per runtime

### Example Summary

```markdown
| Runtime | Status | Assertions | Wall Time | Message ID | Sandbox | Fire Log |
|---------|--------|-----------|-----------|------------|---------|----------|
| claude  | PASS | 3/3     | 127s      | msg_abc (spawn-test-alive-claude-123) | - | spawn-test-claude.jsonl 0->2 |
| codex   | PASS | 3/3     | 95s       | msg_def (spawn-test-alive-codex-123) | - | spawn-test-codex.jsonl 0->1 |
| agy     | blocked | - | - | - | - | - |
| cursor  | blocked | - | - | - | - | - |
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
- Inspect the generated operations repository candidate for `docs/MASTER-OPERATIONS.md`.
- Check the sandbox-local hook fire-log path and before/after counts from the report.
- Exit code: 1

### Grok / Blocked Runtimes
- **Grok**: Best-effort; missing round-trip evidence is a failed assertion
- **Agy/Cursor**: Blocked due to quota; recorded with reset time

## Fire-Log Instrumentation

The harness creates a sandbox-local hook fire-log and passes it to the spawned
runtime:

```bash
export MOGUI_HOOK_FIRE_LOG="$TMPDIR/mogui-spawn-test/<runtime>-<timestamp>/.fire-log/spawn-test-<runtime>.jsonl"
```

The shipped hooks honor `MOGUI_HOOK_FIRE_LOG`; outside spawn-test, the default
remains `~/.mogui/hook-fire-log.jsonl`.

### Fire-Log Format

```json
{"ts":1722728400,"hook":"bash-poll-warn","event":"PreToolUse(Bash)","cwd":"/tmp/mogui-spawn-test/claude-123/mogui-ADE-orchestrator","runtime_hint":"claude","session_kind":"unknown"}
```

Hook names, trigger times, and hook output are recorded here.

## Debugging Failed Runs

### Check Harness Exit Code
```bash
SPAWN_TEST_RUNTIMES=claude ./scripts/spawn-test
echo $?  # 0 = pass, 1 = fail
```

### Re-Enter Failed Sandbox
```bash
cd "$TMPDIR/mogui-spawn-test/claude-<timestamp>/mogui-ADE-orchestrator"
find .. -path '*/sandbox-ops/docs/MASTER-OPERATIONS.md' -print
```

### Check Round-Trip Message
```bash
# In coordinator terminal:
orca orchestration check | grep spawn-test-claude

# In kept sandbox (if async):
cat ../.fire-log/spawn-test-claude.jsonl | tail -20
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

- **Onboarding Flow**: `{{RUNTIME_ROOT}}` product skeleton `ONBOARDING.md` (template-side router; not installed into ops)
- **Structure Check**: generated operations repository with `docs/MASTER-OPERATIONS.md`
- **Master Operations**: `<sandbox>/sandbox-ops/docs/MASTER-OPERATIONS.md`
- **Worker Contract**: `contracts/2026-08-04-spawn-test-harness.md`

---

**Last Updated**: 2026-08-04
**Harness Version**: 1.0
**Template Version**: v0.4.4
