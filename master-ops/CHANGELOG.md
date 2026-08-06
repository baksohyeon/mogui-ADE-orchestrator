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
below are transitional numbers from before this file tracked releases, and
`0.2.0` without the `v` is one more: the v0.2.0 release wrote the number instead
of the tag string, so an installation reporting it is caught the same way as any
other mismatch, by not equalling the latest tag. From v0.3.0 the file holds the
tag string exactly.

One consequence to keep in mind while reading an installation's version line: an
installation onboarded between releases carries unreleased entries while
reporting the last released tag, so that value names the release it came from and
not the exact body it received. When the difference matters, record the commit the
installation was taken from alongside the tag.

## Unreleased

Workspace session-card host twin and deployment (2026-08-06):

- Added byte-identical `workspace-card/AGENTS.md` alongside the canonical
  `CLAUDE.md` card.
- Onboarding, reverify, and harness self-check now validate the canonical pair
  against itself before checking both host-recognized root card names.
- Onboarding now stops and re-syncs the canonical pair before redeploying when
  those source files diverge.

Successor-facing promotion audit and redacted knowledge promotion (2026-08-06):

- Added the promotion inventory at `docs/internal/promotion-audit-2026-08-06.md` and
  redacted incident records under `docs/blame/`.
- Added the boot comparison procedure and public lineage entry format.
- Reconciled contract writing conventions and review voice through rule 11.
- Shipped the product-repository path guard and documented both host hook matchers.
- Promoted measured `agy` Gemini-host mapping and Antigravity folder-trust markers.
- Existing installations must merge these template changes deliberately; generated
  operations repositories are copies and do not update automatically.

Contract convention merge-time re-measurement and citation repair (2026-08-05 worker contract fix):

- Added clause 14, Merge-time re-measurement, so merge decisions re-run thread
  and review measurements, record `review_measured_at` immediately after
  fetching `reviews[]`, and compare later `reviews[].submittedAt` values
  against that timestamp before merging.
- Corrected the prose backlog citation for Chat-to-docs from clause 11 to
  clause 13 and removed the duplicate prose count in the grade distribution.
- Worker routing now calls `scripts/worker-reap --task-id <task-id> --ledger
  <ledger-path>` after a worker pull request merges and keeps ambiguous
  worktrees in place with a report.
- Existing installations do not auto-update. To adopt this entry, copy or merge
  `docs/runbooks/contract-conventions.md` and
  `docs/charter/04-worker-routing-review.md` into the generated operations
  repository and preserve local additions deliberately.

Review follow-up for successor promotion (2026-08-06):

- Product-path guard now supports an opt-in Bash policy inversion via
  `MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1`: any target normalized under the product
  root is denied unless its command class was measured as read-only in the event
  log; unresolved targets are denied with a reason. The flag is off by default so
  an unmeasured allowlist is never the default policy. The shipped allowlist is
  empty because the existing hook-fire log has 0 usable command observations;
  command observations now go to the separate event log, so the measured
  rejection report is `0/0`, N/A rather than an inferred rate.
  Symlink normalization, canonical `product_repo` configuration, runtime config
  resolution, configurable fire logs, and the requested bypass regressions are covered by
  `scripts/test-product-path-guard.sh`; run `scripts/measure-product-path-guard.sh`
  to report the live rate.
- The agy dispatch path now accepts its measured Gemini vendor mapping; the full
  runtime capability table remains a separate contract. `scripts/test-dispatch-runtime.sh`
  preserves this minimum behavior.
- Removed a UUID and corrected public-document wording and structure identified by review.

Dispatch policy and review voice promotion from operations repository
(owner directive 2026-08-05):

- `master-ops/scripts/dispatch` now passes measured model flags through to
  `codex`, `grok`, and `cursor-agent`, and uses `cursor-agent` rather than the
  `cursor` updater command.
- `dispatch --check-only` now calls `dispatch-gate check --no-record`, so dry
  runs inspect the real ledger without appending a row that later fan-out caps
  count as spent budget.
- The shipped tier policy no longer caps `top`; top-tier dispatch now asks the
  owner directly through `dispatch --top-approved "<reason>"`, while
  `unknown: 8` stays capped.
- `docs/runbooks/review-voice.md` now carries rules 8 through 10 and widens
  those rules to every written surface, including chat, commit messages, code
  comments, and self-checks.

Master tooling promotion from operations repository (2026-08-05 measurement,
provenance `mgm-w7m.5`):

- Promoted the measured operations `scripts/` tooling into the template so
  cards and runbooks that call `dispatch`, `measure`, `harness-selfcheck.sh`,
  collision checks, stewardship status, workstream rendering, spawn tests, and
  Orca surface checks have delivered files in fresh installs.
