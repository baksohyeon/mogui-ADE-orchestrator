# Contract conventions

Reusable clauses for worker contracts under `contracts/`. Each one exists because
something went wrong without it. Copy the clause, do not paraphrase it: the precision
is the part that works.

## Why this file exists

A worker contract is the only thing standing between an instruction and an agent that
will follow it literally. Every clause below was written after a worker did exactly what
a vaguer contract permitted. The failures were not carelessness on the worker's part.
They were interface defects on the master's part, and they are fixed here rather than in
a reminder nobody re-reads.

## The rule that generates the rest: an unstated convention is not a convention

The contract is the worker's entire world. It has no memory of yesterday, no sense of the
house style, and no way to notice that something obvious to the master was left out. Where
the contract is silent the worker still has to choose, and it will choose reasonably and
differently.

Measured on 2026-08-03, three times, each in a place the master considered too obvious to
write down:

- Absolute paths. The contract named the forbidden checkout precisely and the required
  worktree vaguely. Four workers landed in the master's primary tree.
- Review replies. The contract said to handle the threads. A worker posted one
  pull-request-level comment and resolved all four silently, which satisfies the sentence
  and loses the record.
- Title format. The contract specified the assignee and banned internal tracker
  identifiers, then said nothing about conventional commits. The title came back as a
  capitalised imperative, correct for some other project.

Every one of those is a place the master thought "they will know". None of them cost the
worker anything to get right once it was written down.

The working test when drafting a contract: for each instruction, ask what a competent
stranger would do with only this sentence and no other context. Where more than one
reasonable answer exists, that gap is the specification, and it belongs in the contract
before the worker finds it. This rule is why the clauses below exist, and every future
clause will come from the same place.

## 1. Workspace clause: name the worker's own path, and the forbidden one [measured]

Grade basis: measured on the authoring instance via worker-contract artifacts that require
first-action `pwd` plus `git branch --show-current` and an explicit forbidden-path stop
condition, including `contracts/2026-08-03-windows-ci-measurement.md`,
`contracts/2026-08-03-cursor-worker-pretrust.md`, and
`contracts/2026-08-03-worker-host-diversity-redispatch.md`.

Give the absolute path the worker must work in, and name the master's own checkout
explicitly as a stop condition.

Naming the forbidden path precisely while describing the required one vaguely produced
four contaminations of the master's primary working tree in one day. Both paths must be
exact.

**Ask for the verdict, never the path.** The first action reports whether the worker is
in the right place, not where it is:

```text
FIRST ACTION (report these three, and no absolute path):
- in_expected_worktree: yes|no   # cwd contains the `.orca/worktrees/<repo>/<slug>` segment
- is_master_checkout:   yes|no   # yes stops the contract immediately
- branch:               `git branch --show-current`
```

This clause used to require `pwd` in the report, and on 2026-08-05 that is what put
home paths into PUBLIC repository history. The measured exposures were
`mogui-agent-harness` commit `c332386` (`pwd = /Users/<owner>/.../harness-survey-0805`)
and `mogui-ADE-orchestrator` commit `f0eed0e`
(`**pwd:** /Users/<owner>/.../onboarding-lane-0804`). Both workers complied exactly;
the contract instructed the disclosure. Redaction later moved the orchestrator branch
forward at `75cd043`, and the owner accepted the existing public exposure on
2026-08-05, but the template defect remains unless this clause changes.

An absolute path is still correct in the contract *to* the worker, because the master
sends that exact target downward and the worker must know where to stand. It is not
correct in the worker's report, commit message, pull request, or review reply, because
those are the surfaces where the path leaks back out. The asymmetry is deliberate:
paths flow down, verdicts flow up.

For ops-repository work, create an isolated `git worktree` first. The master's own
checkout is not a workspace to lend out.

## 2. Batching clause: group the work, do not iterate it [measured]

