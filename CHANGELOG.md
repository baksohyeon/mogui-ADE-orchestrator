# Changelog

Changes to the orchestrator. The template under `master-ops/` has its own
changelog at `master-ops/CHANGELOG.md` and its own version number; the two move
independently.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the major version is 0, the public surface is unstable: CLI flags, file
formats, and module interfaces can change in a minor release. Pin a version if
you build on it.

## [Unreleased]

### Added

- Spawn liveness verification against reissued terminal handles. Orca reissues a
  terminal's handle between creation and first use (observed twice on 2026-08-02,
  once per spawned master), so the handle a spawn returns can be stale on arrival.
  `spawn_successor` now snapshots the terminal list before creating, re-queries it
  after, and when the reported handle is not live it adopts a replacement handle
  only if exactly one new terminal exists in the requested worktree, narrowing by
  pane title when several appear. Zero or multiple unresolvable candidates fail
  closed with exit code 24 (`SPAWN_HANDLE_STALE`) without closing anything; a
  terminal-list failure around the create fails closed with exit code 25
  (`SPAWN_LIST_ERROR`). `SpawnReport` gains a `handle_reissued` flag.

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

[Unreleased]: https://github.com/baksohyeon/mogui-ADE-orchestrator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/baksohyeon/mogui-ADE-orchestrator/releases/tag/v0.1.0