- De-instanced promoted scripts by replacing the source runtime root,
  operations repository, and workspace root with existing onboarding tokens.
  The substitution order is longest path first:
  `{{RUNTIME_ROOT}}`, then `{{OPS_REPO}}`, then `{{WORKSPACE_ROOT}}`.
- Kept the transcript probe default out of the template as a machine-specific
  mangled Claude path; `dispatch` now derives a Claude transcript glob from the
  worker worktree when it can be scoped, and otherwise records the probe as
  unavailable instead of inheriting the source machine's directory name.
- Left out `scripts/hooks/product-path-guard.sh` because it encodes the source
  owner's sibling product repositories and has no existing template token that
  can express that product list without leaking instance state.
- Existing installations do not auto-update. To adopt this entry, copy or merge
  the promoted scripts into the generated operations repository, keep local
  instance config files and tier-policy values local, and wire hooks only after
  confirming the target install's host settings.

Workspace session card onboarding (2026-08-05 owner decision; measured gap:
no step created the workspace-root session card):

- Skeleton: `master-ops/workspace-card/CLAUDE.md` (canonical session card with
  `{{...}}` placeholders) and `README.md` (canonical vs root deploy; link base
  is the workspace root, a deliberate exception to the working-directory
  clause). README carries no template placeholders (step 03 copies it into the
  ops repo; step 05 forbids leftover `{{...}}`). Not the ops-repo agent
  instruction pair and not step 10's owner operating card.
- Card points dispatch at charter §5 (`docs/charter/05-dispatch-gate.md`), not
  at a skeleton-absent wrapper path; review-bot routing cites charter §4.
- Step 05: fill every ops-repo token (no deferral), deploy the filled card to
  the workspace root as a Run action, then Verify (no-placeholder, ops pair,
  root-vs-canonical card). Placement is before `09-spawn.md`.
- Reverify check 6 matches (no deferral pass); check 7 reports root-vs-canonical
  drift only, never silent redeploy.
- Name disambiguation in steps 03, 05, 06, and reverify so nobody `cmp`s the
  wrong `CLAUDE.md` pair.

## v0.4.4

Promotion sweep 2A verified tools (2026-08-04 staging to template):

- New `master-ops/scripts/orca-wait`, `master-ops/scripts/hooks/bash-poll-warn.sh`,
  and `master-ops/docs/runbooks/orca-wait.md` carry the deliveryId
  ack-chain wait wrapper and hand-rolled poll-loop warning hook from the
  authoring operations instance.
- New `master-ops/scripts/conversation-redaction-scan`,
  `master-ops/scripts/pr-body-check`, and
  `master-ops/docs/runbooks/conversation-redaction.md` cover PR bodies,
  PR comments, review-thread comments, and issue bodies for
  conversation-surface home-path leaks without printing the matched value.
- Hook fire-log observability is promoted through fail-open fire-log calls in
  shipped hooks, the new `master-ops/scripts/hook-coverage-report`, and
  `master-ops/docs/runbooks/hook-fire-observability.md`; each hook appends one
  record before ordinary work, logging never blocks hook execution, and the log
  path resolves as `${MOGUI_HOOK_FIRE_LOG:-$HOME/.mogui/hook-fire-log.jsonl}`.
- New `master-ops/scripts/spawn-test` and
  `master-ops/docs/runbooks/spawn-test-harness.md` carry the real-agent
  installer E2E harness, including the founding-guard scenario because it was
  present in the source operations `main` checkout when this sweep started.
- Existing installations do not auto-update from this template. To adopt this
  entry, copy the new scripts and runbooks into the generated operations
  repository, wire any host hooks deliberately, set the spawn-test coordinator
  environment for local runs, and merge local edits by hand.

Agent-inventory consent and default-on harness wiring (2026-08-04 owner
decisions, two onboarding gaps):

- Step 01 asks consent to probe installed agent CLIs with both purposes stated
  (task↔model strength matching; top-tier fan-out cap). On yes, measure
  runtimes/versions/model ids (never guess; use `unknown`); on no, write only
  owner-named entries. Lands instance
  `{{RUNTIME_ROOT}}/config/model-tier-policy.json` (template ships only
  `config/model-tier-policy.example.json`). Gate resolution:
  `DISPATCH_TIER_POLICY` → instance file → template
  `master-ops/model-tier-policy.json`.
- Step 08 wires every shipped hook/skill default-on; one owner sentence that
  any piece can be disabled later by asking the master (who explains first).
  Agent notes table documents disable paths. No per-item wiring opt-out
  questions.
- Existing installations do not auto-update. To adopt: copy the tier-policy
  example, fill from a measured inventory (or manual names), point the gate at
  it or rely on the new default path, and treat host hooks/skills as on unless
  deliberately disabled.