Grade basis: measured on the authoring instance via batched-thread procedure artifacts in
`contracts/2026-08-03-pr66-rebase-and-gates.md` and
`contracts/2026-08-03-pr67-threads-takeover.md`, which require one pull of all
threads, grouped fixes, per-thread replies, and end-of-round verification.

When a task has many similar units (review threads, files, findings), require the worker
to batch rather than loop:

1. Pull every unit in a single query.
2. Group by file and by defect kind, and fix each group once.
3. Post the per-unit responses back to back.
4. Run the gates once at the end, not per unit.

Two things are never traded for speed, and the contract must say so: **one reply per
thread**, and the task's own verification steps. Everything else is throughput.

What those replies should sound like lives in [Review voice](review-voice.md).

Iterating eighteen threads one at a time costs roughly an order of magnitude more turns
than batching them, and the extra turns buy nothing.

## 3. Takeover clause: inheriting is not starting [machine-enforced]

Grade basis: machine-enforced duplicate-contract rejection is backed by dispatch-gate
hash ledger enforcement, wired by the workspace dispatch command and enforced by
`{{RUNTIME_ROOT}}/scripts/dispatch-gate`.

When a worker takes over from a tired or dead predecessor, say so in the contract and
state what already exists:

- If a reply is already posted on a thread, read it, confirm it, and resolve. Do not
  write a second reply over it.
- If the predecessor left a branch with no commits, say that plainly so the worker does
  not go hunting for partial work that was never there.
- Require a commit before the report. An uncommitted working tree is not a deliverable,
  and a worker that dies before committing leaves nothing behind.

A takeover needs its own contract file. The dispatch gate ledgers by contract hash and
will reject a recent re-dispatch of the same contract as a duplicate inside its duplicate
window, which is correct: the second run is not the same job. After that window, the gate
may allow the same hash again, so the contract still has to state whether this is a
takeover and what evidence already exists.

## 4. Pull request narrative clause [measured]

Grade basis: measured on the authoring instance via pull-request body artifacts and
contract requirements, especially
`contracts/2026-08-03-pr-template-narrative-sections.md`, which requires the four named
sections and reviewable accepted/rejected examples.

A pull request body is read by people who were not in the room. The repository template
carries four named sections, and a contract must require them by the same names. Short
bullets, measured facts, no essay:

- **Problem.** What was happening before, and how the worker knows. Counts, dates, paths,
  the command that was run. A description of a feeling is not a problem statement.
- **Why this approach.** Why this way and not another. At least one alternative not taken
  and the reason, or the constraint that dictated the choice.
- **What this changes.** The change, and what it deliberately leaves alone.
- **Expected effect.** What a reader can now observe that they could not before, and the
  command or path that shows it. If it is not observable yet, say what would make it so.

The section names in the contract must match the template exactly. When a contract and a
template use different words for the same section, a worker fills one and drops the other.

The system reasoning is the valuable part of the work, and stripping it leaves a diff
nobody can evaluate. Someone reading the repository cold should be able to follow why
this change exists without asking anyone.

Guidance text in the template carries a failure example per section. A section that only
says "write this well" gets a worker's own judgement of well. A section that shows a
rejected sentence gets the worker comparing their draft against it.

Keep the house rules alongside it: assignee set at creation, no internal tracker
identifiers in the title, traceability in a body provenance line, and the body updated to
current state rather than the state at opening.

Titles follow conventional commits: `<type>: <lowercase description>`, where type is one
of feat, fix, docs, refactor, test, chore, perf, ci. Spell this out in the contract rather
than assuming it. A worker cannot follow a convention the contract never states, and a
title written without it reads as a different project's work.

## 5. No maintainer oracle [prose]

Grade basis: no current hook, linter, or gate in this template reads worker
reports to block unresolved maintainer handoff language or unverifiable claims.

Never write "leave it for a maintainer" into a contract. Give the ladder instead:

1. Run it read-only and measure what it actually does.
2. If it cannot be measured, delete the claim. An unverifiable sentence is worse than no
   sentence.
