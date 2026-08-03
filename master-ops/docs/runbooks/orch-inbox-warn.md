# Orchestration inbox warn hook (`scripts/hooks/orch-inbox-warn.sh`)

Add this block to workspace `.claude/settings.json` under `hooks`:

```json
{
  "UserPromptSubmit": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash {{OPS_REPO}}/scripts/hooks/orch-inbox-warn.sh",
          "statusMessage": "Checking orchestration inbox"
        }
      ]
    }
  ]
}
```

## Behavior

On each turn start, the hook runs `orca orchestration check --peek --json`.
It resolves the Orca CLI the same way onboarding preflight does: `ORCA_CLI_COMMAND` when
set, then `orca-dev` when `ORCA_DEV_REPO_ROOT` is set, then `orca`.
If unacknowledged messages exist, it injects one line with `unacked=<count>` and up to
three subject lines, each truncated to 48 characters.
If the queue is empty, `orca` is missing, output is invalid, or command execution fails,
it prints nothing and exits 0.

## Preconditions and known limits

Precondition: the terminal must be bound to the correct Run.
Measured failure mode: when bound to the wrong Run, the hook can report `unacked=0`,
which confirms a bad assumption instead of correcting it.
Doctrine order: measure run binding first with `orca orchestration run-current` during
boot, then trust this hook output.

Limit: this hook only runs on turns (`UserPromptSubmit`), so it has no effect in a fully
idle session.
If no turns are submitted, no check runs and no warning appears; waking an idle session
remains a human action.

Evidence: three instance validations across two workspaces on 2026-08-03 and 2026-08-04,
provenance joint measurement.
