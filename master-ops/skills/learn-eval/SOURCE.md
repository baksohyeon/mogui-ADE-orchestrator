# Source

- Origin: `affaan-m/ECC`, path `commands/learn-eval.md`, `https://raw.githubusercontent.com/affaan-m/ECC/b38be6a7f6350964d59328b52f0624e1d1d552d1/commands/learn-eval.md`
- Commit: `b38be6a7f6350964d59328b52f0624e1d1d552d1`
- Fetched: 2026-11-11
- sha256 (first 12): `130ca6269052`
- License: MIT. See `LICENSE` in this folder, a byte-for-byte copy of the upstream `LICENSE` at the same commit.

## Why this one

An end-of-note verdict line (Save / Improve then Save / Absorb / Drop) and a
pre-save duplicate checklist, applied before a learned pattern is written to a
skill file.

## Vendor-neutral reading

`SKILL.md` is unedited. Read Claude-only phrases this way:

| Phrase in `SKILL.md` | Vendor-neutral reading |
|---|---|
| `~/.claude/skills`, `.claude/skills` | the install's `skills/` folder |
| `MEMORY.md` | the master's memory index and tracker memories |
| "Claude uses the skill name and description" | the agent picks a skill by its name and description |
| `/learn-eval` | the same steps followed as prose |
| "Claude Code treats `<name>/SKILL.md` as the skill entrypoint" | the agent's own skill-discovery convention: a directory named `<name>/` holding `SKILL.md` |
| Design Rationale's "Opus 4.6+, including the Claude 5 families" | a frontier-tier model with strong contextual judgment, whatever the install actually dispatches to |

The "Global" (`~/.claude/skills`) versus "Project" (`.claude/skills`) distinction
in Step 3 does not carry over: this template keeps one canonical `skills/`
folder per repository, not a separate user-global location, so both save
paths in `SKILL.md` map to that same single folder rather than to two
different ones.