3. Only if deleting costs the reader something real, ask the coordinator a specific
   question carrying the exact claim, what was tried, and the two candidate readings.

A report must not end with unresolved items parked for someone who does not exist.

## 6. Merge stewardship clause [measured]

Grade basis: measured on the authoring instance via stewardship artifacts in
`contracts/2026-08-03-windows-ci-measurement.md` and
`contracts/2026-08-03-cursor-worker-pretrust.md`, which require the four
merge-readiness measurements and exact blocker reporting when not ready.

The worker that opens a pull request stewards it to merge-ready. The master does not poll
checks. Polling is mechanical work that produces no judgement, and every poll spends the
master's context on something a worker can watch for free.

Require the worker to hold the pull request until all four are true, then report the
verdict once:

1. Every check has a non-empty conclusion. An empty conclusion is pending, not pass.
   Read the rollup by entry type before concluding anything is pending. A rollup mixes
   `CheckRun` entries, which carry `name` and `conclusion`, with `StatusContext` entries,
   which carry `context` and `state` instead. Asking for `name` and `conclusion` on a
   `StatusContext` yields `null` and an empty string, which is indistinguishable from a
   check that has not finished.

   Evidence, 2026-08-03: five pull requests were sampled at one moment, and in that sample
   every entry carried a state once read by the right field, including the one that had
   looked permanently pending. That entry was `CodeRabbit` arriving as a `StatusContext`.
   Five pull requests at one moment is a small sample and does not establish that no
   integration will ever stall, so treat this as a reason to check the field selection
   first rather than as proof that a pending entry is always a misread.

   The master wrote an earlier version of this clause naming CodeRabbit as a non-reporting
   bot, on a single observation, and a worker built that claim into a tool's exclusion
   list. The claim was stated with more confidence than one observation supported.

   So the first move is to check the field selection rather than to add the entry to a
   list of excused integrations. An exclusion list carries a standing risk: it would hide a
   genuinely stalled check on the day one appears. If an entry still looks stuck after the
   query is correct, that is worth investigating on its own rather than excusing.
2. Zero unresolved review threads, each with its own reply.
3. A fetch of `origin/main` merged in, with no conflict left behind.
4. The three gates re-run after that merge, with counts.

Whatever those four surface, the worker fixes it in the code itself. A failing check gets
debugged and corrected. A bot round gets each finding fixed and each thread replied to
individually. A conflict gets resolved in the file. The clock restarts after every push,
and the worker keeps going until the four hold.

Reporting a problem is not handling it. A worker that reports "checks are failing" or
"the bot left three comments" has described the work rather than doing it, and the master
would then have to dispatch a second worker to fix what the first one found.

The worker reports `READY` with the four measurements, or reports the exact blocker with
what it tried and why it could not proceed. The merge itself stays with the master,
because merging is outward-facing.

## 7. Merge ordering [prose]

Grade basis: no existing pre-merge overlap guard or merge preflight script was
found that reads both branch file sets and enforces a declared conflict plan.

Before merging two open pull requests in sequence, compare the file sets they touch. If
they overlap, merging the first makes the second conflict, and the second's worker has to
be sent back over ground it already covered.

Measured 2026-08-03: two pull requests were merged back to back with an overlapping file
set. The first went in clean, the second turned `DIRTY` in the same minute, and its worker
made a second pass at a conflict that one comparison would have predicted.

Two ways out, and the choice belongs to the master rather than to either worker:

- Tell the second worker to merge the first branch in before the first lands, so the
  conflict is resolved once and against a known state.
- Merge one, then send the second worker back with the reason stated up front, including
  which structure the winner introduced and where the loser's content should move to.

The failure mode this prevents is not the conflict. Conflicts are ordinary. It is the
worker discovering the conflict without being told why it appeared, and resolving it
toward whichever side it read first.

## 8. Verification clause [measured]

Grade basis: measured through count-based verification requirements and
recorded counterexamples in this runbook, plus operational artifacts such as
`contracts/2026-08-03-pr66-rebase-and-gates.md` that require non-empty check
conclusions and explicit gate counts.

