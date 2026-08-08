# Changelog

Changes to the orchestrator. The template under `master-ops/` has its own
changelog at `master-ops/CHANGELOG.md` and its own version number; the two move
independently.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Versioning

Releases use `MAJOR.MINOR.BUILD`.
`BUILD` is derived at cut time with `git rev-list --count origin/main`.
Only the owner moves `MAJOR` or `MINOR`; automation never bumps either digit.
The first release under this scheme is a `0.5` cut with BUILD derived at cut
time.

While the major version is 0, the public surface is unstable: CLI flags, file
formats, and module interfaces can change in a minor release. Pin a version if
you build on it.

## [Unreleased]

### Added

- Upgrade mode for founded workspaces: give an ops path, detect template drift
  via `master-ops/MANIFEST.json` + `scripts/template-check`, and apply
  template-layer files through `scripts/template-apply` (dry-run first,
  instance-owned paths refused by name). Router mode 3 and a boot-time
  `Template:` line on `harness-selfcheck.sh` are the attachment points.

- `dispatch-gate check --no-record` evaluates a dispatch decision without
  appending a ledger row or issuing a ticket. `master-ops/scripts/dispatch
  --check-only` uses it so dry runs do not spend the fan-out budget they are
  inspecting.

- Onboarding agent-inventory consent and default-on harness wiring (owner
  decisions 2026-08-04): step 01 asks consent to probe installed agent CLIs
  (purpose: match task weight to model strength and identify top-tier models
  that need owner approval), then
  writes instance `config/model-tier-policy.json` from measured (or
  owner-named) runtimes, versions, and model ids — never guessed ids.
  Ships `config/model-tier-policy.example.json` only. Dispatch gate default
  path is now env `DISPATCH_TIER_POLICY` → instance file → template
  `master-ops/model-tier-policy.json`. Step 08 wires shipped hooks/skills
  default-on with one owner sentence that any piece can be disabled later by
  asking the master; agent notes carry disable guidance. No per-item wiring
  opt-out questions.

- Workspace descriptor inventory (owner decision 2026-08-04; closes ledger item
  mgm-tek.9 repository descriptor): ships
  `config/workspace-descriptor.example.json` only (filled instance file is
  gitignored). Per repository: `name`, workspace-root-relative `path`,
  `remote`, `role` (`product`|`ops`), `capabilities`, `prohibited`. Workspace
  fields: `workspace_root_is_plain_folder: true` (no submodules; plain folder
  of siblings is intentional) and `master_seat`. Loader
  `src/master_runtime/core/workspace_descriptor.py` resolves environment
  override → instance file → honest unconfigured. Consumer:
  `scripts/workspace-descriptor-check` and worker-routing guidance read
  `prohibited` (for example `direct-main-commit`, `force-push`) instead of a
  hardcoded product-path list. Onboarding step 02 writes the instance file
  from the measured repository inventory. Docs:
  `docs/public/orca-concepts.md` records that Orca "not a valid worktree
  folder" on the plain root is expected.

- Instance runtime config for onboarding answers: ships
  `config/instance-runtime.example.json` (template never commits a filled copy)
  with `master_host_runtime`, per-runtime `transcript_globs`, and optional
  `product_repo`. Loader
  `src/master_runtime/core/instance_runtime_config.py` resolves each value as
  environment override → config file → honest unconfigured. Consumer:
  `scripts/model-identity-probe` can omit `--transcript` and resolve via
  config/`MOGUI_TRANSCRIPT_GLOB` instead of a baked path. Onboarding steps
  01, 02, 08, and 09 wire existing runtime questions into
  `config/instance-runtime.json` (gitignored). Owner decision 2026-08-04:
  onboarding already asked these facts; they needed a durable landing place.

### Changed

- Root README now starts with product summary, Quickstart, and the tool rationale, with overlapping Orca and tool-stack explanations consolidated.

- `master-succeed retire` now reports each of the three disappearances
  (`pane`, `process`, `tty`) as `measured` / `still_present` / `skipped:<why>`.
  Full `CLOSED` requires all three measured; any skip yields `CLOSED_PARTIAL`
  so a null `process_id` on a folder-workspace pane can no longer read as a
  complete retirement. Accepts optional `--target-pid` and `--target-tty` for
  externally measured targets. Public lifecycle docs name the FIN/ACK
  handshake and call `master-succeed retire` by name.

### Fixed

- `worker-reap` now accepts clean worktrees whose branch changes are already
  present in `origin/main` after a squash merge. The guard still leaves dirty,
  conflicting, or content-changing worktrees in place with a reason.