Workspace descriptor inventory (2026-08-04 owner decision; ledger mgm-tek.9
repository descriptor):

- Onboarding step 02 writes
  `{{RUNTIME_ROOT}}/config/workspace-descriptor.json` from the confirmed
  repository inventory (instance-owned; template ships only
  `config/workspace-descriptor.example.json`).
- Each member records `name`, workspace-root-relative `path`, `remote`,
  `role` (`product`|`ops`), `capabilities`, and `prohibited`. Workspace-level
  `workspace_root_is_plain_folder` is always true (plain folder of siblings;
  no submodules) and `master_seat` records where the master will sit.
- Worker routing (`docs/charter/04-worker-routing-review.md`) consults
  `scripts/workspace-descriptor-check` for `direct-main-commit` and
  `force-push` instead of a hardcoded product-path list (env → file →
  unconfigured).
- Existing installations do not auto-update. To adopt: copy the example into
  the runtime clone as `config/workspace-descriptor.json`, fill repositories
  from the live inventory, and stop relying on any local hardcoded product
  path list in hooks or runbooks.

Onboarding Herald voice (2026-08-04 owner decision):

- Router owner-facing rules now replace the old 3-6 sentence cap with
  genuinely kind, unhurried ELI5: explain as long as clarity needs, with no
  sentence-count limit, while still keeping command blocks and charter text out
  of owner-facing speech.
- Owner scripts in onboarding steps 00-10 now lightly frame the installer as a
  faithful Herald that prepares the place and raises the Master, with step 09
  and the founding kickoff carrying the clearest summoning language.
- Owner-facing register stays plain, warm, modern, and exact. Archaic English
  and Korean old-style honorific seasoning are explicitly not part of the
  voice; technical values, ids, paths, commands, and model names remain modern.

Installer retirement by newborn master (2026-08-04 onboarding 09/10):

- Step 8 now requires the founding kickoff to hand the newborn master an
  installer retirement switch: installer terminal handle, pty id when exposed,
  session id when exposed, exact `orca terminal close` command form, and a warm
  resume note that says a later installer resume should treat itself as retired
  unless the master is proven absent. The note appears before the kill switch.
  If the installer handle, pty id, or session id cannot be measured, the kickoff
  records `unavailable` for that field and does not invent it; an absent-Master
  case routes to `docs/runbooks/succession-boot-card.md` and must not rerun
  Founding.
- Step 10 no longer asks the owner to close the installer terminal. After the
  operating card is printed and verification passes, the newborn master closes
  the installer with that kill switch only after re-listing live terminals and
  confirming the installer handle plus any available pty/session identity match
  the installer and not the newborn master. It then verifies installer process,
  Orca terminal, and tty disappearance; unavailable identifiers, close failures,
  mismatches, ambiguity, or still-present targets are reported plainly and do
  not trigger guessed terminal closure.

Instruction-stacking countermeasure and promotion sweep 2B canon (2026-08-04 owner decisions):

- `master-ops/docs/charter/02-role-constitution.md` now states that the constitution outranks conflicting host, global, or session-injected autonomy defaults, including "do not ask" or "keep working" style instructions, and that conflicts must be named plainly.
- `master-ops/docs/charter/03-execution-principles.md` now carries the answer-first rule, the observable instruction-stacking drift signature, the stop-answer-resume response, and the no per-turn answer-sheet injection policy.
- `master-ops/docs/charter/05-dispatch-gate.md` now specifies camelCase `deliveryId` acknowledgement chaining for event-driven `check --wait`, including the stale-batch failure mode when a backlog is not acknowledged.
- `master-ops/docs/charter/08-boot-hooks-observability.md` and `master-ops/docs/orca-docs-grounding.md` now carry the Orca foundational-knowledge charter: Orca Documentation 22 pages, Developer Reference Wiki 6 pages, `stablyai/orca` snapshots, index-first reading, live binary flags, and Orca primitives before hand-rolled sleep/poll loops.
- `master-ops/docs/runbooks/contract-conventions.md` now includes merge-time `reviews[].submittedAt` re-measurement, public-forge redaction, context-injection policy, and chat-to-docs clauses; `master-ops/docs/charter/07-records.md` mirrors the accepted chat-to-docs rule.
- Existing installations do not auto-update. To adopt this entry, copy the changed charter files, grounding file, contract-conventions runbook, and the new canon tests into the generated operations repository or merge their equivalent local clauses deliberately; then update the local template version record to `v0.4.4`.

Instance runtime config landing (2026-08-04 owner onboarding-parameterization decision):

- Onboarding steps now write confirmed runtime answers into
  `{{RUNTIME_ROOT}}/config/instance-runtime.json` (instance-owned; template
  ships only `config/instance-runtime.example.json`).
