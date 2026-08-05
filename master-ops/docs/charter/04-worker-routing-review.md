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

The installation-specific worker tier mapping lives in the instance file `{{RUNTIME_ROOT}}/config/model-tier-policy.json` when onboarding wrote one (after agent-inventory consent), else the template `model-tier-policy.json`. It groups installed model identifiers into tiers; use the lowest sufficient tier for each worker lane. Measure what this host actually offers before filling it in: never guess a model id, and a model the file has never heard of is not blocked — it resolves to the `unknown` tier and uses that tier's stated cap when present, otherwise uncapped (same as any tier with no `fanout_caps` entry). An unlisted id must not be punished as if it were top tier. Owner directive 2026-08-04 retired the daily one-per-day top cap. Gate resolution: `DISPATCH_TIER_POLICY` → instance `config/model-tier-policy.json` → template `master-ops/model-tier-policy.json`.

Worker contract clause library: `docs/runbooks/contract-conventions.md`.

## Worker Launch Approval Posture

For operations-repository work, dispatch workers into an isolated `git worktree`. The master chooses the worktree at dispatch time, and successor spawn separately fail-closes on `expected_placement` mismatch (`SPAWN_PLACEMENT_MISMATCH = 26`). The worker's first-action placement verdict is not dispatch evidence; it is a self-stop condition for a worker that finds itself in the wrong place. Require `in_expected_worktree`, `is_master_checkout`, and `branch`, with no absolute path in the report, and stop the worker immediately if `is_master_checkout` is `yes`. On 2026-08-03, ambiguous placement caused four contaminations of the master's own tree in one day. Placement contracts still name exact paths downward to the worker; reports send verdicts upward.

Workers launched into isolated worktrees must start with the agent's non-interactive approval flag, or the measured pre-trust posture below, so allowlist or trust prompts cannot block them mid-task. Pre-trust holds when the summary reports the worktree added, updated, or already trusted; the skip path (`Summary: skipped`) leaves the trust prompt in place and says so on stdout, so read the summary line before relying on it. At every dispatch, the master MEASURES the installed CLI's `--help` output and uses only flags present there; it never guesses flags from memory.

MEASURED examples from 2026-08-02:

- Grok: `--always-approve`.
- Claude Code: `--dangerously-skip-permissions`.
- Cursor Agent: `--force` (also exposed as `--yolo`) to force-allow commands unless explicitly denied, plus `--trust` to trust the current workspace without prompting. Source: `cursor-agent --help`. Re-measured 2026-08-04: `-f, --force  Force allow commands unless explicitly denied`; `--trust  Trust the current workspace without prompting`.
- Codex: run `scripts/codex-worker-pretrust <worktree-path>` and retain the account-wide hooks trust posture; Codex uses this pre-trust path instead of a launch approval flag.

MEASURED addition from 2026-08-03:

- Cursor Agent pre-trust: run `scripts/cursor-worker-pretrust <worktree-path>` before attach and require exit status 0 with a summary that reports `added`, `updated`, or `already trusted` (not `skipped`); this uses Cursor Agent's measured `.workspace-trusted` storage instead of relying on `--trust` at worker launch. Follow-up measurement on `cursor-agent 2026.07.23-e383d2b` with a fresh workspace plus project-local `.cursor/hooks.json` showed no second startup gate: launch passed without extra prompts, hooks executed, and no `hooks.state`/`trusted_hash` persistence appeared in Cursor state.

MEASURED addition from 2026-08-04:

- Agy: `--dangerously-skip-permissions` (Auto-approve all tool permission requests without prompting). Source: `agy --help`.

### Successor spawn versus worker pre-trust

This section governs **worker** launch into isolated worktrees. Successor TUI spawn (`master-succeed spawn` / `_spawn_startup_command`) is a different entry point: it starts the next master seat in a host terminal, not a worktree worker under dispatch. For that path the runtime attaches the measured launch approval flags above (cursor-agent: `--force --trust`; agy: `--dangerously-skip-permissions`) so the seat is not prompt-blocked on its first tool call. That does not waive the worker pre-trust workflow. Worker attach into an isolated worktree still requires `scripts/cursor-worker-pretrust` (or the matching pre-trust path for the agent) as written above. Codex successors keep no launch flag and still rely on the account-wide pre-trust path because Codex has none.

Three-vote review is the default for non-trivial merges or direct-push changes. Split review lenses:

- general correctness
- regression disproof
- contract and scope

Use the majority verdict, but a minority P1 `FIX_FIRST` finding must be addressed or explicitly rejected with evidence.

PR review-bot threads are always worker-handled without per-round owner instruction: dispatch a fix worker on arrival, the master verifies, the worker replies and resolves, and the master judges rejections only. (charter rule since template v5) On a repository with review bots attached, zero unresolved threads is a merge precondition: every thread gets a reply stating what was done or why not, and the merge waits for the bots' pass over the latest push. Verify a bot finding against the code before acting on it — bots produce false positives, and a thread resolved without measuring is silence dressed as review.

Do not run large fan-out from the master workflow by default. If it is unavoidable, report scale and estimated cost first.
