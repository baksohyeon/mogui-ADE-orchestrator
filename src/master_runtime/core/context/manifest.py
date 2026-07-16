"""Workspace manifest parsing and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


class ManifestError(ValueError):
    """Raised when manifest input is missing or malformed."""


@dataclass(frozen=True)
class RepositoryDeclaration:
    """A repository declared by the workspace manifest."""

    path: str
    identity: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, init=False)
class WorkspaceManifest:
    """Validated workspace manifest data."""

    workspace_root: str
    workspace_identity: str
    repositories: tuple[RepositoryDeclaration, ...]
    metadata: Mapping[str, Any]

    def __init__(
        self,
        workspace_root: str | Path,
        workspace_identity: str,
        repositories: Iterable[RepositoryDeclaration | Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(workspace_identity, str) or not workspace_identity:
            raise ManifestError("workspace_identity must be a non-empty string")

        normalized_repositories = tuple(
            _coerce_repository(repository) for repository in repositories
        )

        object.__setattr__(self, "workspace_root", str(workspace_root))
        object.__setattr__(self, "workspace_identity", workspace_identity)
        object.__setattr__(self, "repositories", normalized_repositories)
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkspaceManifest":
        """Load a workspace manifest from a JSON file."""

        return load_manifest(path)


def load_manifest(path: str | Path) -> WorkspaceManifest:
    """Load and validate a JSON workspace manifest."""

    manifest_path = Path(path)
    if not manifest_path.exists():
        raise ManifestError(f"manifest file does not exist: {manifest_path}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid manifest JSON: {manifest_path}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot read manifest file: {manifest_path}") from exc

    if not isinstance(raw, Mapping):
        raise ManifestError("manifest must be a JSON object")

    workspace_root = _required_string(raw, "workspace_root")
    workspace_identity = _required_string(raw, "workspace_identity")
    repositories = raw.get("repositories")
    if not isinstance(repositories, list):
        raise ManifestError("manifest repositories must be a list")

    root_path = Path(workspace_root)
    if not root_path.is_absolute():
        root_path = manifest_path.parent / root_path

    metadata = raw.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ManifestError("manifest metadata must be an object")

    return WorkspaceManifest(
        workspace_root=root_path,
        workspace_identity=workspace_identity,
        repositories=repositories,
        metadata=dict(metadata or {}),
    )


def _coerce_repository(
    repository: RepositoryDeclaration | Mapping[str, Any],
) -> RepositoryDeclaration:
    if isinstance(repository, RepositoryDeclaration):
        return repository

    path = _required_string(repository, "path")
    identity = _required_string(repository, "identity")
    metadata = repository.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ManifestError("repository metadata must be an object")

    return RepositoryDeclaration(path=path, identity=identity, metadata=dict(metadata))


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"manifest key {key!r} must be a non-empty string")
    return value
