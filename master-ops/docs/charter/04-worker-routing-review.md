# §4. Worker Routing And Review

Governs worker dispatch, model selection, and review practices. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

The master is agent-host neutral. Neutrality covers artifact formats and agent swappability only; it is never an excuse to avoid required infrastructure. For dispatch and terminal or session operations, prefer Orca's stable IDs (handles, worktrees, RPC) over raw OS utilities. The process-cwd and session-artifact checks in §6 are placement evidence, not dispatch mechanisms. (charter rule since template v5) Measure the configured model flag and the actual session model field at boot. Default master model identifier: `{{MODEL_ID}}`.

A boot measurement is a snapshot of one moment, not a property of the session. Re-measure after resume, after continue, after compaction, at succession audit, and at session close. A probe that samples recent turns answers what the model is now; it cannot see a change that happened earlier and then settled. For that, audit the whole transcript with `{{RUNTIME_ROOT}}/scripts/model-drift-audit`, which exits 0 for no transition, 1 for a transition or an expectation mismatch, and 2 when it cannot decide. Do not read 2 as a pass.

Recommended worker lanes:

- Heavy implementation: an implementation-capable worker with isolated workspace state and explicit acceptance criteria
- Review, diagnosis, small fixes, and chores: a fast reviewer or maintenance worker
- External-network research: a worker lane whose environment explicitly permits that access
- Local code work: a worker lane bound to the relevant repository checkout
- Sensitive areas such as auth, permissions, secrets, credentials, production data, and incident material: a dedicated security or operations session

## Workspace descriptor prohibitions (product main and force-push)

Which repositories belong to this workspace, and which actions are hard-blocked on each, live in the instance workspace descriptor written at onboarding (`{{RUNTIME_ROOT}}/config/workspace-descriptor.json`; template ships only `config/workspace-descriptor.example.json`). Do not keep a parallel hardcoded product-path list in this charter.

Before a direct commit to a repository default branch, a force-push, or any other action named under a repository's `prohibited` list, measure the descriptor:

```bash
"{{RUNTIME_ROOT}}/scripts/workspace-descriptor-check" \
  --path <repository-path> \
  --action direct-main-commit
```

Exit `1` means prohibited; exit `0` means the descriptor does not list that action for the matched repo; exit `2` means unconfigured or invalid (fail closed: do not invent permission). The same check accepts `--action force-push`. Resolution order matches instance runtime config: environment override (`WORKSPACE_DESCRIPTOR` or `MOGUI_WORKSPACE_DESCRIPTOR`) → instance file → honest unconfigured. Product repositories default to prohibiting `direct-main-commit` and `force-push`; ops repositories default to prohibiting `force-push`. Owner-confirmed edits to the instance file win over these defaults.

The installation-specific worker tier mapping lives in the instance file `{{RUNTIME_ROOT}}/config/model-tier-policy.json` when onboarding wrote one (after agent-inventory consent), else the template `model-tier-policy.json`. It groups installed model identifiers into tiers; use the lowest sufficient tier for each worker lane. Measure what this host actually offers before filling it in: never guess a model id, and a model the file has never heard of is not blocked — it resolves to the `unknown` tier and uses that tier's stated cap when present, otherwise uncapped (same as any tier with no `fanout_caps` entry). An unlisted id must not be punished as if it were top tier.

Owner directive 2026-08-05 removed the top-tier fanout cap; `scripts/dispatch` refuses a top-tier model unless the supervised caller supplies the owner-approved reason as `--top-approved "<owner answer>"`.

Gate selection order: explicit `--tier-policy` CLI flag, then environment override, then instance `config/model-tier-policy.json`, then template `model-tier-policy.json`.

Worker contract clause library: `docs/runbooks/contract-conventions.md`.

## Worker Launch Approval Posture

