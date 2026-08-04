"""Load the workspace descriptor inventory written during onboarding.

The workspace root is a plain folder of sibling repositories, never a
submodule parent. The descriptor is the declarative inventory of those
siblings: path, role, capabilities, and prohibited actions. Consumers
resolve facts with a fixed fallback order and refuse to invent defaults.

Fallback order for the descriptor payload:
  1. environment override path (WORKSPACE_DESCRIPTOR / MOGUI_WORKSPACE_DESCRIPTOR)
  2. instance config file (default <repo>/config/workspace-descriptor.json)
  3. honest "unconfigured" (never a baked inventory)

The template ships only config/workspace-descriptor.example.json.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_RELATIVE_CONFIG_PATH = Path("config") / "workspace-descriptor.json"
CONFIG_PATH_ENV = "WORKSPACE_DESCRIPTOR"
CONFIG_PATH_ENV_ALT = "MOGUI_WORKSPACE_DESCRIPTOR"

ALLOWED_ROLES = frozenset({"product", "ops"})
# Documented floor values; the open sets accept additional strings so an
# installation can name local lanes without a schema bump.
KNOWN_CAPABILITIES = frozenset({"pr", "dispatch-target"})
KNOWN_PROHIBITIONS = frozenset({"direct-main-commit", "force-push"})


class WorkspaceDescriptorError(ValueError):
    """Raised when the descriptor is unconfigured or invalid."""


@dataclass(frozen=True)
class RepositoryDescriptor:
    """One member repository in the workspace inventory."""

    name: str
    path: str
    remote: str
    role: str
    capabilities: tuple[str, ...]
    prohibited: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceDescriptor:
    """Resolved workspace inventory. Missing file stays unconfigured."""

    workspace_root_is_plain_folder: bool
    master_seat: str
    repositories: tuple[RepositoryDescriptor, ...]
    source_path: Path | None
    workspace_root: str | None = None

    def repository_for_path(self, path: str | Path) -> RepositoryDescriptor | None:
        """Match a path to a repository by declared relative path or exact name.

        Matching rules (unique hit required; ambiguous hits raise):
        - exact match of the declared relative ``path`` (including ``.``)
        - exact match of the declared ``name`` when the candidate has no
          path separator (``widget`` matches name ``widget``)
        - absolute candidate: only when ``workspace_root`` is set on this
          descriptor, the candidate is under that root, and the relative
          remainder equals the declared path (so ``/other/widget`` cannot
          steal the identity of ``widget`` under a different parent)

        Relative multi-segment candidates that are not exact equals never match
        by basename alone (``other/app`` does not match ``services/app``).
        Absolute candidates without a bound ``workspace_root`` never match.
        """
        raw = Path(path)
        if not str(path).strip():
            return None

        # Prefer resolving absolute inputs against the bound workspace root.
        relative_from_root: str | None = None
        if raw.is_absolute():
            if not self.workspace_root:
                return None
            root = Path(self.workspace_root).expanduser().resolve(strict=False)
            try:
                relative_from_root = (
                    raw.expanduser().resolve(strict=False).relative_to(root).as_posix()
                )
            except ValueError:
                return None
            if relative_from_root in {"", "."}:
                relative_from_root = "."
            candidate_str = relative_from_root
        else:
            candidate_str = raw.as_posix().rstrip("/")
            if candidate_str == "":
                return None
            if candidate_str == ".":
                candidate_str = "."

        matches: list[RepositoryDescriptor] = []
        for repo in self.repositories:
            declared = repo.path.rstrip("/") if repo.path != "." else "."
            if candidate_str == declared:
                matches.append(repo)
                continue
            if (
                candidate_str != "."
                and "/" not in candidate_str
                and candidate_str == repo.name
            ):
                matches.append(repo)

        if not matches:
            return None
        if len(matches) > 1:
            names = ", ".join(sorted({m.name for m in matches}))
            raise WorkspaceDescriptorError(
                f"path {candidate_str!r} matches multiple repository entries: {names}"
            )
        return matches[0]

    def is_prohibited(
        self,
        path: str | Path,
        action: str,
        *,
        default_when_unknown_repo: bool = True,
    ) -> bool:
        """Return whether ``action`` is prohibited for the repository at ``path``.

        When the path matches no inventory entry, default_when_unknown_repo
        controls the answer (True = fail closed / treat as prohibited).
        """
        action_key = action.strip()
        if not action_key:
            raise WorkspaceDescriptorError("action must be a non-empty string")
        repo = self.repository_for_path(path)
        if repo is None:
            return default_when_unknown_repo
        return action_key in repo.prohibited

    def require_repositories(self) -> tuple[RepositoryDescriptor, ...]:
        if not self.repositories:
            raise WorkspaceDescriptorError(
                "workspace descriptor has no repositories: write repositories "
                f"in the instance descriptor file (default {DEFAULT_RELATIVE_CONFIG_PATH}; "
                f"override path with {CONFIG_PATH_ENV} or {CONFIG_PATH_ENV_ALT})"
            )
        return self.repositories


def default_config_path(repo_root: Path | None = None) -> Path:
    if repo_root is not None:
        root = repo_root
    else:
        root = Path(__file__).resolve().parents[3]
    return (root / DEFAULT_RELATIVE_CONFIG_PATH).resolve()


def resolve_config_path(
    explicit: Path | str | None = None,
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    for key in (CONFIG_PATH_ENV, CONFIG_PATH_ENV_ALT):
        from_env = env.get(key)
        if from_env is not None and from_env.strip():
            return Path(from_env).expanduser().resolve()
    return default_config_path(repo_root)


def load_workspace_descriptor(
    path: Path | str | None = None,
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> WorkspaceDescriptor:
    """Load the descriptor from disk when present.

    A missing file is not an error: callers that need inventory use
    require_repositories or is_prohibited after checking source_path.
    """
    env = dict(environ) if environ is not None else dict(os.environ)
    config_path = resolve_config_path(path, repo_root=repo_root, environ=env)
    if not config_path.is_file():
        return WorkspaceDescriptor(
            workspace_root_is_plain_folder=True,
            master_seat="",
            repositories=(),
            source_path=None,
            workspace_root=None,
        )
    payload = _read_payload(config_path)
    return _parse_descriptor(payload, source_path=config_path)


def action_is_prohibited(
    path: str | Path,
    action: str,
    *,
    config_path: Path | str | None = None,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    default_when_unknown_repo: bool = True,
) -> bool:
    """Convenience: load descriptor and test one path/action pair.

    Raises WorkspaceDescriptorError when no descriptor file is configured.
    """
    descriptor = load_workspace_descriptor(
        config_path, repo_root=repo_root, environ=environ
    )
    if descriptor.source_path is None:
        raise WorkspaceDescriptorError(
            "workspace descriptor is unconfigured: set "
            f"{CONFIG_PATH_ENV} (or {CONFIG_PATH_ENV_ALT}), or write "
            f"{DEFAULT_RELATIVE_CONFIG_PATH} during onboarding"
        )
    return descriptor.is_prohibited(
        path,
        action,
        default_when_unknown_repo=default_when_unknown_repo,
    )


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise WorkspaceDescriptorError(
            f"workspace descriptor is not valid UTF-8: {path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceDescriptorError(
            f"workspace descriptor is not valid JSON: {path}: {exc}"
        ) from exc
    except OSError as exc:
        raise WorkspaceDescriptorError(
            f"cannot read workspace descriptor: {path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise WorkspaceDescriptorError(
            f"workspace descriptor root must be a JSON object: {path}"
        )
    return {key: value for key, value in raw.items() if not str(key).startswith("_")}


def _parse_descriptor(payload: Mapping[str, Any], *, source_path: Path) -> WorkspaceDescriptor:
    plain = payload.get("workspace_root_is_plain_folder", True)
    if not isinstance(plain, bool):
        raise WorkspaceDescriptorError(
            "workspace_root_is_plain_folder must be a boolean"
        )
    if plain is not True:
        raise WorkspaceDescriptorError(
            "workspace_root_is_plain_folder must be true: this runtime rejects "
            "submodule parents and non-plain workspace roots"
        )

    master_seat = payload.get("master_seat", "")
    if master_seat is None:
        master_seat = ""
    if not isinstance(master_seat, str):
        raise WorkspaceDescriptorError("master_seat must be a string")

    workspace_root_raw = payload.get("workspace_root")
    if workspace_root_raw is None or workspace_root_raw == "":
        workspace_root: str | None = None
    elif not isinstance(workspace_root_raw, str):
        raise WorkspaceDescriptorError("workspace_root must be a string or null")
    else:
        workspace_root = workspace_root_raw.strip() or None

    raw_repos = payload.get("repositories")
    if raw_repos is None:
        repositories: tuple[RepositoryDescriptor, ...] = ()
    else:
        if not isinstance(raw_repos, list):
            raise WorkspaceDescriptorError("repositories must be a JSON array")
        repositories = tuple(
            _parse_repository(entry, index) for index, entry in enumerate(raw_repos)
        )
        _reject_duplicate_identity(repositories)

    return WorkspaceDescriptor(
        workspace_root_is_plain_folder=True,
        master_seat=master_seat.strip(),
        repositories=repositories,
        source_path=source_path,
        workspace_root=workspace_root,
    )



def _reject_duplicate_identity(repositories: Sequence[RepositoryDescriptor]) -> None:
    seen_paths: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    for repo in repositories:
        path_key = repo.path.rstrip("/")
        if path_key in seen_paths:
            raise WorkspaceDescriptorError(
                f"duplicate repository path {path_key!r} "
                f"(entries {seen_paths[path_key]!r} and {repo.name!r})"
            )
        seen_paths[path_key] = repo.name
        if repo.name in seen_names:
            raise WorkspaceDescriptorError(
                f"duplicate repository name {repo.name!r} "
                f"(paths {seen_names[repo.name]!r} and {path_key!r})"
            )
        seen_names[repo.name] = path_key


def _parse_repository(entry: object, index: int) -> RepositoryDescriptor:
    if not isinstance(entry, Mapping):
        raise WorkspaceDescriptorError(
            f"repositories[{index}] must be a JSON object"
        )
    name = _required_string(entry, "name", index)
    path = _required_string(entry, "path", index)
    remote = entry.get("remote", "")
    if remote is None:
        remote = ""
    if not isinstance(remote, str):
        raise WorkspaceDescriptorError(
            f"repositories[{index}].remote must be a string"
        )
    role = _required_string(entry, "role", index)
    if role not in ALLOWED_ROLES:
        raise WorkspaceDescriptorError(
            f"repositories[{index}].role must be one of {sorted(ALLOWED_ROLES)}, got {role!r}"
        )
    # capabilities may be omitted (defaults to empty). prohibited must be present
    # as an array — missing/null is invalid so product defaults cannot vanish by
    # accident; an explicit [] is the owner-confirmed "no prohibitions" choice.
    if "capabilities" not in entry:
        capabilities: tuple[str, ...] = ()
    else:
        capabilities = _string_list(
            entry.get("capabilities"), f"repositories[{index}].capabilities"
        )
    if "prohibited" not in entry or entry.get("prohibited") is None:
        raise WorkspaceDescriptorError(
            f"repositories[{index}].prohibited must be present "
            "(use an empty array only when the owner confirmed no prohibitions)"
        )
    prohibited = _string_list(
        entry.get("prohibited"), f"repositories[{index}].prohibited"
    )
    return RepositoryDescriptor(
        name=name,
        path=path,
        remote=remote.strip(),
        role=role,
        capabilities=capabilities,
        prohibited=prohibited,
    )


def _required_string(entry: Mapping[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceDescriptorError(
            f"repositories[{index}].{key} must be a non-empty string"
        )
    return value.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise WorkspaceDescriptorError(f"{field} must be a JSON array of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WorkspaceDescriptorError(
                f"{field} entries must be non-empty strings"
            )
        items.append(item.strip())
    return tuple(items)
