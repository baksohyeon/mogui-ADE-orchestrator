# Dev-to-template promotion audit

Measured 2026-08-06 by comparing the operations repository with `master-ops/` in this
repository. Verdicts are based on file names and content; equal counts do not imply a
clean row.

The table is the pre-promotion baseline. After the scoped changes, the template counts
are `docs/runbooks 10`, `docs/blame 12`, `docs/lineage 2`, and `scripts/hooks 6`; the
remaining count differences are recorded as absent or instance-only below.

| Area | Operations | Template | Verdict |
| --- | ---: | ---: | --- |
| `docs/runbooks` | 19 | 9 | promoted and drifted; owner-named conventions and review voice promoted below; remaining operational runbooks are absent or instance-oriented |
| `docs/charter` | 10 | 10 | promoted and drifted; names match, section numbering matches, content has measured-instance drift |
| `docs/blame` | 12 | 0 | promoted here as redacted incident records |
| `docs/lineage` | 8 | 1 | promoted procedure and entry format; generation records remain private instance history |
| `docs/observability` | 1 | 1 | promoted and drifted; index is present, private journals and session records remain instance-only |
| `scripts` | 23 | 18 | promoted and drifted; runtime and logging helpers remain absent from the template |
| `scripts/hooks` | 5 | 5 | drift in both directions: `product-path-guard.sh` was absent from the template, while `bash-poll-warn.sh` is absent from the operations checkout |

The equal `scripts/hooks` count is a trap: names differ, so the row is not identical.
The equal `docs/charter` count is also insufficient; names and section numbering were
checked and agree, while measured prose differs.

## Promotions

- `contract-conventions.md` now states the boolean first-action verdict and carries the
  verbatim Writing block, including the rule that a contract must quote the convention it
  depends on.
- `review-voice.md` now covers rules 1-11, including human-facing home-path shortening.
- All 12 blame reports are present with machine paths, handles, process identifiers,
  workspace identifiers, and tracker identifiers removed or replaced by placeholders.
  Their observed failure shapes, root causes, and measurement-based prevention rules are
  retained.
- `boot-comparison-set.md` and `docs/lineage/README.md` carry the successor procedure and
  entry format. Generation records remain deliberately instance-only.
- `product-path-guard.sh` is shipped and onboarding documents both PreToolUse matchers.
- The dispatch template maps `agy` to the measured Gemini host behavior and includes the
  Antigravity folder-trust start-screen markers; the approval flag does not clear that
  gate.

## Deliberately instance-only

Absolute machine paths, usernames, process ids, terminal names and handles, session and
workspace ids, private boot journals, and private observability sessions cannot be
published without losing their instance-only meaning. They remain in operations records.
