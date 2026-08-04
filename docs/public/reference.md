This reference summarizes the executable scripts in this repository. The table is written by hand from each script's own `--help`, and `tests/test_reference_command_table.py` fails when a command exists with no row, or a row outlives its command.

# Reference

Use this page for command discovery. The lifecycle and delegation guides explain when to use each entry point.

<!-- COMMAND TABLE: rows are checked against scripts/ --help by tests/test_reference_command_table.py -->
| Script | Command | Purpose | Key options |
| --- | --- | --- | --- |
| `scripts/acceptance-loop` | `acceptance-loop validate` | Check an acceptance suite file for structural validity. | None beyond `-h` or `--help`. |
| `scripts/acceptance-loop` | `acceptance-loop split` | Split a suite into a visible set and a held-out set. | `--output-dir`. |
| `scripts/acceptance-loop` | `acceptance-loop run` | Run the deterministic acceptance loop against a proposer command. | `--max-iterations`, `--baseline-ref`, `--restore-cmd`. |
| `scripts/acceptance-loop` | `acceptance-loop inspect` | Report suite and holdout composition without running the loop. | None beyond `-h` or `--help`. |
| `scripts/adapter` | `adapter doctor` | Report visible adapter tools and whether required local dependencies are present. | None beyond `-h` or `--help`. |
| `scripts/codex-worker-pretrust` | `codex-worker-pretrust` | Mark a worktree as trusted in every Orca-managed Codex account config, so a dispatched worker does not stop on a trust prompt. | Positional absolute worktree path; `--accounts-dir`. Finds its own TOML-capable interpreter (`python3`, newer versioned names, `python`) and, when none has `tomllib`, skips loudly without touching any config. |
| `scripts/cursor-worker-pretrust` | `cursor-worker-pretrust` | Mark a worktree as trusted in Cursor Agent's measured trust storage, so a dispatched worker does not stop on the workspace-trust prompt. | Positional absolute worktree path; `--projects-dir`. Writes the measured `.workspace-trusted` marker under `~/.cursor/projects/<project-key>/` after validating existing JSON; when no Python 3.6+ JSON interpreter is available, skips loudly without touching any marker. |
| `scripts/dispatch-gate` | `dispatch-gate check` | Evaluate a worker contract and record an allow or deny decision in the dispatch ledger. | Global `--ledger`; command options `--runtime`, `--contract`, `--agents`, `--est-chars`. |
| `scripts/dispatch-gate` | `dispatch-gate register` | Register a worker job only after a probe confirms the job id appears in an expected artifact. | Global `--ledger`; command options `--job-id`, `--probe-cmd`, `--contract-sha`, `--runtime`. |
| `scripts/dispatch-gate` | `dispatch-gate watch` | Check a worker log for stall conditions. | Global `--ledger`; command options `--log`, `--max-idle`. |
| `scripts/dispatch-gate` | `dispatch-gate report` | Aggregate the ledger into denial, override, tier, and model counts, so the gate's own record can be read back. | Global `--ledger`; command option `--today` limits it to the current UTC day. |
| `scripts/l1-digest` | `l1-digest tick` | Run one read-only L1 digest observation tick from a config file. | `--config`. |
| `scripts/master-bootstrap` | `master-bootstrap` | Build a bounded bootstrap block from charter, optional handoff, budget, session id, and role state checks. | `--charter`, `--handoff`, `--budget`, `--session-id`, `--strict-lease`, `--json`. |
| `scripts/master-bootstrap-live` | `master-bootstrap-live` | Emit the live session-start bootstrap block from a handoff directory and optional role-state file. | `--handoff-dir`, `--role-state-file`, `--budget`, `--bd`, `--charter-pointer`. |
| `scripts/master-recover` | `master-recover` | Inspect recovery inputs and produce a recovery report for a master session. | `--charter`, `--handoff`, `--ledger`, `--repo`, `--monitor-pattern`, `--session-id`, `--json`. |
| `scripts/master-succeed` | `master-succeed detect` | Classify succession trigger text and optional context pressure. | `text`, `--context-ratio`, `--json`. |
| `scripts/master-succeed` | `master-succeed handoff` | Build a thin handoff from a JSON spec. | `--spec`, `--json`. |
| `scripts/master-succeed` | `master-succeed verify-successor` | Verify a successor recovery report. | `--report`, `--json`. |
| `scripts/master-succeed` | `master-succeed check-duplicates` | Detect duplicate master instances by marker while excluding the current handle. | `--self-handle`, `--marker`, `--json`. |
| `scripts/master-succeed` | `master-succeed retire` | Resolve and optionally close exactly one predecessor terminal or session. | `--self-handle`, `--expected`, `--target-handle`, `--target-pty-id`, `--target-session-id`, `--execute`, `--json`. |
| `scripts/master-succeed` | `master-succeed spawn` | Spawn or dry-run a clean successor terminal for a selected workspace. | `--workspace-selector`, `--expected-placement`, `--kickoff-text` or `--kickoff-file`, `--root`, `--model`, `--agent`, `--title`, `--dry-run`, `--json`. |
| `scripts/model-identity-probe` | `model-identity-probe` | Read recent assistant events from a transcript and compare the measured model with an expected model when supplied. | `--transcript` (optional when instance config or `MOGUI_TRANSCRIPT_GLOB` can resolve one), `--runtime`, `--config`, `--expect`, `--limit`. Exit 0 means match when an expected model is supplied, or informational output that asserts nothing when it is not. Exit 2 means drift, undecidable, or unconfigured transcript location. Transcript resolution order when `--transcript` is omitted: env `MOGUI_TRANSCRIPT_GLOB` → `config/instance-runtime.json` (`INSTANCE_RUNTIME_CONFIG` overrides the path) → honest unconfigured (never a baked default path). |
| `scripts/model-drift-audit` | `model-drift-audit` | Walk every assistant turn in a transcript and report model transitions with timestamps. | `--transcript`, `--session`, `--expect`, `--projects-dir`, `--workspace-dir`, `--ignore-synthetic`, `--json`. Exit 0 no transition, 1 transition or expectation mismatch, 2 undecidable. |
| `scripts/next-version` | `next-version` | Print the release version that would be cut now from owner-managed MAJOR.MINOR and a derived build count. | None beyond `--help`. |
| `scripts/onboarding-preflight.sh` | `onboarding-preflight.sh` | Measure the tools onboarding depends on before Step 1 spawns anything, and block on a missing required one. | `--fix` may add or refresh global Orca skills and installs no applications. `PREFLIGHT_WAIVE` downgrades a named check and says so in the summary. Exit 0 ready, 1 blocked. |
| `scripts/redaction-inventory` | `redaction-inventory` | Report tokens that no redaction rule covers, which is the inverse of what the scan asks. | `--baseline`, `--min-count`, `--json`. Exit 0 nothing uncovered, 1 candidates found, 2 cannot decide. A candidate is not a secret and an empty result is not proof of safety. |
| `scripts/redaction-scan.sh` | `redaction-scan.sh` | Scope a gitleaks scan to tracked content, scan commit messages that gitleaks does not read, and state what was covered. | Default is all tracked files; `--staged`, `--range A..B`, `--commit-messages A..B`, `--help`. Organization rules come from `REDACTION_EXTRA_PATTERNS` as `id\|description\|regex` lines, and `REDACTION_REQUIRE_EXTRA=1` makes a missing or empty file exit 2. Exit 0 clean, 1 findings, 2 cannot decide. The `scripts/redaction-allowlist.txt` format is retired: a file still holding entries in it exits 2. |
<!-- END COMMAND TABLE -->

The table lists the public command surface only. Local host routing, private paths, and sensitive-lane details are outside this reference.

Exit codes are not shared vocabulary across these scripts. `model-identity-probe` reports both drift and undecidable as 2; `model-drift-audit` separates them. Read each script's codes from its own row rather than assuming a convention.
