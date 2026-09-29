Per-change changelog fragments replace shared `## Unreleased` edits (2026-09-28):

- `master-ops/changelog.d/`: a change touching `master-ops/` now adds a dated fragment file here
  instead of editing `## Unreleased` directly, so concurrent pull requests stop conflicting on the
  same shared lines. `README.md` documents the name pattern and the fold script; the directory
  ships with no fragment in it once a release folds the ones that came before.
- `scripts/changelog-release` (template side, not installed): folds every `changelog.d/*.md`
  fragment into `## Unreleased`, newest first by date then name, when the owner cuts a release.
  `--dry-run` previews the fold without changing anything. It refuses a malformed fragment name or
  an empty body instead of folding it silently.
- `scripts/generate-manifest` and `master-ops/scripts/template-check` both exclude `changelog.d`
  from the install manifest, so fragments never install and are never reported as unknown files.
- `master-ops/scripts/template-check`: `adoption_notes` for the `Unreleased` section now prepends
  the template's fragment bodies (same newest-first order) ahead of whatever `CHANGELOG.md` itself
  already holds under that heading, so an install compared against a live template still sees
  notes added since the last release.
- `.github/workflows/gates.yml`: a new `changelog-fragment` job, `pull_request` only, requires at
  least one added, well-named fragment whenever a pull request changes `master-ops/` outside
  `changelog.d/`. Its logic lives in `scripts/changelog-fragment-check <base-sha>` so it can also
  run locally. A pull request touching only `changelog.d/` or only `CHANGELOG.md` passes without one.
- Tracker: `mgm-q5am`.
