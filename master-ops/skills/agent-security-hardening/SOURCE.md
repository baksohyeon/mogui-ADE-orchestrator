# Source

- Origin: `affaan-m/ECC`, path `skills/agent-security-hardening/SKILL.md`, `https://raw.githubusercontent.com/affaan-m/ECC/b38be6a7f6350964d59328b52f0624e1d1d552d1/skills/agent-security-hardening/SKILL.md`
- Commit: `b38be6a7f6350964d59328b52f0624e1d1d552d1`
- Fetched: 2026-11-11
- sha256 (first 12): `0e0895ada90a`
- License: MIT. See `LICENSE` in this folder, a byte-for-byte copy of the upstream `LICENSE` at the same commit.

## Why this one

A trust-boundary checklist per side effect (`source -> parser -> validator ->
side effect`, with the identity and scope authorizing it, the validator that
runs just before it, size bounds, audit evidence, and a recovery path
recorded for each one) and a six-item verification gate, for reviewing an
agent runtime or tool gateway.

## Vendor-neutral reading

`SKILL.md` is unedited. No phrase in it is Claude-only; no mapping row is
needed. It names three other ECC skills this template does not vendor:
`security-review`, `security-scan`, and `agent-harness-construction`.

## Known gaps (upstream-only)

The template does not edit vendored text, so a fix to `SKILL.md` itself goes
upstream to `affaan-m/ECC` rather than into this file. One gap observed here:
the reserved-name regex in `workspace_path` (`WINDOWS_RESERVED_NAME`) matches
a reserved device name only when it is followed directly by `.` and an
extension, or by nothing; it misses one written with a space before the
extension, such as `NUL .txt`, which Win32 also strips and treats as the
plain reserved name.
