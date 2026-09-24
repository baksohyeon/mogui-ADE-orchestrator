# Orca CLI Surface Fingerprint Drift Runbook

## What This Checks

`scripts/orca-surface-check.sh` measures the Orca CLI surface this master depends on, comparing current state against a stored baseline. It monitors:

- `appVersion` from `orca status --json`
- `schemaVersion` and `commandCount` from `orca agent-context --json`
- Per-command digests for 24 watched commands (schema shape of flags and usage)

The watched commands are the surfaces called by master scripts and runbooks: `status`, `agent-context`, all `orchestration` subcommands, all `terminal` subcommands, all `worktree` subcommands, and `repo` subcommands.

## Exit Codes

| Exit | Meaning | Action |
|------|---------|--------|
| 0 | Baseline unchanged, all watched commands verified | No action needed. Green. |
| 1 | DRIFT detected in appVersion, commandCount, or watched-command digests | Review and re-verify affected commands before relying on remembered flags. |
| 2 | Could not measure the Orca surface (CLI unavailable or schema unparseable) | Restore Orca access and re-run the check. Does not print the unchanged line. |

## On Drift (Exit 1)

When the check reports DRIFT:

1. Read the output to identify what changed (`appVersion`, `commandCount`, or specific watched commands).
2. For each changed watched command, run `orca <command> --help` and verify the flags and behavior you rely on still work.
3. Update any scripts or runbooks that depended on the old shape.
4. Once verified, refresh the baseline: `scripts/orca-surface-check.sh . --update` (when the `--update` mode is implemented).
5. Record in this runbook that you refreshed the baseline after verification.

**Caution:** Refreshing the baseline without re-verifying the changed commands converts a real warning into a silent pass. The check can only catch drift if the baseline is kept in sync with verified reality.

## On Measurement Failure (Exit 2)

If the check exits 2:

1. Verify Orca is running: `orca status --json` should return JSON.
2. Verify `orca agent-context --json` is available (should return schema with `schemaVersion`, `commandCount`, `commands`).
3. Re-run the check: `scripts/orca-surface-check.sh .`

The check does not print the unchanged line on exit 2, so a green-looking pass during a measurement failure is impossible.

## Integration with Dispatch and Runbooks

This check is run at instance-harness boot to detect Orca upgrades or mid-session surface changes before they break a script mid-call. If the check reports drift, the master should re-verify the affected commands before dispatching new work that depends on them.

## Baseline Refresh Log

This section records when the baseline was refreshed after verification:

- 2026-08-03: Initial baseline created and verified (appVersion 1.4.164, schema v1, 24 watched commands).
