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