Require counts, not adjectives. "Gates pass" is not a report; "448 passed, redaction scan
OK, inventory exit 1 with baseline 445" is. Require the worker to read exit codes from the
command itself rather than through a pipe, and to treat an empty check conclusion as
pending rather than as failure.

Name the command whose count you want, and require the worker to report the command next
to the number. A count without its command is unverifiable: on 2026-08-03 a worker
reported "pytest 2 passed" as its gate result after running only the test file it had
added, against a suite of roughly 450. The number was honest and the gate was not met. It
was caught only because the same worker had reported 450 on an earlier pass, which is luck
rather than a check.

### The reading surface is not the thing

Behind every verification failure recorded here sits one mistake, and it is worth naming
on its own because it does not look like a mistake while it is happening.

A surface that reports success is not the thing that succeeded. The two are separate, and
the surface can be healthy while the thing behind it is absent, stale, or somewhere else
entirely.

Measured on 2026-08-03, three times in one day, each wearing a different costume:

- An exit code read through a pipe belonged to the pipe. The audit said no drift; the
  audit had actually found a real model transition and exited 1.
- A mailbox read from the wrong Run returned old heartbeats and no results. The reports
  had arrived on time, at an address nobody was reading, while the master told the owner
  they had not come.
- An acknowledgement flag returned the same batch on every call. The queue looked drained
  and was not, so a wait loop re-read work it had already handled.

Add a fourth from the same week: a dispatch record reported an injected task against an
agent still sitting on its startup screen.

The habit that prevents all four is one question asked before trusting any green signal:
**what exactly did I just read, and is it the thing itself or a report about the thing?**
When the answer is the second, verify against the thing. Read the terminal, not the
dispatch record. Read the command's own exit code, not the pipeline's. Confirm which
address a report was sent to before concluding it was never sent.

This applies to the master more than to any worker, because the master is the one reading
surfaces all day and has nobody downstream to catch a misread.

## 9. Document reference clause [measured]

A reference from one document to another is written as a real markdown link:
`[readable title](relative/path/to/target.md)`. A path wrapped in backticks is not a
reference; it is a string that happens to look like one.

The reason is navigation. An agent reading a document follows links. A backticked path
has to be recognised as a path, resolved against the reading agent's guess about which
directory the document lives in, and then opened on a hunch. Each of those steps is a
place to fail silently, and the failure looks like the reference was never there. Wiki
brackets have the same defect with a nicer face: they name a target without saying where
it is.

Backticks stay where they belong: code identifiers, flags, commands, literal values,
and file names being discussed as names rather than as destinations. The test is whether
a reader is meant to *go* there. If yes, it is a link.

Basis: owner instruction 2026-08-05, after measured runbooks were found carrying document
references in backticks, including a file written that same day whose whole subject was
making guidance reachable. The convention already existed in places and went unfollowed
elsewhere — an unstated form is not a convention. Those references were converted, each
checked against the file it claimed to point at. When a target lives in another
repository and no relative path resolves to it, say so in the sentence rather than
emitting a link that goes nowhere; that case stays described as a name, not linked.

Verify the links, do not assume them: resolve each target relative to the file that
contains it and confirm the file exists before committing.

## 10. Working directory clause [measured]

Every runnable command in a document states the directory it runs from, and a document
that contains more than one command uses one base for all of them. Prefer forms that do
not care where the shell is: `git -C <path>`, `gh --repo <owner/name>`, absolute paths.
A script that needs its own repository should anchor on its file location, not on the
invoking cwd, so that callers are free to stand anywhere.

A relative path is only half an instruction. The other half is the base it resolves
against, and when that half is unwritten the reader supplies it by guessing. This is the
same defect as a document reference in backticks, one layer down: the string looks
complete and silently means something different depending on where it is read.

