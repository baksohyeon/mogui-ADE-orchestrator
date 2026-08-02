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

When a change touches `master-ops/`, raise `TEMPLATE-VERSION` and add an entry
here in the same change. Skip that and installations on different template
states all report the same version, which is the whole thing this was meant to
prevent.

## 5

Onboarding now requires Orca infrastructure and uses Orca orchestration for all
supervised dispatch. A new read-only-by-default `scripts/onboarding-preflight.sh`
checks Orca status, the orchestration RPC, the global `orca-cli` and
`orchestration` skills, Beads resolution when an ops repository exists, and
Python before onboarding proceeds. `ONBOARDING.md` is rewritten as a token-lean
script-and-command flow while retaining its questions, safeguards, and
verification gates; `--fix` may add or refresh only the required global skills.

Upgrade an existing installation in this order:

1. Pull template v5 in the orchestrator clone.
2. Run `bash scripts/onboarding-preflight.sh` from that clone and fix every FAIL.
3. Enable Orca orchestration, then verify the preflight reports its RPC reachable.
4. Install the required skills with `npx skills add stablyai/orca -g`; refresh the
   orchestration skill with `npx skills update orchestration -g` when needed.
5. Raise the installation's `Template version` line in
   `docs/MASTER-OPERATIONS.md` to 5 after applying the relevant local changes.

Existing local edits still win. From this version onward, raw terminal polling
and vendor-direct agent CLIs do not satisfy supervised dispatch: bind a Run,
create a Task, attach a worker Dispatch, and wait for `worker_done` through Orca
orchestration.

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
