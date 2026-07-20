# U2 Pre-Implementation Verification (accepted results)

> Read-only verification performed 2026-07-16 against the prior host-repo candidate; all conclusions carry over to this repo.

## Stack

- **Python, minimum 3.10, stdlib only at runtime.** The claim "3.11+ is preinstalled everywhere" was measured and **retracted** (macOS system python may be 3.9; distro defaults vary). Python 3.10+ is an explicit documented prerequisite; no bootstrap tool is provided.
- `mypy --strict` is an optional dev check; absence prints SKIP and does not fail the gate. Quality gate = unittest.

## Layout

Canonical src-layout: `src/master_runtime/core/context/{descriptor,manifest,resolver}.py`. Bare top-level `context` package rejected (name collision, extraction). CLI is separate from core and deferred (not needed to verify U2). `pyproject.toml` deferred to packaging.

## U2 contract

`resolve(path, workspace_manifest) -> ContextDescriptor`

- **Manifest declares**: workspace root, known repositories, identities, expected branch policy (opaque passthrough), optional metadata.
- **Runtime observes**: path existence, `.git` presence (dir = repo, `gitdir:` file = worktree), repo membership (longest-path match), nesting, disappearance.
- **Non-goal**: path-local discovery does not recursively scan arbitrary workspace subtrees beyond declarations, workspace-root children, and the queried path's ancestors.
- **Conflict model**: declarations are never trusted. Drift is data, not an exception — per-repo status ∈ {declared+observed, declared-missing, observed-undeclared} + explicit warnings. Only malformed input raises (`ManifestError`). No git commands are executed — pure filesystem observation.

## Minimal ContextDescriptor (U2)

Required: kind, resolved_path, workspace_identity, repository_identity (when inside a repo), repo_set (with per-entry status), capabilities (minimal: `git_repo: bool`), warnings.
Deferred: parent descriptor object (U2 reports nesting as kind + enclosing path string), full capability model (approval unit), default-branch metadata (repo rules unit). Excluded: session/worktree-registry anything.

## Fixtures & tests

- Fixture strategy: **reusable Python fixture builder** in tests (tempdir trees; empty `.git/` dir markers + `gitdir:` files suffice — no real `git init` needed since the resolver never calls git). External JSON tree specs rejected (schema maintenance risk).
- Regression cases (generalized, no vendor names):
  - A: non-Git multi-repository root resolves as first-class kind with full repo set — not an error.
  - B (reduced): folder-kind descriptor reports `git_repo=False`; allowing/denying capability requests is a later unit's responsibility.
  - C (reduced): a folder workspace receives a stable folder descriptor even when no Git worktree exists; deterministic across calls. Full session-registry reproduction deferred to adapter integration tests.
- Plus: declared-missing, observed-undeclared, nested repo, worktree (`gitdir:` file), longest-path membership.

## Verification commands

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
command -v mypy >/dev/null && mypy --strict src || echo "SKIP: mypy not installed (optional)"
```

Real workspace coordinates are supplied only via a local manifest outside this repo (`*.local.json` is gitignored).
