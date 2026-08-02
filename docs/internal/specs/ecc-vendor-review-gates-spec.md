# ECC Review Gates Vendoring Spec

Date: 2026-08-02

## Scope

This repo vendors a selected ECC review-gate set for orchestrator-side usage:

- `.claude/commands/review-pr.md`
- `.claude/agents/code-reviewer.md`
- `.claude/agents/comment-analyzer.md`
- `.claude/agents/pr-test-analyzer.md`
- `.claude/agents/silent-failure-hunter.md`
- `.claude/agents/type-design-analyzer.md`
- `.claude/agents/code-simplifier.md`
- `.claude/commands/orch-review.md`
- `.claude/workflows/orch-review.workflow.js`
- `.claude/workflows/README.md`
- `.claude/skills/delivery-gate/SKILL.md`
- `.claude/skills/delivery-gate/hooks/quality-gate.py`

## Placement Rationale

Placed under `.claude/` (orchestrator session assets), not `master-ops/`, because these are host runtime review gates for this harness repository session rather than generated operations-repository template content.

## License Notice

The vendored ECC material is under MIT with required copyright notice retained in:

- `vendor/ecc/LICENSE-ECC`

Source project:

- https://github.com/affaan-m/ECC

## Delivery-Gate Hook Wiring Policy

This repository stores delivery-gate payload files only. It does **not** auto-wire
hooks into user-global settings.

### Wiring specification (owner/security session only)

1. Copy payload script into a chosen local scripts path.
2. Add a `Stop` hook entry in the host settings file that executes the script.
3. Keep changes local to the operator environment, outside this repository.

### Non-goals

- No modification of `~/.claude/settings.json` by repository code.
- No automatic hook registration during install or onboarding.

## Upstream vs Local Changes

For this harness, vendored ECC assets include the following local behavior changes:

- `orch-review.workflow.js`: reviewer `agentType` values are remapped to locally vendored agents (`code-reviewer`, `silent-failure-hunter`) so the workflow runs self-contained without requiring external `ecc:` namespace registration.
- `orch-review.workflow.js`: security trigger keywords are expanded to include request/input access patterns (`req`, `params`, `body`, `input`, and related terms).
- `orch-review.workflow.js`: dedup identity now uses evidence plus location keying to avoid collapsing distinct repeated snippets in the same file.
- `orch-review.workflow.js`: severity merge now preserves the strictest finding payload/proof when dimensions disagree on severity.
- `commands/review-pr.md`: PR argument handling now requires safe numeric-id extraction and rejects raw shell interpolation; diff retrieval uses `gh pr diff` (with `gh pr view --json files` for file metadata).
- `commands/review-pr.md`: cross-repository PR URLs now preserve parsed `<owner>/<repo>` and pass `--repo` in all `gh` PR calls to avoid reviewing the wrong repository.
- `commands/orch-review.md`: PR URL parsing guidance now explicitly allows normalized URLs with trailing slash/query/hash stripped before id extraction, and preserves `<owner>/<repo>` with `--repo` for all PR-mode `gh` calls.
- `skills/delivery-gate/SKILL.md`: install path and enforcement docs are aligned to the vendored hook payload and current script behavior (disk reminder/warn/critical tiers and growth-log blocking rule).
- `workflows/README.md`: workflow narrative is aligned to local agent mappings and fail-closed verifier behavior.
- `vendor/ecc/LICENSE-ECC`: removed local absolute clone path from attribution notice; source attribution remains via upstream repository URL.
