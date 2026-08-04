# Conversation-surface redaction runbook

## What it does

**Authoring guard** - `scripts/pr-body-check` now includes redaction scans after narrative-section checks. Detects absolute home paths (macOS and Linux home-directory forms) in PR bodies and exits 1 if violations are found.

**Detection scan** - `scripts/conversation-redaction-scan` scans GitHub PR bodies, PR comments, repository-participant review summary bodies, review-thread comments, and issue bodies for the same patterns. Outputs findings as `surface|number|author|locator|pattern_class` (never printing the matched value itself) and exits 1 when violations exist.

## Why this matters (incident 2026-08-04, second occurrence)

Workers copied absolute home paths (identity-revealing home-directory strings) verbatim into public PR bodies and review replies. Repository redaction CI scanned tracked content only, so conversation surfaces shipped the leak; the owner caught it by eye and swept 2 PR bodies, 1 review reply, and 2 bot comments. Cheap, measured defenses prevent recurrence:

1. **Authoring time guard**: Run before merge (already a habit).
2. **Detection scan**: Periodic sweep for missed leaks.

## Authoring guard: scripts/pr-body-check

Extended to scan the PR body text against redaction patterns after checking narrative sections. On hit, prints the pattern class and line number (never the matched value) and exits 1.

```bash
scripts/pr-body-check <PR#> [--repo owner/repo]
```

Output on redaction violation:
```text
Problem: filled
Why this approach: filled
What this changes: filled
Expected effect: filled

Redaction violations detected:
  Line 5: [home_path] absolute path detected
```

Exit: 0 all checks pass, 1 section or redaction failure, 2 usage error.

## Detection scan: scripts/conversation-redaction-scan

Minimal v1 implementation. Fetches and scans:
- PR bodies
- PR comments
- Repository-participant review summary bodies (`authorAssociation` other than `NONE`; third-party bot review summaries are not owner-editable after submission)
- Review-thread comments
- Issue bodies (extensible)

Same pattern source as the authoring guard (home_path from product repo gitleaks config).

```bash
scripts/conversation-redaction-scan [--repo owner/name] [--limit N]
```

Options:
- `--repo` - Target repository (default: `$MOGUI_PRODUCT_REPO` or `baksohyeon/mogui-ADE-orchestrator`)
- `--limit` - Maximum PRs to scan (default: 30, always stated in output)

Output format (one line per finding):
```text
surface|number|author|locator|pattern_class
pr_body|72|dorito|PR#72|home_path
pr_comment|71|someone|PR#71/comments|home_path_linux
```

Exit: 0 clean, 1 findings exist, 2 API error.

## Remedy playbook (applied 2026-08-04)

When findings are detected, follow this exact procedure (owner-approved per PR#67 precedent):

1. **Edit own bodies/comments**: Use `gh pr edit` or GitHub web UI to remove the leak and replace with placeholder form (`~/path` or generic form like `<your-home-dir>`).
   ```bash
   gh pr edit <PR#> --body "$(cat new-body.txt)"
   ```

2. **Delete bot comments quoting a leak**: If a bot comment (CodeRabbit, linter, etc.) quoted the leaked value in context, delete the comment, not just edit it (because edit leaves the history). Use the endpoint for the surface that carried the leak; issue comments and pull-request review comments use different APIs.
   ```bash
   gh api repos/owner/repo/issues/comments/<comment-id> -X DELETE
   gh api repos/owner/repo/pulls/comments/<review-comment-id> -X DELETE
   ```

3. **Run redaction scan to verify**: After remediation, re-run the scanner to confirm the sweep is complete.
   ```bash
   scripts/conversation-redaction-scan --repo owner/repo
   ```

## Cadence

- **Before release**: Run `scripts/conversation-redaction-scan` against the product repo to catch any missed leaks.
- **On demand**: When a worker reports a suspected leak, or as a spot-check.
- **In CI** (future): Wire into pre-merge checks if desired.

## Falsification canary

To validate the scanner works, seed a synthetic marker in a test fixture and verify detection. Ideal: use a real historical finding (e.g., PR#72's original body pre-edit), but those are now cleaned. Fixture approach:

1. Create a test PR body file with a known marker:
   ```bash
   HOME_MARKER="/"Users/testcase
   {
     printf '## Problem\n'
     printf 'User path is %s/development.\n' "$HOME_MARKER"
     printf '\n## Why this approach\nfilled\n'
     printf '\n## What this changes\nfilled\n'
     printf '\n## Expected effect\nfilled\n'
   } > /tmp/test-pr-body.txt
   ```

2. Run pr-body-check against it:
   ```bash
   scripts/pr-body-check <real-PR#> --body-file /tmp/test-pr-body.txt
   ```

   Expected output:
   ```text
   Problem: filled
   Why this approach: filled
   What this changes: filled
   Expected effect: filled

   Redaction violations detected:
     Line 2: [home_path] absolute path detected
   ```

   Exit: 1 (violation detected)

3. Verify scanner does NOT print the actual path in any output (only the class name and location).

## Related docs

- `docs/analysis/2026-08-03-redaction-conversation-surface.md` - Design analysis and approach comparison
- Product repo `config/gitleaks.toml` - Canonical redaction patterns (home_path, etc.)
- Contract `contracts/2026-08-04-conversation-redaction-guard.md` - Worker contract and incident record
