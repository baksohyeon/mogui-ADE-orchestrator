# master-ops template changelog

The version in `TEMPLATE-VERSION` is the version of this template. Onboarding
copies it into the operations repository it generates, so an installation can
say which version it came from.

A generated operations repository is a copy. It does not update when this
template does. To bring an existing installation forward, read the entries
between its version and the current one and apply what applies. Local edits win
where they conflict; that is the point of a copy.

Check what an installation is on, from the root of the generated operations
repository:

```console
$ grep 'Template version' docs/MASTER-OPERATIONS.md
```

This file is not in that repository. Step 3 keeps it out, so it stays in the
orchestrator clone alongside the template it describes.

When a change touches `master-ops/`, add an entry under `## Unreleased` in the
same change. `TEMPLATE-VERSION` moves only when a release is cut, and it holds
that release's tag string. The repository's existing scheme continues, so the
release after `v0.1.0` is `v0.2.0`. Merging a change is not releasing it, and
between releases this file keeps whatever the last release left in it.

Skew is decided by comparing that string with the latest release tag for
equality, never by comparing magnitudes. The integers 3 through 6 in the entries
below are transitional numbers from before this file tracked releases; an
installation still reporting one of them is caught the same way as any other
mismatch, by not equalling the latest tag.

One consequence to keep in mind while reading an installation's version line: an
installation onboarded between releases carries unreleased entries while
reporting the last released tag, so that value names the release it came from and
not the exact body it received. When the difference matters, record the commit the
installation was taken from alongside the tag.

## Unreleased

`docs/MASTER-OPERATIONS.md` gains an Incident-Derived Rules section: eleven
rules, each carrying the observation that produced it and the measurement that settles
it. The Closed Principles Pointer moves from section 8 to section 9.

The rules were already being applied across the preceding versions; what was
missing was their evidence. A rule stated bare gets argued away by the next
reader, who has not seen the failure it came from, and a rule with no
measurement cannot be checked at all. Both halves are therefore mandatory for
anything added to that section.

The rules cover what the recent template versions were built against:
reachability is not capability and a record is not an effect; silence is not a
pass; a declaration is not a measurement; put the guard where the incident was;
say whether a constraint came from availability or from policy; fix the pair or
the survivor lies; a green light must name its scope; a gate nobody can pass is
a gate nobody runs; do not read a blocker, test it. Two are about the work
itself rather than the system: a squash merge erases the base a stacked branch
was built on, and reverting a file discards work that was never committed.

Upgrade an existing installation by copying the new section into its operations
SSOT and renumbering the Closed Principles Pointer. The installed `Template
version` line moves at the next release tag rather than here. An installation
that has its own incidents should
append them in the same form rather than replacing these: the section is meant
to accumulate, and a rule earned locally outranks one inherited from a template.

## Unreleased

The tier policy gains a version 2 shape that gates on tier multiplied by fan-out
instead of on model identity. The incident this policy exists for was a top tier
spread across ten workers, and identity was the wrong axis for it in both
directions: a single top-tier dispatch passed, while `unknown_model: "deny"`
blocked every model the file had not been hand-edited to name, including cheaper
or stronger ones released later.

A version 2 policy lists `tiers` and a `fanout_caps` entry per tier, plus a
required cap for `unknown`. A model in no tier is `unknown` and capped there
rather than denied, so a new model is usable once before anyone edits the file,
and never silently: the tier lands in the ledger, the decision carries a
`TIER_UNKNOWN_MODEL` warning distinct from a denial, and `report` prints an
`unknown` row labelled as allowed without a known tier. Exceeding any cap still
requires `--tier-override "<reason>"`, which is recorded as before.

The cap counts accumulation inside `window_seconds`, not concurrency. Ten
sequential single-agent dispatches therefore reach the same cap as one fan-out of
ten, because the cost the window measures does not care whether the workers
started together. An override passes one request without refunding what the
window already counted.

Version 1 policies load and behave exactly as before, so upgrading the runtime
alone changes no verdicts. Migrate by rewriting the file to version 2 with the
models this host actually offers, measured rather than copied from the template
default.

The gate also stops mixing its two output streams in a way that reads as one:
the verdict remains JSON on stdout, and every human diagnostic on stderr is now
prefixed with `dispatch-gate: `. Callers must not merge the streams, since
`2>&1` into a JSON parser fails and an unprefixed reason code made that look like
malformed output rather than a second stream.

Upgrade an existing installation by rewriting `master-ops/model-tier-policy.json`
in the version 2 shape and re-reading the dispatch section of
`docs/MASTER-OPERATIONS.md`. The installed `Template version` line moves at the
next release tag rather than here.

