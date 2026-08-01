This reference summarizes the executable scripts in this repository. The generated section is derived from local `scripts/` help output.

# Reference

Use this page for command discovery. The lifecycle and delegation guides explain when to use each entry point.

<!-- AUTO-GENERATED from scripts/ --help -->
| Script | Command | Purpose | Key options |
| --- | --- | --- | --- |
| `scripts/acceptance-loop` | `acceptance-loop validate` | Check an acceptance suite file for structural validity. | None beyond `-h` or `--help`. |
| `scripts/acceptance-loop` | `acceptance-loop split` | Split a suite into a visible set and a held-out set. | `--output-dir`. |
| `scripts/acceptance-loop` | `acceptance-loop run` | Run the deterministic acceptance loop against a proposer command. | `--max-iterations`, `--baseline-ref`, `--restore-cmd`. |
| `scripts/acceptance-loop` | `acceptance-loop inspect` | Report suite and holdout composition without running the loop. | None beyond `-h` or `--help`. |
| `scripts/adapter` | `adapter doctor` | Report visible adapter tools and whether required local dependencies are present. | None beyond `-h` or `--help`. |
| `scripts/dispatch-gate` | `dispatch-gate check` | Evaluate a worker contract and record an allow or deny decision in the dispatch ledger. | Global `--ledger`; command options `--runtime`, `--contract`, `--agents`, `--est-chars`. |
| `scripts/dispatch-gate` | `dispatch-gate register` | Register a worker job only after a probe confirms the job id appears in an expected artifact. | Global `--ledger`; command options `--job-id`, `--probe-cmd`, `--contract-sha`, `--runtime`. |
| `scripts/dispatch-gate` | `dispatch-gate watch` | Check a worker log for stall conditions. | Global `--ledger`; command options `--log`, `--max-idle`. |
| `scripts/l1-digest` | `l1-digest tick` | Run one read-only L1 digest observation tick from a config file. | `--config`. |
| `scripts/master-bootstrap` | `master-bootstrap` | Build a bounded bootstrap block from charter, optional handoff, budget, session id, and role state checks. | `--charter`, `--handoff`, `--budget`, `--session-id`, `--strict-lease`, `--json`. |
| `scripts/master-bootstrap-live` | `master-bootstrap-live` | Emit the live session-start bootstrap block from a handoff directory and optional role-state file. | `--handoff-dir`, `--role-state-file`, `--budget`, `--bd`, `--charter-pointer`. |
| `scripts/master-recover` | `master-recover` | Inspect recovery inputs and produce a recovery report for a master session. | `--charter`, `--handoff`, `--ledger`, `--repo`, `--monitor-pattern`, `--session-id`, `--json`. |
| `scripts/master-succeed` | `master-succeed detect` | Classify succession trigger text and optional context pressure. | `text`, `--context-ratio`, `--json`. |
| `scripts/master-succeed` | `master-succeed handoff` | Build a thin handoff from a JSON spec. | `--spec`, `--json`. |
| `scripts/master-succeed` | `master-succeed verify-successor` | Verify a successor recovery report. | `--report`, `--json`. |
| `scripts/master-succeed` | `master-succeed check-duplicates` | Detect duplicate master instances by marker while excluding the current handle. | `--self-handle`, `--marker`, `--json`. |
| `scripts/master-succeed` | `master-succeed retire` | Resolve and optionally close exactly one predecessor terminal or session. | `--self-handle`, `--expected`, `--target-handle`, `--target-pty-id`, `--target-session-id`, `--execute`, `--json`. |
| `scripts/master-succeed` | `master-succeed spawn` | Spawn or dry-run a clean successor terminal for a selected workspace. | `--workspace-selector`, `--kickoff-text` or `--kickoff-file`, `--root`, `--model`, `--title`, `--dry-run`, `--json`. |
| `scripts/model-identity-probe` | `model-identity-probe` | Read recent assistant events from a transcript and compare the measured model with an expected model when supplied. | `--transcript`, `--expect`, `--limit`. Exit 0 match, 2 drift or undecidable. |
| `scripts/model-drift-audit` | `model-drift-audit` | Walk every assistant turn in a transcript and report model transitions with timestamps. | `--transcript`, `--session`, `--expect`, `--projects-dir`, `--workspace-dir`, `--ignore-synthetic`, `--json`. Exit 0 no transition, 1 transition or expectation mismatch, 2 undecidable. |
| `scripts/redaction-scan.sh` | `redaction-scan.sh` | Scan tracked, staged, or ranged files for secrets and internal identifiers before publication. | `--staged`, `--range A..B`, `--help`; allowlist defaults to `scripts/redaction-allowlist.txt` or `REDACTION_ALLOWLIST`. |
<!-- END AUTO-GENERATED from scripts/ --help -->

The generated table intentionally lists the public command surface only. Local host routing, private paths, and sensitive-lane details are outside this reference.

Exit codes are not shared vocabulary across these scripts. `model-identity-probe` reports both drift and undecidable as 2; `model-drift-audit` separates them. Read each script's codes from its own row rather than assuming a convention.
