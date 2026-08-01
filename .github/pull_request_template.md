## Summary

What changed, and what made it necessary.

## Testing

- [ ] `PYTHONPATH=src python3 -m pytest tests -q` — paste the count
- [ ] A test that fails without this change, or a note on why none was needed
- [ ] New files staged before running any scan. The scanners read tracked files, so an unstaged addition is invisible to them and the run comes back green without having looked at it.

## Review

If you ran a review, automated or otherwise, say what it flagged and what you did. Say which findings you reproduced yourself. A review is a claim until it is measured.

## Changelog

There are two, and they are not interchangeable.

- Changes to the orchestrator go under `[Unreleased]` in the root `CHANGELOG.md`, if a user would notice them. Internal refactors and test-only changes need no entry.
- Changes to `master-ops/` go in `master-ops/CHANGELOG.md`, covered below.

## Template impact

Does this touch `master-ops/`? Generated operations repositories are copies made at onboarding and do not pick up template changes. Say what an existing install has to do. Otherwise write `none`.

If it does touch `master-ops/`, raise `master-ops/TEMPLATE-VERSION` and add an entry to `master-ops/CHANGELOG.md`. Without that, installs on different template states all report the same version and the version stops meaning anything.

## Notes

Platform, follow-up work, anything a reviewer should know.