## 6

The dispatch gate now enforces the installation-specific
`model-tier-policy.json` fail closed, records justified tier overrides in its
ledger, and provides a stable plain-text `report` rollup for model use, cost
proxy, denials, overrides, and time span. Existing installations should copy
and customize the policy file before adopting this gate version.

Model identifiers are matched casefolded, because exact-string membership let a
case variant of a denied tier miss the denied set and pass as a warning wherever
`unknown_model` is `warn`. Every check entry also records `tier_policy_path` and
`tier_policy_sha256`, and `report` lists each policy a span was judged against:
the policy path is caller-supplied through `--tier-policy` or
`DISPATCH_TIER_POLICY`, so without that identity an allowed top-tier dispatch
cannot be told apart from one a substituted policy allowed. More than one policy
row in a day's rollup is the signal.

Upgrade an existing installation by copying `master-ops/model-tier-policy.json`,
re-running `bash scripts/onboarding-preflight.sh`, and raising the installed
`Template version` line to 6.

## 5

Onboarding now requires Orca infrastructure and uses Orca orchestration for all
supervised dispatch. A new read-only-by-default `scripts/onboarding-preflight.sh`
checks Orca status, orchestration capability, the `orca-cli` and
`orchestration` skills, Beads resolution when an ops repository exists, and
Python before onboarding proceeds. It also gates the rest of the tool surface a
master and its workers actually invoke: the named agent CLI, the worker runtimes
dispatch targets, Git, an authenticated `gh`, a runnable test entry point, a
writable dispatch ledger directory, and the organization rules file.

Enforcement is graded rather than absolute, because a check that cannot be
satisfied and cannot be waived teaches the operator to skip the whole preflight
and lose every other check with it. `PREFLIGHT_WAIVE=<labels>` downgrades named
failures to printed, counted waivers, and the summary then reads READY WITH
WAIVERS and lists them: a waived required check was not satisfied. Entries that
match no check are named as well, since a misspelled waiver leaves the check
enforced while the operator believes otherwise. Two checks are graded on their
own: a missing worker runtime warns when another listed runtime resolves, and
`gh` blocks only when the binary is absent, while unauthenticated or a missing
`workflow` scope warns.
`ONBOARDING.md` is rewritten as a token-lean script-and-command flow while
retaining its questions, safeguards, and verification gates; `--fix` may add or
refresh only the required global skills. Template v5 also adds the append-only
`scripts/codex-worker-pretrust` helper so every Orca Codex account trusts a
worker worktree before dispatch.

Two of those checks measure differently than a first reading suggests, because
both were wrong in the first cut. Orchestration is judged by capability, not
reachability: a retained legacy coordinator answers reads and drops writes with
`effectsApplied:false`, so `run-current` must report a bound non-legacy Run.
Skills are judged by the artifact, not the installer: the required skills can
resolve on a host that has no `skills` package manager at all, and an installer
listing that cannot run is not evidence of absence.

The organization rules file moves from optional to required, since two of the
three publish gates refuse to run without it. The preflight validates its format
and reports counts only. It never prints a rule, an identifier, or a match,
because that file's contents are what the scanner protects. The format is one
rule per line as `id|description|regex`, `#` comments and blank lines skipped,
split on the first two pipes only so the regex may contain `|`, and every regex
must compile: the inventory drops uncompilable rules without reporting them, so
a malformed rule narrows coverage while the file still looks populated.

The minimum Python version is now 3.11 because the pre-trust helper uses the
standard-library `tomllib` parser to make config edits safely.

The v5 upgrade contract also adds governance rules to the template: Orca is
required infrastructure, neutrality covers only artifact formats and agent
swappability, PR review-bot threads are worker-handled by standing delegation,
and supervised dispatch is vendor-neutral Orca orchestration only. Existing
installations should add these rules to their operations SSOT when applying the
v5 upgrade; accidental out-of-orchestration work must remain plainly recorded.

Upgrade an existing installation in this order:

1. Pull template v5 in the orchestrator clone.
2. Run `bash scripts/onboarding-preflight.sh` from that clone and fix every FAIL;
   re-collect and confirm the workspace facts before routing work.
3. Before each Codex worker attach, run `scripts/codex-worker-pretrust <worktree-path>` from the orchestrator clone.
4. Enable Orca orchestration and bind a Run with `orca orchestration run-create`,
   then verify the preflight reports a non-legacy Run bound to this terminal.
5. Select or create the approved ops repository, then verify `bd where` from the
   workspace root resolves to it and no tracker root is selected above it.
