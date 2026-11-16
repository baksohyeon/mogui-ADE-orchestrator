- `scripts/harness-selfcheck.sh` adds one warning-only `Infra:` line each for
  `ctx` and `code-review-graph`: whether the CLI runs, whether it is
  reachable as an MCP server for this host session (Claude user-scope
  `mcpServers`, or a project `.mcp.json` entry gated by
  `enableAllProjectMcpServers`/`enabledMcpjsonServers` and rejected by a
  `disabledMcpjsonServers` entry in any settings file; Codex's
  `config.toml`), and whether it is fresh and covering (ctx: every provider
  Orca's own agent-session index reports sessions for among `claude` and
  `codex`; code-review-graph: every repo in its multi-repo registry has a
  graph no older than `CODE_REVIEW_GRAPH_STALE_DAYS`, default 7 days). These
  lines never change the script's exit code; Orca and beads keep their
  existing pass/fail checks unchanged. Refs #317.