- Step 01 lands `master_host_runtime` from the agent-CLI answer, preferring
  measured installer runtime over an empty ask.
- Step 02 may land optional `product_repo` and measured `transcript_globs`.
- Step 08 completes `transcript_globs` for named master hosts; Step 09 requires
  launch and model-probe guidance to read the config (or env overrides) rather
  than hardcoding a host runtime or transcript path.
- Existing installations do not auto-update. To adopt: copy the example into
  the runtime clone as `config/instance-runtime.json`, fill the keys from the
  live master host and measured transcript locations, and stop using any local
  wrapper default such as a stale `DEFAULT_MASTER_HOST_RUNTIME`.

Instance-validated asset promotion (2026-08-04 staging to template):

- New `master-ops/docs/runbooks/contract-conventions.md` carries the authoring
  instance's eight graded worker-contract clauses, reading-surface doctrine, and
  prose backlog, adapted with template placeholders and authoring-instance
  evidence labels.
- Worker routing now points to the contract conventions runbook and requires
  isolated `git worktree` placement proof for operations-repository workers.
- New `master-ops/skills/blame-agent/SKILL.md` and the Blame observability genre
  register the structured incident observation tool, including its Korean output
  contract and proposed trigger list pending owner decision.
- New `master-ops/scripts/hooks/orch-inbox-warn.sh` and
  `master-ops/docs/runbooks/orch-inbox-warn.md` carry the orchestration inbox
  warning hook, including correct-Run precondition, binding-first doctrine, and
  idle-session limit.
- Existing installations do not auto-update from this template. To adopt this
  entry, copy the new files into the generated operations repository, wire the
  hook in host settings by hand, and merge local charter or observability edits
  deliberately.

Master-operations charter progressive split (2026-08-03 post-founding):

- `master-ops/docs/MASTER-OPERATIONS.md` is now an index table (26 lines) with a section brief for each of the ten charter topics; full section bodies moved to `master-ops/docs/charter/` one file per section (01-document-map.md … 10-closed-principles-pointer.md). Load one section at a time; sections not needed for the current task stay closed.
- Every section file opens with a one-line statement of what it governs and a link back to the index.
- Cross-references throughout the repository that pointed at sections by number (in README.md, docs/public/defense-inventory.md, onboarding step files, and CHANGELOG.md) updated to link to the new charter files while keeping the section number visible in the link text.
- No rule text changed; this is a structural reorganization only. The original §0–§9 numbering became §1–§10 after splitting to remove a monolithic load pattern that reappeared post-founding (every boot loaded all 325 lines even when one dispatch question needed one rule).

Cursor worker pre-trust runbook guidance (2026-08-03 measurement):

- `master-ops/docs/charter/04-worker-routing-review.md` now includes a Cursor
  pre-trust companion beside the Codex guidance: run
  `scripts/cursor-worker-pretrust <worktree-path>` before attach and require exit
  status 0 with a summary reporting `added`, `updated`, or `already trusted`
  (not `skipped`), so trust prompts do not block startup in isolated worktrees.
- `master-ops/docs/charter/05-dispatch-gate.md` now repeats the same attach
  requirement so pre-trust verification is explicit in both worker-routing and
  dispatch-gate procedures.
- Follow-up measurement on `cursor-agent 2026.07.23-e383d2b` is now recorded in
  both sections: a fresh workspace with project-local `.cursor/hooks.json` showed
  no second startup trust gate after pre-trust (no extra prompt), hooks executed,
  and Cursor state persisted no `hooks.state` or `trusted_hash` key.

Orchestration channel doctrine: acknowledgement, addressing, and reachability rules
(2026-08-03 incident and measurement):

- New §9 rule "Acknowledgement is part of reading. A handle is routing metadata; a Run address is an identity. A loopback test proves nothing about reachability from outside," with observation from a blocking incident on 2026-08-03 where two masters could not reach each other for about an hour because a read-but-unacknowledged delivery held the queue head while both senders saw success and both receivers saw nothing to read. Measurement includes `orca orchestration check --terminal <handle>` returning the oldest unacknowledged delivery as proof of a stalled queue, `orca orchestration run-current --json` verifying the terminal's actual bound Run, and cross-session delivery testing to confirm reachability from outside.
- §5 now specifies that a coordinator clears each delivery with the acknowledgement flag before waiting again, and cross-master traffic addresses a standing Run rather than a transient handle.
- Succession boot card now binds a standing coordinator Run to the session at step 4, recording its durable address for peers before anyone needs it, with a note that a handle recorded in its place will be dead by the next restart.

Selector kinds and worker placement documentation (2026-08-03):

