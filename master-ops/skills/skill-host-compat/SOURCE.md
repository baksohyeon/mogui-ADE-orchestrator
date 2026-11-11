# Source

- Origin: `affaan-m/ECC`, path `skills/skill-host-compat/SKILL.md`, `https://raw.githubusercontent.com/affaan-m/ECC/b38be6a7f6350964d59328b52f0624e1d1d552d1/skills/skill-host-compat/SKILL.md`
- Commit: `b38be6a7f6350964d59328b52f0624e1d1d552d1`
- Fetched: 2026-11-11
- sha256 (first 12): `246242187c2d`
- License: MIT. See `LICENSE` in this folder, a byte-for-byte copy of the upstream `LICENSE` at the same commit.

The companion command file `commands/skill-host-compat.md` is not vendored:
it is bound to a Node script and a Claude plugin path this template does not
ship.

## Why this one

The rule sentences that catch Claude-only variables (`${CLAUDE_SESSION_ID}`,
`${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`,
`$ARGUMENTS`) inside shell fences, and frontmatter keys outside `name,
description, metadata, license, allowed-tools`.

## Vendor-neutral reading

`SKILL.md` is unedited. Read Claude-only phrases this way:

| Phrase in `SKILL.md` | Vendor-neutral reading |
|---|---|
| `node scripts/ci/validate-skill-host-compat.js`, `/skill-host-compat` | not shipped; grep the five tokens above in shell fences when a check is needed |
| `.agents/skills/`, `.cursor/skills/` copies | no per-host copies in this template; the canonical `skills/` text is written host-neutral from the start |
