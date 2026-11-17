- Required infra (#317 stage 2) follow-ups (#328), from the final review on
  PR #326 and a seat postmortem the day after it merged. `harness-selfcheck.sh`
  now judges MCP registration against the host actually running the check
  (`MASTER_HOST_RUNTIME`, resolved the same way `scripts/dispatch` resolves its
  own master host runtime): a Claude-hosted seat no longer reads a Codex-only
  `code-review-graph`/`ctx` registration as `OK`, an unconfigured host warns
  naming itself unmeasurable, and the symmetric Codex-hosted cases are
  covered too. A new `Infra: ctx-upgrade` line warns when `ctx upgrade
  status --format json` reports `error`, or the installed version is
  numerically behind the latest version it last recorded — the actual root
  cause of the seat postmortem that opened #317, a `ctx` stuck on an old
  release whose failure modes were already closed upstream; it reads
  `status`, never `check`, so this bounded check cannot itself trigger a
  network call or an upgrade. `code-review-graph`'s own `Runs:` timeout now
  names a cold `uv` cache as the likely cause instead of a bare "timed out",
  and the runbook documents that first-run download as a real, if narrow,
  side effect of a check otherwise read-only.

  The `.mcp.json` merge onboarding Step 7 used to carry as an inline python3
  snippet is now `scripts/install-mcp-config`, idempotent and refusing a
  malformed or non-object destination; both `08-settings-and-skills.md` and
  `upgrade.md` call it, so a re-stamp's walk-through can actually write
  `.mcp.json` instead of leaving it missing on a seat that never ran that
  subsection live. `test-dispatch-mcp-install.sh`'s doc-snippet extraction is
  replaced by `test-install-mcp-config.sh`, run directly against the script.
  Two tests that separately re-parsed the pinned `code-review-graph` entry by
  hand now read it through `install-mcp-config --print-entry` instead
  (#328 test hygiene). `test-dispatch-runtime.sh`'s `rm -rf "$work"` cleanup
  traps are guarded with `"${work:?}"`.
