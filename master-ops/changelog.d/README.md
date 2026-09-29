One file per change touching `master-ops/`, holding what would have been its `## Unreleased` entry.
Name: `<YYYY-MM-DD>-<slug>.md`, slug lowercase `[a-z0-9-]+`.
Folded into `../CHANGELOG.md` by the owner when a release is cut, not at merge time.
Script: `scripts/changelog-release` (`--dry-run` to preview the fold first).
