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

The installation-specific worker tier mapping lives in `model-tier-policy.json`, which groups installed model identifiers into tiers; use the lowest sufficient tier for each worker lane. Measure what this host actually offers before filling it in: a template default lists models a machine may not have, and a model the file has never heard of is not blocked, it is capped as `unknown`.

Worker contract clause library: `docs/runbooks/contract-conventions.md`.

## Worker Launch Approval Posture

For operations-repository work, dispatch workers into an isolated `git worktree` and require first-action placement proof (`pwd`, `git branch --show-current`) in that worker checkout. If those measurements show the master's primary checkout instead, stop immediately: on 2026-08-03 this exact ambiguity caused four contaminations of the master's own tree in one day.

Workers launched into isolated worktrees must start with the agent's non-interactive approval flag, or the measured pre-trust posture below, so allowlist or trust prompts cannot block them mid-task. Pre-trust holds when the summary reports the worktree added, updated, or already trusted; the skip path (`Summary: skipped`) leaves the trust prompt in place and says so on stdout, so read the summary line before relying on it. At every dispatch, the master MEASURES the installed CLI's `--help` output and uses only flags present there; it never guesses flags from memory.

MEASURED examples from 2026-08-02:

- Grok: `--always-approve`.
- Claude Code: `--dangerously-skip-permissions`.
- Cursor Agent: `--force` (also exposed as `--yolo`) to force-allow commands unless explicitly denied, plus `--trust` to trust the current workspace without prompting.
- Codex: run `scripts/codex-worker-pretrust <worktree-path>` and retain the account-wide hooks trust posture; Codex uses this pre-trust path instead of a launch approval flag.

MEASURED addition from 2026-08-03:

- Cursor Agent pre-trust: run `scripts/cursor-worker-pretrust <worktree-path>` before attach and require exit status 0 with a summary that reports `added`, `updated`, or `already trusted` (not `skipped`); this uses Cursor Agent's measured `.workspace-trusted` storage instead of relying on `--trust` at worker launch. Follow-up measurement on `cursor-agent 2026.07.23-e383d2b` with a fresh workspace plus project-local `.cursor/hooks.json` showed no second startup gate: launch passed without extra prompts, hooks executed, and no `hooks.state`/`trusted_hash` persistence appeared in Cursor state.

Three-vote review is the default for non-trivial merges or direct-push changes. Split review lenses:

- general correctness
- regression disproof
- contract and scope

Use the majority verdict, but a minority P1 `FIX_FIRST` finding must be addressed or explicitly rejected with evidence.

PR review-bot threads are always worker-handled without per-round owner instruction: dispatch a fix worker on arrival, the master verifies, the worker replies and resolves, and the master judges rejections only. (charter rule since template v5) On a repository with review bots attached, zero unresolved threads is a merge precondition: every thread gets a reply stating what was done or why not, and the merge waits for the bots' pass over the latest push. Verify a bot finding against the code before acting on it — bots produce false positives, and a thread resolved without measuring is silence dressed as review.

Do not run large fan-out from the master workflow by default. If it is unavoidable, report scale and estimated cost first.