- `dispatch-gate check` no longer denies repeated contract hashes as
  `DUPLICATE_CONTRACT`; repeated ALLOW rows now carry an `attempt` ordinal so
  the ledger identifies retries by `contract_sha` plus attempt.
- Windows CI measurement leg: skip the diagnosed Unix script-execution surface
  (extensionless shebangs → WinError 193, bash/WSL paths, exec-bit discovery)
  via `tests/windows_exec_surface.py` so `tests (windows-latest)` reports green
  on the Windows-compatible subset. The skipped class is the Windows backlog;
  the job stays measurement-only (`continue-on-error` unchanged). Onboarding
  structure tests now read UTF-8 explicitly so Windows default encodings do not
  false-fail doc inventory checks.

### Added

- `scripts/cursor-worker-pretrust`, measured on this host against known trusted
  2026-08-03 worktrees under `.orca/worktrees/mogui-ADE-orchestrator/`: Cursor
  Agent persists workspace trust in `~/.cursor/projects/<project-key>/.workspace-trusted`
  as JSON with `workspacePath` and `trustedAt`. The script writes that marker
  for the measured key form (absolute path with `/` mapped to `-` and `.` removed),
  validates existing JSON before editing, stays idempotent, and rejects missing
  worktree paths. Added docs rows and a runbook Cursor pre-trust section beside
  the existing Codex guidance so worker startup can be pre-trusted before
  orchestration attach. Additional measurement on `cursor-agent 2026.07.23-e383d2b`
  found no second startup trust gate for project hooks: in a fresh workspace with
  project-local `.cursor/hooks.json`, startup passed with no extra prompt after
  pre-trust, hooks executed, and Cursor state showed no persisted `hooks.state` or
  `trusted_hash` key. Hardening follow-up: reject trailing-slash symlink
  `--projects-dir` values, refuse non-regular marker paths, probe for Python
  3.6+ capability (and versioned `python3.10`–`python3.6` candidates), and write
  markers through no-follow directory FDs with atomic replace so symlink
  preflight is not only TOCTOU-sensitive shell checks.
- Adopted `MAJOR.MINOR.BUILD` release numbering for orchestrator releases. The
  release build number is now derived from `git rev-list --count origin/main`
  at cut time, and the owner alone moves MAJOR or MINOR.

- Documentation identifier audit: public and template docs now describe the
  measured `model-identity-probe` no assertion path, drift exit, and undecidable
  exit separately. A regression test pins documented dispatch-gate reason codes
  to the source enum so plausible labels cannot re-enter unchecked.

- First-run setup guide rewrite in `docs/public/getting-started.md` for a
  reader who has never opened Orca: measured prerequisites, install and shell
  command registration, folder workspace versus checkout, wake-up and
  onboarding decision preview, boot proof, and a first supervised worker.
  README Quickstart and document table point at that path honestly instead of
  stopping at a wake-up phrase. Unverified first-launch UI labels and
  non-macOS installers are marked rather than invented.

- README section "What one dispatch actually looks like": walks a single
  supervised dispatch end to end, naming the actual Orca command and this
  repository's gate at each step. Closes the gap between knowing why Orca is
  required and understanding what the machinery does on a single job. Includes
  the failure mode that motivated the design: a dispatch record showed success
  while the worker terminal was still on its startup screen, caught only
  because dispatch state and shell effect are separate objects.
- `docs/public/defense-inventory.md` "Breaks when" column and "Substrate and
  stability" section: each guard now names a concrete failure condition grounded
  in the tree or in a measurement run on 2026-08-03. Substrate paragraph
  distinguishes guards standing on contracted surfaces (this repository's
  scripts, `git`, documented Orca subcommands) from those on vendor-internal
  formats (host session storage). When vendor surfaces are unreadable, guards
  degrade to recorded warnings (e.g. `MODEL_PROBE_FAILED`) rather than false
  passes. Observed example: 2026-08-03 grok worker's `register` call returned
  `MODEL_PROBE_FAILED` when session file did not exist yet.
- README section "What is standing guard" and `docs/public/defense-inventory.md`:
  the existing defense inventory (dispatch gate with tier × fan-out and a
  ledgered policy digest, transcript model probes, spawn placement and
  empty-seat checks, redaction scope honesty, frozen-session revival checks,
  progressive onboarding) surfaced with paths and measurements. No new guards;
  every claim points at a file that already lived in the tree.

## [0.4.1] - 2026-08-03

### Fixed

- `dispatch-gate register` accepts a verified `sentinel-log` dispatch without
  requiring an Orca orchestration record, and records the completion channel in
  the ledger. `orchestration` dispatches still require Orca verification.

### Removed