Basis, measured 2026-08-05 on the authoring instance. A document's spawn and
duplicate-check steps were written against the workspace root while its seat-check step
was written against the ops repository, and nothing in the document said to move between
them. No single directory satisfied the document, so a successor following it in order
would hit a false failure at whichever step did not match, and the failure would look
like a broken tool rather than a broken path. The same day, a shell left inside a product
checkout made `git archive` resolve against the wrong repository and made a stale
worktree ref read as canonical — twice, in the space of one session.

The fix is in that order: make the tool location-independent, then state one base, then
write the commands. A self-check that needed its own repository was changed to anchor its
repo-relative paths on its own file location and verified to produce byte-identical
output and exit 0 from three different directories; its regression suite still passed.
Only after that could the document's two bases be merged into one. The document can name
a single base only once the tool no longer inherits the invoking cwd.

Never leave the shell parked somewhere other than the seat. Reaching a repository is not
a reason to move into it.

## 11. Public-surface redaction clause [measured]

Grade basis: measured incident (2026-08-04, second occurrence) — workers copied absolute
home paths (`/Users/<name>`) verbatim into PR bodies and review replies; repository
redaction CI scanned tracked content only, so conversation surfaces shipped the leak;
the owner swept public forge text by eye.

Worker-authored text on any public forge surface — PR bodies, comments, review replies,
commit messages — never contains absolute machine paths or identity-bearing strings.
Evidence quotes use placeholder form (`~/path`, `<home>`) instead of literals. Run the
body checker before `gh pr create` or `gh pr edit`; repository scanners do not read forge
conversation surfaces.

## 12. Context-injection policy [measured]

Grade basis: measured owner decision (2026-08-04) after instruction-stacking drift:
per-turn hook injection of the rules would make succession measurement less honest and
would spend prompt budget on an answer sheet.

Do not solve rule drift by injecting the whole constitution or contract-conventions
runbook into every turn. Context injection stays minimal: role-state and the smallest
active execution rule may be surfaced for boot or recovery, but canonical rule text lives
in Git and drift is handled through canon text plus post-hoc observation such as fire logs
and retros. A contract may require reading the relevant canon section; it must not require
building a per-turn rule bundle.

## 13. Chat-to-docs rule [prose]

Grade basis: owner directive (2026-08-04); no current hook decides whether an explanatory
chat answer should become documentation.

An explanation written in chat to resolve owner confusion is a documentation candidate by
default. The worker should judge in the same work cycle whether it belongs in public
template docs or operations guides and route it there when recurrence would cost more
than the doc change. Chat is not a documentation surface.

## 14. Merge-time re-measurement [measured]

Grade basis: one merged-with-unread-findings incident followed by four valid catches from
the same night's re-measurement duty.

At merge time, re-run the thread and review measurements instead of trusting the last
worker report. Compare `reviews[].submittedAt` with the last measured time; any bot
review submitted after that measurement must be read in full before merging. A clean
worker report is stale the moment a later bot review exists, and merging before reading
that later review is a missed finding, not an accepted risk.

## Grade distribution (2026-08-05)

- machine-enforced: 1
- measured: 10
- prose: 3

Distribution is non-uniform, so these grades are based on enforceability and
observable evidence rather than intent.

## Backlog: raise every prose clause

- Clause 5 (`No maintainer oracle`): add a worker-report oracle lint in the generated
  operations repository's `scripts/`; read each `worker_done` body artifact and fail when
  unresolved maintainer-handoff language appears without an escalation id and attempted
  measurement record.
- Clause 7 (`Merge ordering`): add a pre-merge overlap check in the generated operations
  repository's `scripts/`; read branch file sets from
  `git diff --name-only origin/main...<branch>` for both pending branches and require an
  explicit strategy token (`pre-merge` or `redispatch`) when overlap is non-zero.
- Clause 13 (`Chat-to-docs rule`): add a review checklist item that asks whether any
  owner-confusion answer in the run should land in docs before the PR is opened.
- Honest limit: these clauses remain prose today because no current gate in this repository
  reads those artifacts during dispatch or merge flow.
