- `scripts/harness-selfcheck.sh`'s `ctx`/`code-review-graph` `Infra:` checks
  (#317 stage 1) no longer print `OK` for a state nothing actually measured:
  an `orca search --index-status --json` that parses but carries no
  `result.sessionsByAgent`, or a `ctx status` with zero indexed providers,
  now warn `undecided`/`ctx has indexed no providers` instead of reading as
  a clean pass; an empty `code-review-graph` registry warns `no repository
  registered`; a non-finite or non-positive `CODE_REVIEW_GRAPH_STALE_DAYS`
  (`nan`, `inf`, `0`, `-1`) warns naming the variable and falls back to the
  default of 7; a Codex `[mcp_servers.<tool>]` table with `enabled = false`
  is no longer read as reachable, the quoted header form
  `[mcp_servers."<tool>"]` is now accepted, and a Claude local-scope server
  under `projects[<path>].mcpServers` now counts as registered. The 10s
  timeout bound is one variable (`INFRA_TIMEOUT_SECONDS`), and a timeout
  kill reports `timed out after Ns` instead of a generic empty-output
  reason. Refs #317.