6. Replace all template placeholders, verify `CLAUDE.md` and `AGENTS.md` are
   byte-identical, and make settings and security-sensitive hook ownership
   explicit before enabling anything.
7. Install only the required skills with
   `npx skills add stablyai/orca -g --skill orca-cli --skill orchestration`;
   refresh the orchestration skill with `npx skills update orchestration -g`
   when needed.
8. Raise the installation's `Template version` line in
   `docs/MASTER-OPERATIONS.md` to 5 after applying the relevant local changes.

Existing local edits still win. From this version onward, raw terminal polling
and vendor-direct agent CLIs do not satisfy supervised dispatch: bind a Run,
create a Task, attach a worker Dispatch, and wait for `worker_done` through Orca
orchestration. Finish by spawning exactly one verified Generation 1 master
through Orca and have that master perform the Step 9 first-boot smoke, including
role, model, placement, lineage, and completion evidence.

## 4

The Step 8 spawn gate accepts MATCH_REISSUED alongside MATCH (in `ONBOARDING.md`
only, not copied into installations). The runtime's spawn now verifies the
returned terminal handle is live, because Orca reissues handles between creation
and first use — observed on both founding spawns of 2026-08-02. When the
reported handle is stale and exactly one new terminal in the requested worktree
carries the pane title, the spawn adopts that handle and reports
MATCH_REISSUED with `handle_reissued: true`; a gate that requires the literal
MATCH would reject exactly the case the verification exists to survive.

Installations copy nothing for this version; only the onboarding flow changed.
An installation on version 3 raises the `Template version` line in
`docs/MASTER-OPERATIONS.md` to 4 if it wants to record currency.

The Step 8 failure contract is fail-closed: it does not retry with a filesystem
path selector and does not boot the master in the installer session.
Disconnected, zero-candidate, or ambiguous (2+) candidates fail closed without
terminal cleanup.

## 3

The operations card (`CLAUDE.md`/`AGENTS.md`) gains an owner-communication
rule: tracker issues are referred to by title with the ID in parentheses, never
by bare ID, and charter vocabulary gets one plain clause of explanation on
first use. Added after a production master proposed "Maintenance 범위에서 74m
착수 승인" and the owner's reply was to ask, twice, what that meant.

Onboarding changes in the same spirit, in `ONBOARDING.md` (not copied into
installations, listed for completeness): an Orientation section before Step 0
that explains the system, the three layers, the step map, and the end state
before any question is asked; a position line opening every step; and Step 5
now explains the tracker's role and asks the user to choose the issue prefix
instead of silently taking the tracker's repo-name default.

An installation on version 2 applies this in two edits. Copy the new
communication bullet into both `CLAUDE.md` and `AGENTS.md` (they stay
byte-identical), then raise the `Template version` line in
`docs/MASTER-OPERATIONS.md` to 3.

## 2

One integrity rule added to `docs/observability/README.md`: an instruction to
leave something out of the record is itself recorded, along with what was asked,
when, and by whom. A request carrying a credential, token, or key is recorded as
metadata only, never as a value or a verbatim quote, and the gap is marked where
it was.

Two genres removed: `docs/field-notes/` and `docs/agent-journey/`. They were
carried while the authoring workspace worked out what the observability suite
should be, and neither paid for its tokens once it had. A generated repository
gets retro and travelog, and adds its own genre if a question stays unanswered.

An installation on version 1 applies this in two edits. Copy the new bullet from
`docs/observability/README.md`, then raise the `Template version` line in
`docs/MASTER-OPERATIONS.md` to 2. That line is how a later upgrade knows what
this installation already has; leaving it at 1 makes the next pass offer this
same change again.

Already running field notes or an agent journey? Nothing forces you to stop. The
template no longer ships them; your copy is yours.

## 1

First versioned template. Everything before this shipped unversioned, so an
installation created earlier will not carry a version line. Add one by hand
after applying whatever entries look relevant, and treat its starting point as
unknown.

The list below covers changes since the public release, not the whole history
of the template. An installation older than that should diff against
`master-ops/` directly rather than trust this list to be complete.

Notable content at this version:

- Section 1 states that a coordinated repository's agent instruction file does
  not declare the master's role. Added after a first-generation master read a
  product repository's instruction file and reported itself as that
  repository's paired developer.
- Section 3 says a boot measurement is a snapshot and names the points to
  re-measure at, with the whole-transcript audit for changes a recent-turn
  probe cannot see.
- Step 5 of onboarding wires the issue tracker to the workspace root, where the
  master actually runs, and verifies from there.
- Step 7.5 offers the skill layer and prints install commands without running
  them.