- `docs/public/orca-concepts.md` adds distinction between folder workspace and repository worktree selector kinds to the object model, with the consequence for what a session can do on its first command.
- `master-ops/onboarding/04-seat.md` adds a worker placement subsection stating the rule inverse to the master's placement and the verification check.

ONBOARDING.md installer UX pass from the 2026-08-03 mogui founding run
(feedback tracked as maintainer backlog on that install):

- Standing owner-facing language rules: no jargon quizzes; plain glosses for
  probe/placement/selector; shell examples the owner sees use a `$ ` prefix.
- Pacing and context diet: ship one step chunk at a time; start path is
  Orientation → Step 0 only; re-read the step from disk if the transcript drifts.
- Step 1 splits into purpose (with examples) → root → full-child inventory by
  default → name/monitor/model. Outside repositories lead with "move or clone
  under the root"; external lane is secondary opt-in. Monitor namespace is
  explicitly not the issue-tracker prefix.
- Step 1A no longer measures or ranks workspace-root folder candidates (that
  felt intrusive). The installer explains terms, gives pick criteria, asks the
  owner to choose the folder and paste an absolute path (prefer Orca **Copy
  path**), then validates only what was pasted.
- Step 3.5 explains the full open-measure-close temporary-terminal flow before
  any UI action; owner speech says "temporary terminal," not "probe."
- Step 5 byte-only CLAUDE.md/AGENTS.md drift is announce-and-proceed with an
  ELI5 line; only substantive divergence asks the owner.
- Step 6 asks for a master callsign; "master" stays the doc role label.
- Step 7.6 drops the comprehension-quiz verify; explain the gate gap and continue.
- README notes that callsign is chosen at install and lists example names.

ONBOARDING progressive-load split (mgm-ed3), same 2026-08-03 feedback, second
pass — the first pass added rules to the monolith, which made the overload
worse; this pass cuts the load unit itself:

- `ONBOARDING.md` becomes a router: session-mode question, agent load rules,
  standing owner-language rules, placeholder list, and a step index. Everything
  else moves to one file per step under `onboarding/` (`00-orientation.md` …
  `10-card-and-retire.md`), loaded one file per turn, next file only after the
  current step's Verify passes.
- Session-mode triad at the top of the router: Founding (00→10), Reverify
  (`onboarding/reverify.md`, read-only health checklist, spawn blocked), and
  Template improve (not installation; route as an ordinary task). Mixing modes
  in one session is what the 2026-08-03 run measured going wrong.
- Every numbered founding step file carries an "Owner script (3–6 sentences)" block;
  `reverify.md` keeps an Owner script and adds `Checklist` and `Report` sections;
  owner-facing turns are capped at that plus one or two questions. Verify lists, the Orca
  charter, and the Step 8 command sequence are agent-only sections; Step 8
  commands are folded under "do not paste to the owner" and lose the `$`
  owner-prompt prefix.
- Progressive loading is host- and model-agnostic by rule: a stronger model does
  not earn monolith reading, and a model that summarizes well does not earn
  skipping a step file.
- Step 3's skeleton copy and its verify now also exclude the `onboarding/`
  directory alongside `TEMPLATE-VERSION`, `CHANGELOG.md`, and `ONBOARDING.md`.
- Entry files (`CLAUDE.md`/`AGENTS.md`) now instruct: read the router only, ask
  the mode question, open `00-orientation.md`, one step file per turn, never all
  step files at once.

Charter countermeasure for host-injected autonomy defaults (2026-08-03,
instance-validated, promotion per staging→production loop):

- UserPromptSubmit hook now couples the role-state injection with the
  `Proposal -> Approval -> Execution` rule in every turn, establishing a
  mechanical guard against host defaults that override the charter. See
  MASTER-OPERATIONS §8 hook spec and §9 incident-derived rules for motivation
  and measurement.
- New §9 rule "Host-injected autonomy defaults override the charter unless
  mechanically countered," with observation from 2026-08-03 founding run,
  measurement via hook wiring and transcript audit.

## v0.4.1

No template changes in this release; the version string moves so an
installation's skew check compares equal against the latest tag.

## v0.4.0

A prose pass over the onboarding guide removed em dashes and filler; no rule,
step, or verification changed meaning.

Retirement gets a completion criterion and a revival check. Complete means
three measured disappearances (process, pane, tty), never a close command's
return value, which has been wrong in both directions on real hosts. Frozen
sessions stay resumable forever from any terminal the agent CLI runs in,
phones included; four retired masters revived at once by a mobile resume is
the measured incident. The boot card now scans running agent processes for
lineage session ids (the session id is the portable key, since resume flags
differ per agent CLI), recovers unanswered owner instructions from revivals,
and takes them through the same three disappearances.

