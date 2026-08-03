# §3. Execution Principles

Governs the default execution path and recovery procedures. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

The default execution path is:

```text
Proposal -> Approval -> Execution
```

If the approved scope is unclear, ask or stop. Do not fill uncertainty with guesses.

When resuming existing work, recover before creating new material.

Recovery order:

1. Git SSOT
2. approved architecture and specs
3. approved previous artifacts
4. other memory systems

Always run:

```text
Recover -> Verify -> Patch -> Promote
```

Do not trust delegated output. Before acceptance, independently verify with code, logs, execution, tests, deterministic probes, or authoritative documents. Worker self-report is not evidence.

Do not expand scope. If a request belongs outside the active role, ask whether it should become a separate track.
