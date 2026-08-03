# Worker report: onboarding runtime config

- **pwd:** `/Users/cnai/dev/personal/mogui/mogui-ADE-orchestrator/.orca/worktrees/mogui-ADE-orchestrator/onboarding-lane-0804`
- **branch:** `feat/onboarding-lane-0804` (path contains `.orca/worktrees`)
- **commit:** `a1449923e66c124ef4e568f0758e0a0c8809dd61`
- **PR:** https://github.com/baksohyeon/mogui-ADE-orchestrator/pull/77
- **assignee:** baksohyeon
- **gates:** `PYTHONPATH=src python3.12 -m pytest tests -q` → **477 passed, 13 subtests passed**
- **redaction-scan:** OK, 0 findings (org rules not loaded)
- **provenance:** owner onboarding-parameterization decision 2026-08-04

## Measured existing onboarding runtime questions

1. `master-ops/onboarding/01-preflight.md` — agent CLI / `ORCA_AGENT_CLI` (master host runtime).
2. `master-ops/onboarding/02-workspace-facts.md` — default model id; inventory/purpose for optional product path.
3. `master-ops/onboarding/08-settings-and-skills.md` — which hosts run the master.
4. `master-ops/onboarding/09-spawn.md` — launch runtime for gate/spawn (consumes answers).

Also measured: instance wrapper `mogui-master-ops/scripts/dispatch` hardcodes `DEFAULT_MASTER_HOST_RUNTIME=codex` and a Claude transcript glob (audit 2026-08-04).

## Config schema

| Key | One-sentence meaning |
| --- | --- |
| `master_host_runtime` | Agent CLI name the master session runs on. |
| `transcript_globs` | Per-runtime filesystem globs locating session JSONL for model probes. |
| `product_repo` | Optional absolute path of the primary product repository. |

- Example shipped: `config/instance-runtime.example.json`
- Filled path (instance-owned, gitignored): `config/instance-runtime.json`
- Fallback: env override → config file → honest unconfigured

## Files touched

- `.gitignore`
- `CHANGELOG.md`
- `config/instance-runtime.example.json`
- `docs/internal/specs/model-identity-probe-wiring-spec.md`
- `docs/public/reference.md`
- `master-ops/CHANGELOG.md`
- `master-ops/TEMPLATE-VERSION` (`v0.4.3`)
- `master-ops/onboarding/01-preflight.md`
- `master-ops/onboarding/02-workspace-facts.md`
- `master-ops/onboarding/08-settings-and-skills.md`
- `master-ops/onboarding/09-spawn.md`
- `scripts/model-identity-probe` (consumer)
- `src/master_runtime/core/instance_runtime_config.py`
- `tests/test_instance_runtime_config.py`

## Consumer

`scripts/model-identity-probe`: when `--transcript` is omitted, resolves via `MOGUI_TRANSCRIPT_GLOB` → instance config `transcript_globs` / `master_host_runtime` → unconfigured (exit 2). Never bakes a default path or host.

## Left for steward / follow-up

- PR merge (worker must not merge).
- Instance wrapper `mogui-master-ops/scripts/dispatch` can drop `DEFAULT_MASTER_HOST_RUNTIME=codex` once it reads this config or `MOGUI_MASTER_HOST_RUNTIME`.
- Dispatch capability token was not available in this worker environment; heartbeats were rejected with `dispatch_capability_invalid`.
