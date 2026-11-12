# chore: Fable 5.2 defaults

## Summary

Claude master onboarding and succession now recommend and default to `claude-fable-5-2`.

## Changes

- `model-tier-policy.json` lists `claude-fable-5-2` in `tiers.top` and retains the prior Fable identifiers for compatibility.
- Onboarding recommends `claude-fable-5-2` for the Claude master candidate.
- `master-succeed` and `spawn_successor` agree on `claude-fable-5-2`, while an explicit model remains authoritative.

## References

- Issue: #252
