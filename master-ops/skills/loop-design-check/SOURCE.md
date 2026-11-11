# Source

- Origin: `affaan-m/ECC`, path `skills/loop-design-check/SKILL.md`, `https://raw.githubusercontent.com/affaan-m/ECC/b38be6a7f6350964d59328b52f0624e1d1d552d1/skills/loop-design-check/SKILL.md`
- Commit: `b38be6a7f6350964d59328b52f0624e1d1d552d1`
- Fetched: 2026-11-11
- sha256 (first 12): `d48c239c8b9f`
- License: MIT. See `LICENSE` in this folder, a byte-for-byte copy of the upstream `LICENSE` at the same commit.

## Why this one

A machine-decidable done criterion, a "must not" boundary, a retry cap, and a
hand-to-human condition, all in one place in a contract.

## Vendor-neutral reading

`SKILL.md` is unedited. Read Claude-only phrases this way:

| Phrase in `SKILL.md` | Vendor-neutral reading |
|---|---|
| `/loop`, `/goal`, `/schedule` | the same actions written as steps |
| dispatching and waiting on a loop's workers | `scripts/dispatch` and Orca orchestration |
| `autonomous-loops`, `continuous-agent-loop` | other ECC skills, not shipped here (they are vendor-bound to the mechanism layer) |
| "Claude Code sub-agents" | dispatched workers |
| "a main Claude" (loops, dispatching plan/build/judge) | a master or a dispatched worker |
| `CLAUDE.md` (bloated, stale memory) | the workspace card, or an install's own bootstrap file in general |
