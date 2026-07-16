"""Context resolution primitives."""

from master_runtime.core.context.descriptor import (
    Capabilities,
    ContextDescriptor,
    ContextKind,
    RepoEntry,
    RepoStatus,
)
from master_runtime.core.context.manifest import (
    ManifestError,
    RepositoryDeclaration,
    WorkspaceManifest,
    load_manifest,
)
from master_runtime.core.context.resolver import resolve

__all__ = [
    "Capabilities",
    "ContextDescriptor",
    "ContextKind",
    "ManifestError",
    "RepoEntry",
    "RepoStatus",
    "RepositoryDeclaration",
    "WorkspaceManifest",
    "load_manifest",
    "resolve",
]
