# Worker Host Diversity

The master and a worker on the same host runtime draw from the same quota pool.
That costs the coordinator the budget it needs to keep dispatching, reviewing,
and recovering work. The dispatch wrapper therefore makes the runtime choice
visible at the point of issue.

`scripts/dispatch` accepts `--runtime <name>`. If omitted, it chooses an
installed runtime that is not the configured master host. When the requested
runtime matches the master host, the wrapper prints a warning and continues.
This is advisory by design: the master decides per dispatch, and the record
exists so the trend is visible rather than to police any single call.

Codex workers use `--approve-for-me` with `sandbox_workspace_write.network_access=true` by default after an install has been refreshed from this template. Existing installs must run the [template Upgrade flow](../../onboarding/upgrade.md) first, and the Codex CLI must support `--approve-for-me` (measured on codex-cli 0.167.0); a CLI without it fails at launch, so upgrade `codex` before dispatching. Setting `codex_bypass_approvals_and_sandbox: true` in the instance runtime config switches to `--dangerously-bypass-approvals-and-sandbox`, which disables the sandbox. An out-of-worktree escalation under `--approve-for-me` is decided by the Codex automatic reviewer, not by a human, and whether it ever approves one is unmeasured; one observation on 2026-11-12 recorded 7 `~/.mogui` writes denied with none escalated.

Use `--same-host-reason "<text>"` when the same-host choice is deliberate. That
prints a quieter acknowledgement instead of the warning and records the reason.

The audit trail is append-only in `~/.mogui/dispatch-ledger.jsonl`. Count
collisions with:

```bash
python3 - <<'PY'
import json
from pathlib import Path

ledger = Path.home() / ".mogui" / "dispatch-ledger.jsonl"
total = collisions = 0
for line in ledger.read_text(encoding="utf-8").splitlines():
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        continue
    if entry.get("kind") != "host_diversity_audit":
        continue
    total += 1
    collisions += int(bool(entry.get("same_host")))
print(f"{collisions}/{total} audited dispatches used the master host")
PY
```

Limit: this guard measures the runtime the caller declares, not the account or
quota pool behind it. Two different runtimes on the same underlying account
would still collide, and this guard would not see it.