- The permanently skipped lineage test. It dry ran the append against a real
  operations ledger at a path the publication sweep replaced with a fictional
  one, so it could never run on any machine, and the property it checked
  (append preserves existing bytes) is already covered twice on the same code
  path by the synthetic fixtures. The suite now reports zero skips.

## [0.4.0] - 2026-08-03

### Added

- The scan warns when organization rules contain no native script pattern:
  a rule set that spells an identifier only in its romanized form misses the
  same identifier in its native spelling (measured live with a Korean name).
  The warning fires only when organization rules are loaded, and never prints
  rule content.

- `master-succeed spawn --expected-placement <worktreeId>`: after the existing
  requested versus actual check, the spawn verifies the actual worktree against
  an independently supplied expected placement and fails closed with a new exit
  code (26, `SPAWN_PLACEMENT_MISMATCH`) when they differ. The existing check
  answers "did I get what I requested"; this one answers "did I request the
  right place", which a request edited until the validator went green cannot
  answer (the 2026-08-03 misplacement).

- `docs/public/orca-concepts.md`: Orca's object model (projects, folder
  workspaces, repository worktrees), where the master sits and why, selector
  forms with their measured behavior, and expected UI labels that look
  alarming. Linked from the README document table, the document index, and the
  lifecycle page's founding spawn section. Written after a misplacement where
  a master was spawned into a repository worktree instead of the workspace
  folder workspace (2026-08-03).
- CI: `.github/workflows/gates.yml` runs the test suite (ubuntu and macos,
  Python 3.12, checksum pinned gitleaks) and the committed ruleset redaction
  scan on every pull request and push to main. What CI cannot cover is stated
  in the workflow header: the organization rules live outside the repository,
  so the full scan stays local. The inventory runs informationally.
- An opt-in pre-push hook (`hooks/pre-push`, enable with
  `git config core.hooksPath hooks`) scans each pushed ref range, covering
  changed files and commit messages both, with a tracked tree fallback when no
  range resolves.

### Fixed

- Bare `folder:<uuid>` workspace selectors no longer die in the spawn precheck:
  the terminal listing call wraps them in the `id:` form it requires, while
  terminal create keeps the caller's original string (the two subcommands
  disagree about bare folder selectors; measured on two hosts).
- `path:` workspace selectors now match the `repoId::path` worktree identity
  Orca resolves them to, compared by real path; resolution failure falls back
  to the literal comparison, never open.
- Both mismatch errors append the accepted selector forms, so an exit 22 or 26
  tells the caller what to pass instead of inviting a workaround.
- Organization rules are proven against the engine that runs them. Python's
  `re` validated the rules, gitleaks compiles RE2, and a rule Python accepted
  crashed the engine at config load while every invocation swallowed the
  crash: scans with organization rules configured reported `OK` having
  scanned nothing. The merged config now runs a canary through gitleaks
  before anything is scanned (failure exits 2 naming rule ids, never
  patterns), and a nonzero gitleaks exit during a scan is an engine error
  and exits 2 rather than reading as a clean file.

## [0.3.0] - 2026-08-03

### Changed

