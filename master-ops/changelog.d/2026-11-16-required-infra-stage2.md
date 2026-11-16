- Required infra (#317 stage 2) ships wired by default instead of just
  measured. `scripts/dispatch` launches every worker with the
  `code-review-graph` server pinned once in `templates/mcp-servers.json`:
  Claude workers get it through `--mcp-config`, Codex workers through an
  inline `-c mcp_servers.<name>={...}` TOML override; neither persists past
  the one launch. A `required-infra` standing-rule block (naming orca,
  beads, `ctx`, and code-review-graph) folds into every dispatched brief the
  same way `mail-before-done` does. On the master side, onboarding Step 7
  (`08-settings-and-skills.md`) now merges the same pinned entry into the
  workspace-root `.mcp.json`, keeping other servers already there (an
  existing `code-review-graph` entry is replaced with the pinned one) and
  refusing to touch a malformed file; merges `enabledMcpjsonServers` into the
  master's settings so that project-scope entry is actually reachable
  (the gap a peer seat hit via `disabledMcpjsonServers`); and registers
  every confirmed repository into code-review-graph's multi-repo registry
  so `cross_repo_search_tool`/`list_repos_tool` cover the workspace.
  Measured against `code-review-graph@2.4.0`: `serve` needs no `--repo`
  flag even from a non-repository directory, since every exposed tool takes
  an explicit `repo_root` argument instead. `upgrade.md` points existing
  seats at the same subsection. Refs #317.
