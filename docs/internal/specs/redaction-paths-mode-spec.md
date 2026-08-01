# Redaction Scan Paths Mode Spec

Date: 2026-08-01

## Scope

This document specifies one addition to `scripts/redaction-scan.sh`: a `paths`
mode that scans an explicit list of files and directories instead of a
repository's tracked set.

Nothing else changes. `redaction-inventory` is not extended, no detector library
is adopted, and no new gate is wired.

## Problem

The scan modes are `tracked`, `staged`, and `range`. All three resolve their
target through git, so the unit of work is "a repository." The unit that
actually matters for a leak is "the set of things about to leave," and those two
only sometimes coincide.

Blog drafts, artifacts, and issue bodies are staged in a private repository and
published individually. Pointing the current scanner at that repository scans
everything in it, and a private operations repository is full of internal
identifiers by design. The result is a wall of findings that carries no signal,
so in practice the publish path goes unscanned.

Every leak this project has had came out of the publish path.

## Behavior

`--paths <path>...` selects `paths` mode. Each argument is a file or a
directory; directories are walked. Rule loading, matching, allowlisting, and the
`--require-extra` fail-closed behavior are unchanged, so a finding means the
same thing it means in `tracked` mode.

Output reports findings and exits 1 when any are present. It does not redact,
rewrite, block, or delete. What to do about a finding is the operator's call,
and a tool that decides for them will eventually decide wrong on something that
was fine.

The mode is run deliberately before publishing, as a separate invocation. It is
not wired to a hook. A blocking hook on an outbound action was considered and
rejected: the failure this is meant to prevent was a scan whose red exit was
read after the push had already happened, and the fix for that is separating the
two calls, not adding a third mechanism that also has to be right.

## Non-Goals

**Images.** No OCR. Screenshots that accompany published writing are reviewed by
a person. Documenting this is part of the work, because a scanner that reports
clean while never having looked at the images is worse than no scanner.

**Commit metadata.** Author and committer fields stay out of scope.

**Automatic identifier discovery.** Organization-specific identifiers are still
a hand-maintained rule list. `redaction-inventory` measures the holes in that
list; a person fills them.

## On PII Detection Libraries

Adopting a general PII detection library such as Presidio was evaluated and
declined for now.

Every identifier this project has actually leaked was organization-specific: a
company name, an internal repository name, a person's name. A general detector
does not know those, so they would arrive as custom recognizers, which is the
hand-maintained list again under a different name. The marginal detections a
general library adds, mostly structured national identifiers, correspond to no
content this project publishes.

The cost is concrete. The core is standard-library-only with no dependencies,
which this repository states as a property. A detector of that class brings an
NLP model stack.

Reopen if third-party personal data starts appearing in published output at
volume, or if structured identifier detection becomes a real requirement.

## Verification

- a fixture with seeded identifiers is caught in `paths` mode
- `--require-extra` still exits 2 when no organization rules load, in the new
  mode as well as the existing ones
- `tracked` mode output is unchanged
- a directory argument walks, and a file argument does not require a repository