For operations-repository work, dispatch workers into an isolated `git worktree`. The master chooses the worktree at dispatch time, and successor spawn separately fail-closes on `expected_placement` mismatch (`SPAWN_PLACEMENT_MISMATCH = 26`). The worker's first-action placement verdict is not dispatch evidence; it is a self-stop condition for a worker that finds itself in the wrong place. Require `in_expected_worktree`, `is_master_checkout`, and `branch`, with no absolute path in the report, and stop the worker immediately if `is_master_checkout` is `yes`. On 2026-08-03, ambiguous placement caused four contaminations of the master's own tree in one day. Placement contracts still name exact paths downward to the worker; reports send verdicts upward.

Workers launched into isolated worktrees must start with the agent's non-interactive approval flag, or the measured pre-trust posture below, so allowlist or trust prompts cannot block them mid-task. Pre-trust holds when the summary reports the worktree added, updated, or already trusted; the skip path (`Summary: skipped`) leaves the trust prompt in place and says so on stdout, so read the summary line before relying on it. At every dispatch, the master MEASURES the installed CLI's `--help` output and uses only flags present there; it never guesses flags from memory.

Coverage registry. A launch flag or pre-trust step covers what was measured and nothing more, so each runtime's row records what its posture covers, what it was measured not to cover, and whether a write-root guard holds, each with the date and the condition of the measurement. A later measurement adds a dated fact to a cell and never turns a column back into a boolean. A runtime with no measurement reads `coverage unmeasured`. The rows match the runtimes `runtime_command()` in `scripts/dispatch` names: claude, codex, cursor, grok, gemini, opencode, agy. Any other runtime name is launched as a bare command of that name with no measured posture, and has no row until it is measured.

| Runtime | Launch posture (flag or pre-trust step) | Covers | Measured not covered | Write-root guard |
| --- | --- | --- | --- | --- |
| claude | `--dangerously-skip-permissions` (measured from `--help` 2026-08-02), plus `scripts/claude-worker-pretrust <worktree>` run by `dispatch` | tool permission prompts | folder-trust dialog ("Quick safety check"), 2026-10-02 on a fresh worktree, flag set; cleared by `claude-worker-pretrust`. Destructive-operation prompt ("Dangerous rm operation on statically-unresolvable target"), 2026-08-06 and again on a claude worker pane 2026-11-09, flag set. Write root: an opaque interpreter body (`python3 -c "open(..., 'w')"`, a heredoc fed to an interpreter) writing outside the worktree passes the guard unless the parse sees a redirect or `cd` in it: measured 2026-11-10 in worker mode, a `python3 -c` body and a `python3 <<'EOF'` heredoc body each opening a file outside the root for writing were both admitted. Write root on a reused pane (`dispatch --terminal`): not enforced, 2026-11-10 on claude 2.1.319, a pane launched with a worker settings file kept refusing writes against its launch-time root after that file was repointed at a new root, so a running claude cannot take the current task's root | covers only the shapes `test-product-path-guard.sh` tests, since 2026-11-09, on a pane `dispatch` creates: `dispatch` launches each claude worker with `--settings <per-task file>` running `product-path-guard.sh` in worker mode, the worktree as the only write root. Live run 2026-11-09 (claude 2.1.319, `-p`, flag set): a Write-tool write and a Bash redirection outside the worktree were both blocked and the hook fire log carried two `block` records |
| codex | `--approve-for-me` (measured from `codex --help` 2026-11-11) by default, plus `scripts/codex-worker-pretrust <worktree-path>` with the account-wide hooks trust posture retained (2026-08-02); `-c sandbox_workspace_write.network_access=true` stays on the default path. `--dangerously-bypass-approvals-and-sandbox` remains only when `codex_bypass_approvals_and_sandbox` is true (opt-in since 2026-10-17) | first-visit worktree trust prompt, when the summary reports added, updated, or already trusted. 2026-11-12: approval requests are auto-reviewed under `--approve-for-me`; measurement is prompts per dispatch, baseline 29 and 15 on 2026-11-11, target 0 | hook-trust modal ("Hooks need review") when the hook set changes: card note 2026-08-06; 2026-10-24 on codex-cli 0.164.0 with one unreviewed hook in a scratch `CODEX_HOME`, the modal showed with and without the bypass flag; `dispatch` answers it under dispatch authority after vetting the hooks (2026-10-01) | covered by the workspace-write sandbox for the touch shape measured 2026-11-09 on codex-cli 0.167.0; other shapes unmeasured. Reused pane (`--terminal`): unverified, the pane keeps its launch sandbox (2026-11-10). The default path uses `--approve-for-me` with automatic review and `sandbox_workspace_write.network_access=true`; with the bypass flag true there is no sandbox: unguarded |
| cursor | `--force` (also `--yolo`) plus `--trust` (measured from `cursor-agent --help` 2026-08-02, re-measured 2026-08-04), plus `scripts/cursor-worker-pretrust <worktree-path>` (2026-08-03): exit 0 with a summary of added, updated, or already trusted, not skipped | command permission prompts; workspace trust via the measured `.workspace-trusted` storage. Follow-up on `cursor-agent 2026.07.23-e383d2b` with a fresh workspace and project-local `.cursor/hooks.json`: no second startup gate, hooks executed, no `hooks.state` or `trusted_hash` persistence | first-visit workspace-trust prompt is not covered by `--trust` at launch (2026-08-03); cleared by pre-trust | coverage unmeasured |
| grok | `--always-approve` (measured from `--help` 2026-08-02) | tool approval prompts | coverage unmeasured | coverage unmeasured |
| agy | `--dangerously-skip-permissions`, "Auto-approve all tool permission requests without prompting" (measured from `agy --help` 2026-08-04) | tool permission requests | Antigravity's folder-trust gate is not cleared by the flag (on record 2026-08-06); the `HOOK_TRUST_MARKERS` entry stays required after launch | coverage unmeasured |
| gemini | launched bare (`gemini`): absent from PATH on 2026-08-05, so no flag was measured | coverage unmeasured | coverage unmeasured | coverage unmeasured |
| opencode | launched bare: absent from PATH on 2026-08-05, so no flag was measured | coverage unmeasured | coverage unmeasured | coverage unmeasured |

