Changelog fragment tooling: thirteen review-thread fixes in one pass (2026-09-29):

- `scripts/changelog-release`: `--dry-run` no longer truncates the preview when a fragment or
  existing entry contains a `## ` line inside a fenced code block. The fold is now a recoverable
  step — a rerun after a partial failure (changelog written, a fragment's deletion failed) detects
  that a fragment's body is already present as a whole paragraph block under `## Unreleased`
  (boundary-padded match, not a bare substring test, so a new fragment whose body merely overlaps
  unrelated existing text still folds instead of being silently dropped), reports it
  `already folded`, and deletes it without folding it again. A malformed date (e.g. `2026-02-30`)
  is refused the same way a bad name is. A missing or unreadable `master-ops/CHANGELOG.md` prints
  one stderr line and exits 2 instead of a raw traceback.
- `scripts/changelog-fragment-check`: only root-level `changelog.d/*.md` files count as fragments,
  matching what both fold consumers actually read — a fragment left in a subdirectory, or a
  non-`.md` file such as a stray `.DS_Store`, no longer satisfies or trips the gate. Both diff
  scans now run with `--no-renames`, so `git mv` of a fragment (or of a `master-ops/` file) is seen
  as an add/delete pair instead of a rename `--diff-filter=A` would silently drop. An added
  fragment with an empty body, or an impossible calendar date, now fails the gate, mirroring the
  release script's own refusals — an impossible date could otherwise merge and then block the
  next release-time fold.
- Fragment-name grammar (`FRAGMENT_RE`): the canonical definition, plus the impossible-date check,
  now lives in `master-ops/scripts/template_common.py`; `master-ops/scripts/template-check` imports
  it. `scripts/changelog-release` and `scripts/changelog-fragment-check` cannot import across the
  template boundary without a `sys.path` hack, so they keep string-identical duplicates instead,
  checked by a test that compares the compiled regex patterns.
- `master-ops/scripts/template-check`: an unreadable fragment (bad encoding, etc.) is now skipped
  and recorded under `questions_unanswered`, matching its own docstring, instead of aborting the
  whole check with exit 2.
- `master-ops/CHANGELOG.md`: the fragment instruction now states the two gate exemptions
  (`changelog.d/`-only and `CHANGELOG.md`-only changes) so the guidance agrees with the gate.
- `master-ops/MANIFEST.json`: `scripts/test-changelog-fragment-check.sh` is now excluded from the
  install manifest (`scripts/generate-manifest` `EXCLUDE_FILES`) since the script it exercises,
  `scripts/changelog-fragment-check`, is deliberately not installed; a skipping test is a line
  nobody reads, so exclusion was chosen over a subject-absent skip.
- Tests: `tests/test_changelog_release.py` gained coverage for the fenced-heading preview, the
  impossible-date refusal, the missing-changelog error, both idempotent-rerun halves, and the
  shared-grammar equality check. `tests/test_template_check_apply.py` now asserts the `README.md`
  fixture body never leaks into an adoption note. `master-ops/scripts/test-changelog-fragment-check.sh`
  gained cases for the subdirectory fragment, the empty-body fragment, and the `git mv` rename.
- Tracker: `mgm-q5am`; round one `task_04bfdb95c7d6`.