- `scripts/codex-worker-pretrust` finds a TOML-capable interpreter instead of
  demanding Python 3.11. A resolver probes `python3`, newer versioned names, then
  `python` (the only name Windows Git Bash and Windows venvs expose), taking the
  first whose `tomllib` imports; the probe is the capability, not a version
  number. When nothing qualifies, the script skips instead of erroring: exit code
  changes from 2 to 0, nothing is written, the summary line reads
  `Summary: skipped — ...` so a machine can tell the skip from a clean run, and
  the reason prints to both stdout and stderr. Callers that branched on exit 2
  for the case of a missing interpreter should read the summary instead. (#40)
- `scripts/onboarding-preflight.sh` enforces no interpreter version floor:
  `python3` presence still fails when missing, the version is reported and never
  compared, and a tool that needs a more capable interpreter locates one itself
  at runtime. The `pytest` check warns instead of failing, because tests are the
  agent's job; `gitleaks` and `ctx` warn instead of blocking, since publishing
  needs the former and the records practice the latter while running a master
  needs neither; the Codex plugin check advises instead of blocking, because a
  routing policy that sends heavy work to Codex is one workspace's choice. Every
  demoted check stays in the essential components summary, so the downgrade is
  from blocking to loud, not from blocking to silent. (#35, #37, #39)
- The redaction gate runs on gitleaks. `scripts/redaction-scan.sh` keeps only
  what gitleaks does not do: scoping to tracked content, scanning commit
  messages (measured: gitleaks does not read them), translating the
  organization rules file, and stating what was covered. The operator interface
  is unchanged; exemptions move to `.gitleaksignore` fingerprints or a config
  allowlist, and a file still holding entries in the retired
  `scripts/redaction-allowlist.txt` format exits 2 rather than being ignored.
  A parity test planted before the swap caught three translation errors. (#29,
  #30, #32)
- `dispatch-gate register` measures the worker's actual model instead of
  trusting the declaration, because the incident the tier policy exists for was
  a worker inheriting a tier nobody asked for. (#27)

### Added

- `tests/test_reference_command_table.py` pins `docs/public/reference.md` to the
  actual `scripts/` surface: it reads each executable's own `--help`, compares
  the (script, command) pairs against the table's rows, and fails in both
  directions. The table had sat behind an `AUTO-GENERATED` marker whose
  generator never existed, and four commands had drifted out of it. (#36)
- First tests for `scripts/redaction-inventory`, closing two silent passes. (#28)

### Fixed

- Public documentation caught up with the code: the getting-started page names
  what a user actually installs and scopes the list to the master-session path
  (#35); the concept pages stopped describing the removed adapter dispatch and
  isolation paths as live mechanisms (#38, #41); the scan documentation matches
  what the scan does (#34).

## [0.2.0] - 2026-08-02

Tagged alongside the master-ops template's v0.2.0 release. These runtime entries
shipped in that tag but were recorded under Unreleased at the time; they are
restored to their release here. The template's changes for the same tag are
in `master-ops/CHANGELOG.md`.


### Added

- Spawn liveness verification against reissued terminal handles. Orca reissues a
  terminal's handle between creation and first use (observed twice on 2026-08-02,
  once per spawned master), so the handle a spawn returns can be stale on arrival.
  `spawn_successor` now snapshots the terminal list before creating, re-queries it
  after, and accepts the reported handle only if it is live, absent from the
  pre-create snapshot, and in the requested worktree. Otherwise it adopts a
  replacement handle only if exactly one new terminal in that worktree carries the
  requested pane title (containment, since Orca prefixes live titles with status
  glyphs); the report then says `MATCH_REISSUED` with `handle_reissued: true` and
  records the stale handle as `reported_handle`. Zero or multiple unresolvable
  candidates fail closed with exit code 24 (`SPAWN_HANDLE_STALE`) and close
  nothing — which also means the created terminal may still be running unmanaged
  and needs manual reconciliation via `orca terminal list`. A list failure before
  the create blocks the create with exit code 25 (`SPAWN_LIST_ERROR`); a list
  failure after it attempts a cleanup close first and exits 25 on success or 23
  (`SPAWN_CLOSE_ERROR`) if that close also fails. Cleanup closes are skipped
  entirely — the error says "pre-existing; terminal not closed" — whenever the
  reported handle already appeared in the pre-create snapshot, because closing it
  could kill a user's terminal that the handle was recycled from. Disconnected
  list entries never count as live, and entries without a handle are skipped
  rather than failing the whole list.

### Removed

- The typed `adapter dispatch` path: `scripts/adapter dispatch`, `core/adapter/dispatch.py`,
  `core/adapter/isolation.py`, `ToolProfile`, and `CodexCompanionProfile`. It reached
  Codex through a plugin script at a version-pinned path and was the only implementation
  of that interface, so a plugin upgrade would have broken it silently. Workers run as
  CLI sessions in Orca panes, which is the path in actual use, and `scripts/dispatch-gate`
  still gates them. `adapter doctor` stays and no longer probes for the plugin script.

## [0.1.0] - 2026-08-01

First tagged version. The repository was already public and usable before this
tag. What the tag adds is a point you can pin and a place to record what
changed after it, not a change in what the code does.

### Added

- `CHANGELOG.md` and versioned releases. Before this, "which version" had no
  answer other than a commit SHA.
- `CODE_OF_CONDUCT.md`, adopting the Contributor Covenant.
- `SECURITY.md`, stating where to report a vulnerability and what response to
  expect from a single-maintainer project.

### Changed

- README no longer says there is no version tag.
- The pull request template distinguishes the two changelogs. A change to the
  orchestrator and a change to the template are recorded in different files.

### Notes on what 0.1.0 contains

Everything in the repository at this tag, which the README describes in full.
The pieces exercised against real workspaces are succession, contract-gated
dispatch, the acceptance loop, and the compaction-resilience probe. 295 unit
tests pass, 1 skipped.

There is no CI at this tag. Tests and the redaction scanners run locally before
a push, so a passing count in a pull request is the author's word.

[Unreleased]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/baksohyeon/mogui-ADE-orchestrator/releases/tag/v0.1.0
