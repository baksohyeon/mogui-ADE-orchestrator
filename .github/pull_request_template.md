## Summary

What changed, and what made it necessary.

## Testing

- [ ] `PYTHONPATH=src python3 -m pytest tests -q` — paste the count
- [ ] A test that fails without this change, or a note on why none was needed
- [ ] New files staged before running any scan. The scanners read tracked files, so an unstaged addition is invisible to them and the run comes back green without having looked at it.

## Review

If you ran a review, automated or otherwise, say what it flagged and what you did. Say which findings you reproduced yourself. A review is a claim until it is measured.

## Template impact

Does this touch `master-ops/`? Generated operations repositories are copies made at onboarding and do not pick up template changes. Say what an existing install has to do. Otherwise write `none`.

## Notes

Platform, follow-up work, anything a reviewer should know.
