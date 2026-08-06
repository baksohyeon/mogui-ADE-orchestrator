# Upgrade — Bring A Founded Ops Repository Forward

Load rule: read this file only when the router's mode question answered **Upgrade**, or when the Founding guard routed here because an ops repository or lineage file already exists. Router: [`../ONBOARDING.md`](../ONBOARDING.md). This mode uses no other step file.

**Position and action:** the workspace already has an ops repository. Compare it to the current template manifest, show the owner exactly what would change, and apply only after explicit confirmation. Do not re-found. Do not touch instance-owned records.

**Standing block: do not spawn.** No new master terminal, no `master-succeed spawn`, no founding kickoff. If a check fails badly enough that a new master seems needed, that is a succession decision for the owner and the living master — not an upgrade outcome.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: this workspace was already set up, and the book the Master reads from may be behind the current template. What we do next: measure what is missing or unknown against the template's file list, show every path that would be written and why, then wait for a clear yes before writing anything. Paths the workspace owns for itself — lineage, role state, tracker data, local config, contracts — stay untouched by name. Provide the workspace root and ops repository path when those facts are not already available.

## Checklist

0. **Bootstrap the facts first**: ask the owner for the workspace root and ops repository path (or the operating card). Do not scan the disk for candidate workspaces. Do not substitute this orchestrator clone's paths. The ops-side `{{WORKSPACE_NAME}}`, `{{WORKSPACE_ROOT}}`, `{{OPS_REPO}}`, `{{MONITOR_NS}}`, `{{MODEL_ID}}`, and `{{REPO_LIST}}` values below mean values measured from that ops repository. `{{RUNTIME_ROOT}}` and `{{TEMPLATE_VERSION}}` come from the template clone.

1. **Locate the template**: the live ADE clone that carries the current skeleton (the one this router was loaded from is the default). Record its path as the template root. An install too old to contain `scripts/template-check` is still checkable by running the script from the template side:

```console
"{{RUNTIME_ROOT}}/master-ops/scripts/template-check" --ops "{{OPS_REPO}}" --template "{{RUNTIME_ROOT}}/master-ops"
```

When the ops repository already has the script:

```console
"{{OPS_REPO}}/scripts/template-check" --ops "{{OPS_REPO}}" --template "{{RUNTIME_ROOT}}/master-ops"
```

2. **Read the report**: the report states which set it produced (`install-manifest` alone, or `template-compare` when `--template` was given). Record installed version (or "undeterminable" when `MANIFEST.json` is absent), template version, absent required paths, and unknown present paths. A missing manifest is the expected shape for pre-manifest installs — continue by content presence, do not invent a version.

3. **Dry-run apply (always first)**: print the exact file list and the reason for each path. No write yet.

```console
"{{RUNTIME_ROOT}}/master-ops/scripts/template-apply" --ops "{{OPS_REPO}}" --template "{{RUNTIME_ROOT}}/master-ops"
```

4. **Owner confirmation**: show the dry-run plan in the owner's language. Require an explicit confirmation before any write. There is no silent apply and no flag that skips confirmation on any run. If the owner declines, stop and leave the report.

5. **Write pass (only after confirmation)**: re-run with `--write` and type the confirmation phrase the tool demands. Placeholder substitution uses only the documented set from the router (`{{WORKSPACE_NAME}}`, `{{WORKSPACE_ROOT}}`, `{{OPS_REPO}}`, `{{MONITOR_NS}}`, `{{MODEL_ID}}`, `{{REPO_LIST}}`, `{{RUNTIME_ROOT}}`, `{{TEMPLATE_VERSION}}`). Add none. Prefer values already measured from the existing install. For example, repeat `--placeholder KEY=VALUE` for each measured value: `"{{RUNTIME_ROOT}}/master-ops/scripts/template-apply" --ops "{{OPS_REPO}}" --template "{{RUNTIME_ROOT}}/master-ops" --write --placeholder WORKSPACE_NAME="{{WORKSPACE_NAME}}" --placeholder WORKSPACE_ROOT="{{WORKSPACE_ROOT}}" --placeholder OPS_REPO="{{OPS_REPO}}" --placeholder MONITOR_NS="{{MONITOR_NS}}" --placeholder MODEL_ID="{{MODEL_ID}}" --placeholder REPO_LIST="{{REPO_LIST}}" --placeholder RUNTIME_ROOT="{{RUNTIME_ROOT}}" --placeholder TEMPLATE_VERSION="{{TEMPLATE_VERSION}}"`.

6. **Refusals by name**: the apply step must refuse, and report as such, for:
   - `docs/lineage/`
   - `docs/runbooks/role-state.md`
   - `.beads/`
   - `config/`
   - `contracts/`
   - anything the manifest does not claim

   Per-file outcomes are one of: planned, written, skipped-as-instance-owned, refused-not-in-manifest, error-invalid-path, error-missing-template-file. Dry-run prints `planned` for each template-layer path that would write; any `error-*` outcome fails the plan (nonzero exit) before confirmation.

7. **Re-check**: run `template-check` again with `--template` and confirm the report_set is `template-compare`. A clean shape is the goal; remaining unknown paths that are deliberate local additions stay listed as unknown and are not deleted.

## Report

State, in the owner's language: which report set was produced, installed vs template version, how many paths were written, how many were refused as instance-owned, and how many unknown local paths remain. Then stop; Upgrade has no spawn and no further steps.
