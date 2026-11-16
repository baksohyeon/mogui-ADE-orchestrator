- PR #326 round 2 (#317): `scripts/harness-selfcheck.sh`'s `code-review-graph`
  `Infra:` "Runs" check now probes the pinned launcher read from
  `templates/mcp-servers.json` (`uvx code-review-graph@<pin> --version`,
  the launcher `command` plus `args[0]`) instead of a bare `code-review-graph`
  binary on `PATH`, which no session ever calls directly and which warned
  forever on a host with `uvx` but no global `code-review-graph` shim — the
  common, correctly-wired case. A missing or unreadable servers file, or an
  entry with no `command`/`args`, is named by that reading; an absent
  launcher reports `launcher '<command>' absent from PATH`. `scripts/dispatch`
  now emits `--mcp-config` for a Claude worker only when that file is
  readable, warning once on stderr naming the path otherwise and continuing
  the launch, matching the Codex path's existing silent-skip for the same
  gap. Tests read the pin and the Codex `-c` string from
  `templates/mcp-servers.json` instead of a second hand-typed literal.
  Refs #317.
