---
description: Comprehensive PR review using specialized agents
---

Run a comprehensive multi-perspective review of a pull request.

## Usage

`/review-pr [PR-number-or-URL] [--focus=comments|tests|errors|types|code|simplify]`

If no PR is specified, review the current branch's PR. If no focus is specified, run the full review stack.

## Steps

1. Identify the PR:
   - if `$ARGUMENTS` is provided, derive a **safe numeric PR id** first
   - accept either a bare integer or a GitHub PR URL, after stripping query/hash/trailing slash
   - reject anything else; never pass raw `$ARGUMENTS` into shell commands
   - use:
     - `gh pr view <NUMBER> --json files` for changed files metadata
     - `gh pr diff <NUMBER>` for unified diff text
   - if no argument is provided, resolve current branch PR with `gh pr view` and then read diff via `gh pr diff`
2. Find project guidance:
   - look for `CLAUDE.md`, lint config, TypeScript config, repo conventions
3. Run specialized review agents:
   - `code-reviewer`
   - `comment-analyzer`
   - `pr-test-analyzer`
   - `silent-failure-hunter`
   - `type-design-analyzer`
   - `code-simplifier`
4. Aggregate results:
   - dedupe overlapping findings
   - rank by severity
5. Report findings grouped by severity

## Confidence Rule

Only report issues with confidence >= 80:

- Critical: bugs, security, data loss
- Important: missing tests, quality problems, style violations
- Advisory: suggestions only when explicitly requested