### Successor spawn versus worker pre-trust

This section governs **worker** launch into isolated worktrees. Successor TUI spawn (`master-succeed spawn` / `_spawn_startup_command`) is a different entry point: it starts the next master seat in a host terminal, not a worktree worker under dispatch. For that path the runtime attaches the measured launch approval flags above (cursor-agent: `--force --trust`; agy: `--dangerously-skip-permissions`) so the seat is not prompt-blocked on its first tool call. That does not waive the worker pre-trust workflow. Worker attach into an isolated worktree still requires `scripts/cursor-worker-pretrust` (or the matching pre-trust path for the agent) as written above. Codex successors keep no launch flag and still rely on the account-wide pre-trust path because Codex has none.

Three-vote review is the default for non-trivial merges or direct-push changes. Split review lenses:

- general correctness
- regression disproof
- contract and scope

Use the majority verdict, but a minority P1 `FIX_FIRST` finding must be addressed or explicitly rejected with evidence.

PR review-bot threads are always worker-handled without per-round owner instruction: dispatch a fix worker on arrival, the master verifies, the worker replies and resolves, and the master judges rejections only. (charter rule since template v5) On a repository with review bots attached, zero unresolved threads is a merge precondition: every thread gets a reply stating what was done or why not, and the merge waits for the bots' pass over the latest push. Verify a bot finding against the code before acting on it — bots produce false positives, and a thread resolved without measuring is silence dressed as review.

After a worker's pull request is merged, recover the worker resources with `scripts/worker-reap --task-id <task-id> --ledger <ledger-path>` and record the reap in the ledger. Ambiguous worktrees are not removed: leave them in place and report the dirty, unmerged, inaccessible, or otherwise unsafe state.

Do not run large fan-out from the master workflow by default. If it is unavoidable, report scale and estimated cost first.