Step 1 stops leaving outside repositories implicit. When the user names a
repository that lives outside the confirmed workspace root, the installer asks
which home it gets: moved or cloned under the root (recommended when the master
will route real work into it, since the inventory and workspace-level code
measurement only see what lives under the root) or recorded as an external
lane, staying put with its absolute path and access rules in the operations
document. The installer never moves repositories itself, and the step's
verification now requires every named outside repository to end up in one of
the two homes.

The master's seat moves to the workspace level. Step 3.5 previously prescribed
the ops repository worktree and forbade the folder route as unverified; the
folder route is now verified from the CLI (`id:folder:<uuid>` passes precheck
listing, terminal create, and spawn placement match, measured 2026-08-03), and
a master seated in one repository's worktree shipped as a real misplacement the
same day. Step 3.5 now seats the master in the workspace root's folder
workspace (or the primary worktree when the workspace is a single repository),
proves the seat with a placement probe terminal (`terminal show` must report
`worktreeId` as `folder:<uuid>`; an empty `worktreePath` is the expected shape,
judge by `worktreeId`), persists the selector in `id:` prefixed form (bare
`folder:` is accepted by `terminal create` but rejected by `terminal list`, a
measured subcommand asymmetry, so only the `id:` form works everywhere), treats
the probe handle as transient rather than durable, and closes the probe so
Step 8's spawn is the only terminal in the seat. Step 8 resolves the durable
selector on the host again instead of checking a dead handle.

