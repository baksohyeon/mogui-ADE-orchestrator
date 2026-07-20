"""Pure filesystem context resolver.

Non-goal: path-local discovery does not recursively scan arbitrary workspace subtrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from master_runtime.core.context.descriptor import (
    Capabilities,
    ContextDescriptor,
    ContextKind,
    RepoEntry,
    RepoStatus,
)
from master_runtime.core.context.manifest import WorkspaceManifest, load_manifest
from master_runtime.core.context.manifest import ManifestError


@dataclass(frozen=True)
class _ObservedRepo:
    path: Path
    identity: str
    marker_kind: ContextKind


_GITDIR_PREFIX = "gitdir:"


def resolve(
    path: str | Path,
    workspace_manifest: WorkspaceManifest | str | Path,
) -> ContextDescriptor:
    """Resolve path context from manifest declarations and filesystem facts.

    Path-local recursive repository discovery is a non-goal; only declarations,
    workspace-root children, and the queried path's ancestors are observed.
    """

    manifest = _coerce_manifest(workspace_manifest)
    workspace_root = _normalize_path(Path(manifest.workspace_root))
    resolved_path = _normalize_path(Path(path))

    declared = _declared_repositories(workspace_root, manifest)

    observed, observation_warnings = _observe_repositories(
        workspace_root,
        resolved_path,
        declared,
    )
    entries, repo_warnings = _build_repo_set(workspace_root, declared, observed)
    warnings = tuple(sorted((*observation_warnings, *repo_warnings)))
    matched = _longest_repo_match(resolved_path, observed.values())

    if matched is None and resolved_path == workspace_root:
        return ContextDescriptor(
            kind=ContextKind.MULTI_REPO_WORKSPACE,
            resolved_path=str(resolved_path),
            workspace_identity=manifest.workspace_identity,
            repository_identity=None,
            repo_set=entries,
            capabilities=Capabilities(git_repo=False),
            warnings=warnings,
        )

    if matched is None:
        return ContextDescriptor(
            kind=ContextKind.FOLDER,
            resolved_path=str(resolved_path),
            workspace_identity=manifest.workspace_identity,
            repository_identity=None,
            repo_set=entries,
            capabilities=Capabilities(git_repo=False),
            warnings=warnings,
        )

    enclosing = _enclosing_repo(matched.path, observed.values())
    kind = matched.marker_kind
    descriptor_warnings = list(warnings)
    if enclosing is not None:
        kind = ContextKind.NESTED_REPO
        descriptor_warnings.append(
            f"Nested repository {matched.path} inside enclosing repository {enclosing.path}"
        )

    return ContextDescriptor(
        kind=kind,
        resolved_path=str(resolved_path),
        workspace_identity=manifest.workspace_identity,
        repository_identity=matched.identity,
        repo_set=entries,
        capabilities=Capabilities(git_repo=True),
        warnings=descriptor_warnings,
    )


def _coerce_manifest(
    workspace_manifest: WorkspaceManifest | str | Path,
) -> WorkspaceManifest:
    if isinstance(workspace_manifest, WorkspaceManifest):
        return workspace_manifest
    return load_manifest(workspace_manifest)


def _normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _repository_path(workspace_root: Path, repository_path: str) -> Path:
    path = Path(repository_path)
    if not path.is_absolute():
        path = workspace_root / path
    return _normalize_path(path)


def _declared_repositories(
    workspace_root: Path,
    manifest: WorkspaceManifest,
) -> dict[Path, str]:
    declared: dict[Path, str] = {}

    for declaration in manifest.repositories:
        repo_path = _repository_path(workspace_root, declaration.path)
        existing_identity = declared.get(repo_path)
        if existing_identity is not None:
            if existing_identity != declaration.identity:
                raise ManifestError(
                    "repository path collision after normalization: "
                    f"{declaration.path!r} maps to {repo_path} with identities "
                    f"{existing_identity!r} and {declaration.identity!r}"
                )
            continue
        declared[repo_path] = declaration.identity

    return declared


def _observe_repositories(
    workspace_root: Path,
    resolved_path: Path,
    declared: dict[Path, str],
) -> tuple[dict[Path, _ObservedRepo], tuple[str, ...]]:
    observed: dict[Path, _ObservedRepo] = {}
    warnings: list[str] = []

    for repo_path, identity in declared.items():
        marker_kind = _git_marker_kind(repo_path)
        if marker_kind is not None:
            observed[repo_path] = _ObservedRepo(repo_path, identity, marker_kind)

    children, child_warnings = _immediate_children(workspace_root)
    warnings.extend(child_warnings)
    for child in children:
        marker_kind = _git_marker_kind(child)
        if marker_kind is not None and child not in observed:
            observed[child] = _ObservedRepo(
                child,
                _observed_identity(workspace_root, child),
                marker_kind,
            )

    for ancestor in _candidate_ancestors(workspace_root, resolved_path):
        marker_kind = _git_marker_kind(ancestor)
        if marker_kind is not None and ancestor not in observed:
            observed[ancestor] = _ObservedRepo(
                ancestor,
                _observed_identity(workspace_root, ancestor),
                marker_kind,
            )

    return observed, tuple(warnings)


def _immediate_children(workspace_root: Path) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    if not workspace_root.is_dir():
        return (), ()
    try:
        children = sorted(
            (child for child in workspace_root.iterdir() if child.is_dir()),
            key=lambda child: str(child),
        )
    except OSError as exc:
        return (), (f"Could not list workspace children: {workspace_root}: {exc}",)
    return tuple(children), ()


def _candidate_ancestors(workspace_root: Path, resolved_path: Path) -> tuple[Path, ...]:
    if not _is_relative_to(resolved_path, workspace_root):
        return ()

    ancestors: list[Path] = [resolved_path]
    ancestors.extend(resolved_path.parents)
    return tuple(
        ancestor
        for ancestor in ancestors
        if ancestor == workspace_root or _is_relative_to(ancestor, workspace_root)
    )


def _git_marker_kind(path: Path) -> ContextKind | None:
    git_marker = path / ".git"
    if git_marker.is_dir():
        return ContextKind.GIT_REPO
    if git_marker.is_file():
        try:
            with git_marker.open("r", encoding="utf-8", errors="replace") as marker:
                prefix = marker.read(len(_GITDIR_PREFIX))
        except OSError:
            return None
        if prefix == _GITDIR_PREFIX:
            return ContextKind.GIT_WORKTREE
    return None


def _build_repo_set(
    workspace_root: Path,
    declared: dict[Path, str],
    observed: dict[Path, _ObservedRepo],
) -> tuple[tuple[RepoEntry, ...], list[str]]:
    entries: list[RepoEntry] = []
    warnings: list[str] = []

    for repo_path, identity in declared.items():
        if repo_path in observed:
            entries.append(
                RepoEntry(
                    path=str(repo_path),
                    identity=identity,
                    status=RepoStatus.DECLARED_OBSERVED,
                )
            )
        else:
            entries.append(
                RepoEntry(
                    path=str(repo_path),
                    identity=identity,
                    status=RepoStatus.DECLARED_MISSING,
                )
            )
            warnings.append(f"Declared repository missing on disk: {repo_path}")

    for repo_path, observed_repo in observed.items():
        if repo_path not in declared:
            entries.append(
                RepoEntry(
                    path=str(repo_path),
                    identity=observed_repo.identity,
                    status=RepoStatus.OBSERVED_UNDECLARED,
                )
            )
            warnings.append(
                "Observed undeclared repository: "
                f"{_display_path(workspace_root, repo_path)}"
            )

    return (
        tuple(sorted(entries, key=lambda entry: (entry.path, entry.identity))),
        sorted(warnings),
    )


def _longest_repo_match(
    resolved_path: Path,
    observed_repositories: Iterable[_ObservedRepo],
) -> _ObservedRepo | None:
    matches = [
        repo for repo in observed_repositories if _is_relative_to(resolved_path, repo.path)
    ]
    if not matches:
        return None
    return max(matches, key=lambda repo: (len(repo.path.parts), str(repo.path)))


def _enclosing_repo(
    repo_path: Path,
    observed_repositories: Iterable[_ObservedRepo],
) -> _ObservedRepo | None:
    matches = [
        repo
        for repo in observed_repositories
        if repo.path != repo_path and _is_relative_to(repo_path, repo.path)
    ]
    if not matches:
        return None
    return max(matches, key=lambda repo: (len(repo.path.parts), str(repo.path)))


def _observed_identity(workspace_root: Path, repo_path: Path) -> str:
    return f"observed:{_display_path(workspace_root, repo_path)}"


def _display_path(workspace_root: Path, path: Path) -> str:
    if _is_relative_to(path, workspace_root):
        return path.relative_to(workspace_root).as_posix() or "."
    return str(path)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
