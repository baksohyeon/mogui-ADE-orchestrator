"""Descriptor data types for filesystem-derived workspace context."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContextKind(str, Enum):
    """Resolved context shape."""

    FOLDER = "folder"
    GIT_REPO = "git-repo"
    GIT_WORKTREE = "git-worktree"
    MULTI_REPO_WORKSPACE = "multi-repo-workspace"
    NESTED_REPO = "nested-repo"


class RepoStatus(str, Enum):
    """Relationship between manifest declarations and filesystem observations."""

    DECLARED_OBSERVED = "declared+observed"
    DECLARED_MISSING = "declared-missing"
    OBSERVED_UNDECLARED = "observed-undeclared"


@dataclass(frozen=True)
class RepoEntry:
    """A repository declaration or observation included in the workspace set."""

    path: str
    identity: str
    status: RepoStatus


@dataclass(frozen=True)
class Capabilities:
    """Minimal capability facts available from U2 context resolution."""

    git_repo: bool


@dataclass(frozen=True)
class ContextDescriptor:
    """Stable context descriptor returned by the resolver."""

    kind: ContextKind
    resolved_path: str
    workspace_identity: str
    repository_identity: str | None
    repo_set: tuple[RepoEntry, ...]
    capabilities: Capabilities
    warnings: list[str] = field(default_factory=list)