Onboarding gains an Orca Context Charter, installer scope only: ground every
Orca claim in the docs snapshot (agent index first, smallest page next), treat
the snapshot as read-only and generated, cite the page or source file used and
check the live Orca repository when freshness matters, keep provider
assumptions out of plans, state in one line what was relied on before
proceeding, answer newcomer questions about projects, workspaces, and worktrees
in place, and explain expected UI labels that look alarming (the "Unavailable
worktree" chip on folder workspace sessions) before the user has to ask. The
operating card printed in Step 10 now points at the runtime repository's Orca
concepts guide, and Step 10 answers lingering Orca questions under the charter
before the installer retires.

## v0.3.0

The charter's review-bot rule gains its missing half. The v5 rule said who
handles bot threads (workers, without per-round owner instruction); it did not
say when a merge may proceed. Now, on a repository with review bots attached,
zero unresolved threads is a merge precondition: every thread gets a reply
stating what was done or why not, and the merge waits for the bots' pass over
the latest push. A bot finding is verified against the code before it is acted
on, because bots produce false positives and a thread resolved without
measuring is silence dressed as review. Repositories without bots inherit no
ceremony. Generalized from field use: one pull request ran the full cycle with
five threads from two bots, all answered and resolved before merge.

The charter's Codex pre-trust posture stops overstating what the tool
guarantees. Pre-trust holds when the summary reports the worktree added,
updated, or already trusted; the skip path (`Summary: skipped`, no TOML-capable
interpreter on the host) leaves the trust prompt in place and says so on
stdout. The attach instruction now says to confirm the summary is not
`skipped`, instead of promising unconditionally that startup never blocks.

ONBOARDING's Step 0 verification matches the preflight's new tiering: `gitleaks`
and `ctx` are measured and warn without blocking when absent, with the
consequence attached (the redaction gate cannot decide without its engine; the
records practice cannot query cross-provider history), so an install that will
publish treats the warning as a real item while a host that does neither
onboards without ceremony.

Onboarding gains a Step 10 that ends the session properly.

Everything installed is worthless if the user does not know the handful of
sentences that operate it, so the installer prints an operating card as plain text
and tells the user to keep it under a name they will find again. The card is written
to be pasted into any agent, so it depends on nothing about the installer session:
how to ask for role state, how to propose and approve, how to delegate, which gates
run before publishing and what they do not cover, how to ask for succession, and
which components were declined at install so behaviour that looks like a defect can
be checked against that first. A blank decline line is not allowed, because blank
reads as unknown rather than as none.

The step also verifies the conversation rather than the artifacts. The earlier steps
ask questions, and a run that produced files without answers guessed; the check is
that facts were confirmed rather than inferred and that each essential decline was
re-asked once.

Then it asks the user to close the installer terminal, with the reason: two agents
holding one repository is how uncommitted work gets lost, and the installer has no
further role. The installer does not close anything itself.

Onboarding now names the stack this template was built against, with each
component's role and the boundary it is deliberately kept inside. A tool adopted
without its boundary becomes the next thing to unwind, so the table states both:
the tracker's memory is a pointer cache toward Git rather than the knowledge source
of truth, the history index is a trace archive rather than routine boot context,
the review graph earns its place on token cost rather than correctness, and the
worker runtime plugin is one wiring of the adapter layer rather than a harness
requirement. The same boundaries are recorded in `docs/MASTER-OPERATIONS.md`, where
the master reads them daily.

The preflight checks the behaviour-shaping layers, methodology and restraint. Both
are skill packs rather than one agent's plugins, so detection is agent-neutral and
accepts either packaging: a skill directory under any known root, or an agent's
plugin manifest, which is the same content wrapped differently. Only the install
hint varies by host. They warn rather than fail, with the consequence attached to
the warning: without the methodology layer the charter reads as advice rather than
procedure, and without the restraint layer expect larger diffs and more speculative
structure.

Onboarding also records the five questions that decided the stack, so the same test
applies to what an installer chooses to install: does it require an API key, does it
force or over-collect telemetry, does it add a management point, does it survive the
operation growing past one person, and what does it resolve beyond the agent-context
help that every tool claims. The maintainer-facing version of the same bar lives in
`CONTRIBUTING.md`, since an installation receives a stack rather than choosing one.

Declining an essential component now gets one re-ask. Not a nag: the consequence is
restated and the question is asked again, once, then the answer is final. The first
no usually answers a different question, because a component list reads as
preferences: the first pass answers "do I want this" while the question that matters
is "am I accepting this behaviour". The confirmed decline is recorded together with
what it accepts. Where the agent has no interactive query interface the re-ask cannot
happen, so the contract carries the confirmed declines up front and the record says
they were confirmed in advance rather than asked.

The preflight summary repeats every missing essential component with its consequence
in a block of its own, because fifteen lines of check output is exactly the length at
which the important line gets skimmed past.

And one asymmetry is written down rather than left to be discovered: an agent with
no interactive query interface cannot run the steps that ask the user a question.
Onboarding is a conversation, so either run it from an agent that can ask, or supply
every answer in the dispatch contract and record that they were answered in advance
rather than asked.

The redaction gate now runs on gitleaks. `scripts/redaction-scan.sh` keeps only
what gitleaks does not do: scoping to tracked content, scanning commit messages,
translating the organization rules file, and stating what was covered. The file
went from 440 lines to 304, and the rule list, allowlist parser, and masking
plumbing are gone.

The operator interface does not change. `REDACTION_EXTRA_PATTERNS` still names a
file of `id|description|regex` lines outside version control, and the wrapper
translates it into a gitleaks config that extends the committed one, so no host
converts anything. `REDACTION_REQUIRE_EXTRA=1` still exits 2 when those rules are
absent.

Two behaviours are new because the engine changed. Exemptions move to gitleaks'
own mechanisms, a `.gitleaksignore` fingerprint or a config allowlist, and an
allowlist file still holding entries in the retired format now exits 2 rather than
being ignored: an installation whose exemptions stopped applying should hear it
from the gate. Scanning is one path per invocation, because gitleaks scopes a
single path argument reliably and falls back to the whole directory when given
several, which would make a tracked scan depend on untracked local scratch.

The reported organization-rule count now describes what was loaded rather than what
the file held. A mutation that kept the count while dropping the generated config
from the run was invisible, since a clean tree stays clean either way. A test now
plants a token no shipped rule matches and requires it to be found with the rules
and missed without them.

The adapter's health check no longer probes Orca with `orca --version`. That flag
does not exist: on one host it prints the usage banner and exits 0, so the check
passed while proving nothing, and a Linux user reported the same command launching
the GUI application. It now uses `orca status --json`, the documented probe, which
is what the onboarding preflight already used. Added to the incident-derived rules
as its own entry, since the shape generalizes past this one tool.

The preflight also requires `ctx`, the cross-provider agent history index, with a
reachable local index. The records practice asks what happened across sessions and
providers, which no single provider's transcript can answer. Waivable like any
other check for a host that does no history work.

Onboarding now states consequences instead of listing options.

Step 7.5 offered a skill layer as optional. The template carries documents and
scripts and cannot carry the host layer that makes a master behave the way those
documents describe, so several of those components are optional in name only. Each
one now comes with the consequence of declining it, said in the same breath as the
offer, and the user's answer is recorded per component including a decline. A
declined component is a fact about the installation; later behaviour that looks
like a master defect is often a declined component instead.

New Step 7.6 states what the publish gates do not cover: pull request titles and
bodies, review comments, release notes, issue text, and anything typed into a
forge web interface. None of it is in the repository, so no scanner here reads it,
and it is where internal names arrive most easily because it is prose rather than
code. A gate trusted beyond its scope is worse than no gate, since it turns an
unchecked surface into a believed-clean one. The same rule is added to the
incident-derived rules section with the grep that settles it.

The redaction gate starts moving onto gitleaks as its matching engine, and this
release carries the preparation rather than the swap.

`config/gitleaks.toml` holds the rules this repository needs beyond gitleaks'
maintained default set, which covers provider secrets far better than a
hand-written list. Organization-specific patterns stay out of it: this repository
is public, so committing them would publish what they protect. They belong in a
second config named by `GITLEAKS_CONFIG`, kept outside version control, which is
the same contract `REDACTION_EXTRA_PATTERNS` has.

`tests/test_gitleaks_parity.py` is the safety net for the swap. It runs both
engines over one fixture per rule plus the excused classes and requires them to
agree, because zero findings on both sides proves nothing by itself. Two
translation errors surfaced while writing it and are fixed: synthetic home
prefixes had become gitleaks `paths`, which skips files rather than content, and
the placeholder list had become `stopwords`, which excused nothing here while
`regexes` does. Current state: 14 of 14 positives flagged by both, 3 of 3
negatives excused by both, no divergence.

The preflight now requires `gitleaks` on PATH, waivable like any other check.

One scope fact the swap depends on: `gitleaks dir .` walks the working tree,
including untracked build output, and compiled bytecode alone produced 57 findings
against 0 in tracked content. Build products are excluded in the config, and the
wrapper will feed gitleaks the tracked file list rather than the directory.

What gitleaks does not do, measured rather than assumed: it does not scan commit
messages. A key placed only in a commit message returns "no leaks found" while the
same key in file content is found. The wrapper keeps that scan, and keeps
`redaction-inventory`, which measures the inverse question of which tokens no rule
covers and has no gitleaks equivalent.

`scripts/redaction-scan.sh` now scans commit messages, which it never did.

The scan read tracked file contents, so a message was outside its scope while a
green result read as a full check. An internal workspace name sat in four commit
messages of this public repository and the scanner never objected; a person found
it by eye, and the cleanup needed a history rewrite.

`--range A..B` now also scans the messages of the commits in that range, and
`--commit-messages A..B` does it in any mode. Findings are reported against
`commit:<sha>` with the line number inside the message, so they can be allowlisted
the same way a file line can. Both summary lines state the count, and say
`commit-messages=not-scanned` where messages were not in scope, because a green
line that does not name what it skipped is indistinguishable from a full check.

Five tests drive the scanner inside temporary repositories that carry a copy of
it, which is also the shape a real installation has. Two mutations confirmed they
bite: disabling the message scan fails three, and dropping the scope from the OK
line fails four.

`scripts/redaction-inventory` gets its first tests, and two ways it could report
a clean result without having read anything are closed.

Rule lines that are malformed or whose regex does not compile were dropped in
silence, so the printed rule count described what loaded rather than what the file
held: coverage narrowed while the file still looked populated. The scope line and
the JSON output now report how many lines were considered and how many were
unusable.

A repository with no tracked files reported OK. Reading nothing is not a clean
result, so that case now exits 2 as undecidable, the same as a missing pattern
file or a non-repository.

Nine tests drive the real script in temporary git repositories and assert exit
codes, since the exit code is what the publish gate consumes: unset pattern file,
a file with no usable rule, unusable lines reported, no tracked files, outside a
repository, an uncovered candidate, a rule that covers it, a baseline that
suppresses it, and the JSON scope fields. Two mutations confirmed they bite:
restoring the silent drop fails two of them, and letting an empty repository pass
fails another.

`register` now compares the model a dispatch declared with the model the worker
actually ran. Until now the gate enforced the declaration at `check` and
`register` took no model at all, so a worker inheriting a tier nobody asked for
registered clean: the incident the tier policy exists for lives one step past the
declaration.

Declare the measurement per dispatch with `--model-probe-cmd`, alongside
`--declared-model`. The command must read an artifact the agent itself produced,
such as its session transcript; `scripts/model-identity-probe` is the reference
implementation. A TUI status line is not a measurement source, because it is what
a renderer drew rather than what the session recorded, and authenticating against
it would leave a verification stamp with nothing behind it.

The verdict is graded rather than absolute. No declared model warns as
`MODEL_UNVERIFIED`, a probe that returns nothing warns as `MODEL_PROBE_FAILED`,
and both still register: a runtime with no way to report its model would
otherwise be unable to dispatch, and a check nobody can satisfy is a check nobody
enables. A measured model in a tier the policy watches more closely than the
declared one denies with `MODEL_TIER_ESCALATION`. Running looser than declared
warns as `MODEL_MISMATCH`. Every registration records `model_declared`,
`model_measured`, and `model_verified`, so an unverified one is distinguishable
from a verified one.

Tier ranking reuses the policy's own per-window caps rather than a new ordering
field, so the two cannot disagree about which tier is trusted less. Version 1
policies have no tiers to rank, so a mismatch there is recorded and not ranked.

## v0.2.0

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
