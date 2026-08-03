## Problem

State what happened before the change with counts, dates, paths, and the command used to observe it.
Rejected: "Docs were confusing."
Accepted: "On 2026-08-03, loading `master-ops/ONBOARDING.md` (524 lines) twice made a worker ignore its own 'load one step file per turn' rule in terminal replay."

## Why this approach

Name at least one alternative not taken and why, or name the constraint that forced this choice.
Rejected: "This felt cleaner."
Example: "Split one box into four fixed headings so missing reasoning appears as an empty section during review."

## What this changes

- List concrete file-level changes and what is intentionally out of scope.
- Use bullets only in this section; do not write a paragraph.
- Rejected: "Updated the template a bit and left other things alone."

## Expected effect

State what a reviewer can observe now and where to check it, using a path or command.
If the effect is not observable yet, state what event would make it observable.
Rejected: "This should improve PR quality eventually."

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
