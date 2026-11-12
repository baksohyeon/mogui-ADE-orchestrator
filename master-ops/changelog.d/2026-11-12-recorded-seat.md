# feat: resolve succession spawn from the recorded seat path

## Summary

Onboarding records the stable master seat path in the instance runtime config, and `master-succeed spawn` resolves the current live Orca workspace selector from that path when no selector is supplied.

## Changes

- `master-succeed spawn` refuses when the recorded path has zero or multiple live workspace matches and keeps explicit selector overrides available.
- Onboarding step 3.5 and the public lifecycle guide document the path record and runtime resolution.
- Tests cover one match, zero matches, multiple matches, explicit override, and the missing-record fallback.

## References

- Issue: #216
