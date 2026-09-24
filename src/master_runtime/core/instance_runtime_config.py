"""Load instance-owned runtime facts written during onboarding.

Instance facts (which agent CLI hosts the master, where each runtime keeps
session transcripts, optional product repositories) must not be baked into the
template. Onboarding writes them to an instance config file; consumers resolve
values with a fixed fallback order and refuse to invent defaults.

Fallback order for every value:
  1. environment override
  2. instance config file
  3. honest "unconfigured" (never a baked guess)

Default config path is ``<repo>/config/instance-runtime.json``. Override the
path with ``INSTANCE_RUNTIME_CONFIG``. The template ships only
``config/instance-runtime.example.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RELATIVE_CONFIG_PATH = Path("config") / "instance-runtime.json"
CONFIG_PATH_ENV = "INSTANCE_RUNTIME_CONFIG"
MASTER_HOST_RUNTIME_ENV = "MOGUI_MASTER_HOST_RUNTIME"
# Alternate name used by some instance wrappers (measured 2026-08-04).
MASTER_HOST_RUNTIME_ENV_ALT = "MASTER_HOST_RUNTIME"
TRANSCRIPT_GLOB_ENV = "MOGUI_TRANSCRIPT_GLOB"
PRODUCT_REPO_ENV = "MOGUI_PRODUCT_REPO"


class InstanceRuntimeConfigError(ValueError):
    """Raised when a required instance runtime fact is unconfigured or invalid."""


@dataclass(frozen=True)
class InstanceRuntimeConfig:
    """Resolved instance runtime facts. Missing optional fields stay None."""

    master_host_runtime: str | None
    transcript_globs: Mapping[str, str]
    product_repositories: tuple[str, ...]
    source_path: Path | None
    transcript_glob_env_override: str | None = None
    warnings: tuple[str, ...] = ()

    def require_master_host_runtime(self) -> str:
        if self.master_host_runtime is None or not self.master_host_runtime.strip():
            raise InstanceRuntimeConfigError(
                "master_host_runtime is unconfigured: set "
                f"{MASTER_HOST_RUNTIME_ENV} (or {MASTER_HOST_RUNTIME_ENV_ALT}), "
                "or write master_host_runtime in the instance config file "
                f"(default {DEFAULT_RELATIVE_CONFIG_PATH}; override path with "
                f"{CONFIG_PATH_ENV})"
            )
        return self.master_host_runtime.strip()

    def require_transcript_glob(self, runtime: str | None = None) -> str:
        name = (runtime or self.master_host_runtime or "").strip()
        if not name:
            raise InstanceRuntimeConfigError(
                "transcript_glob is unconfigured: pass a runtime name, or "
                "configure master_host_runtime first"
            )
        if self.transcript_glob_env_override is not None and self.transcript_glob_env_override.strip():
            return self.transcript_glob_env_override.strip()
        glob = self.transcript_globs.get(name)
        if glob is None or not str(glob).strip():
            raise InstanceRuntimeConfigError(
                f"transcript_glob for runtime {name!r} is unconfigured: set "
                f"{TRANSCRIPT_GLOB_ENV}, or write transcript_globs.{name} in "
                f"the instance config file (default {DEFAULT_RELATIVE_CONFIG_PATH}; "
                f"override path with {CONFIG_PATH_ENV})"
            )
        return str(glob).strip()

    def require_product_repositories(self) -> tuple[str, ...]:
        if not self.product_repositories:
            raise InstanceRuntimeConfigError(
                "product_repositories is unconfigured: set "
                f"{PRODUCT_REPO_ENV}, or write product_repositories (array) or "
                "product_repo (one-entry string) in the instance config file "
                f"(default {DEFAULT_RELATIVE_CONFIG_PATH}; override path with "
                f"{CONFIG_PATH_ENV})"
            )
        # Validated lazily, here, rather than at load(): MOGUI_PRODUCT_REPO is
        # also used elsewhere in this repo with owner/repo slug semantics
        # (dispatch-collision-check), and a caller that never asks for product
        # repositories (e.g. model-identity-probe) must not crash just because
        # that unrelated env var happens to be set when it loads the config.
        return tuple(
            _require_absolute_path(entry, "product_repositories")
            for entry in self.product_repositories
        )


def default_config_path(repo_root: Path | None = None) -> Path:
    # Prefer an explicit root. When omitted, locate the repository from this
    # module path (src/master_runtime/core/...) rather than Path.cwd(), so a
    # probe launched from another directory still finds config/instance-runtime.json.
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
    from_env = env.get(CONFIG_PATH_ENV)
    if from_env is not None and from_env.strip():
        return Path(from_env).expanduser().resolve()
    return default_config_path(repo_root)


def load_instance_runtime_config(
    path: Path | str | None = None,
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> InstanceRuntimeConfig:
    """Load config from disk (if present) and apply env overrides.

    A missing config file is not an error: values may still come from the
    environment. Callers that need a value use the require_* helpers, which
    raise InstanceRuntimeConfigError when the value is unconfigured.
    """
    env = dict(environ) if environ is not None else dict(os.environ)
    config_path = resolve_config_path(path, repo_root=repo_root, environ=env)
    payload = _read_payload(config_path)

    file_master = _config_optional_str(payload.get("master_host_runtime"), "master_host_runtime")
    file_globs = _parse_transcript_globs(payload.get("transcript_globs"))

    master = (
        _optional_str(env.get(MASTER_HOST_RUNTIME_ENV))
        or _optional_str(env.get(MASTER_HOST_RUNTIME_ENV_ALT))
        or file_master
    )
    # Env transcript glob is runtime-agnostic so a single override can target
    # the active probe without inventing per-runtime env var names.
    transcript_env = _optional_str(env.get(TRANSCRIPT_GLOB_ENV))

    product_env = _optional_str(env.get(PRODUCT_REPO_ENV))
    if product_env is not None:
        # Not validated here: see require_product_repositories(), which is
        # where this is checked lazily.
        product_repositories: tuple[str, ...] = (product_env,)
        warnings: tuple[str, ...] = ()
    else:
        product_repositories, warnings = _parse_product_repositories(payload)

    return InstanceRuntimeConfig(
        master_host_runtime=master,
        transcript_globs=file_globs,
        product_repositories=product_repositories,
        source_path=config_path if config_path.is_file() else None,
        transcript_glob_env_override=transcript_env,
        warnings=warnings,
    )


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstanceRuntimeConfigError(
            f"instance runtime config is not valid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise InstanceRuntimeConfigError(
            f"instance runtime config root must be a JSON object: {path}"
        )
    # Keys starting with "_" are documentation / comments in the example file.
    return {key: value for key, value in raw.items() if not str(key).startswith("_")}


def _parse_transcript_globs(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InstanceRuntimeConfigError(
            "transcript_globs must be a JSON object mapping runtime name to glob"
        )
    globs: dict[str, str] = {}
    for key, raw in value.items():
        if str(key).startswith("_"):
            continue
        if not isinstance(key, str) or not key.strip():
            raise InstanceRuntimeConfigError(
                "transcript_globs keys must be non-empty runtime names"
            )
        if not isinstance(raw, str) or not raw.strip():
            raise InstanceRuntimeConfigError(
                f"transcript_globs[{key!r}] must be a non-empty string glob"
            )
        globs[key.strip()] = raw.strip()
    return globs


def _parse_product_repositories(payload: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve product_repositories (canonical array) vs product_repo (one-entry string).

    product_repositories wins when both are present, with a warning naming the
    redundancy. Returns (repositories, warnings).
    """
    raw_list = payload.get("product_repositories")
    raw_string = payload.get("product_repo")

    if raw_list is not None:
        if not isinstance(raw_list, list) or not raw_list:
            raise InstanceRuntimeConfigError(
                "product_repositories must be a non-empty array of absolute paths"
            )
        repos_from_list = tuple(
            _require_absolute_path(entry, "product_repositories") for entry in raw_list
        )
        # product_repositories wins outright: a malformed legacy product_repo
        # must not block a valid array, so it is never validated here, only
        # checked for presence to raise the redundancy warning.
        warnings = (
            (
                "product_repositories and product_repo are both set in the "
                "instance runtime config; product_repositories wins and "
                "product_repo is ignored",
            )
            if _product_repo_is_present(raw_string)
            else ()
        )
        return repos_from_list, warnings

    if raw_string is not None:
        if not isinstance(raw_string, str):
            raise InstanceRuntimeConfigError(
                "product_repo must be a string or null in the instance runtime config"
            )
        stripped = raw_string.strip()
        if stripped:
            return (_require_absolute_path(stripped, "product_repo"),), ()

    return (), ()


def _product_repo_is_present(raw_string: object) -> bool:
    if raw_string is None:
        return False
    if isinstance(raw_string, str):
        return bool(raw_string.strip())
    return True


def _require_absolute_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstanceRuntimeConfigError(f"{field} entries must be non-empty strings")
    stripped = value.strip()
    expanded = os.path.expanduser(stripped)
    if not os.path.isabs(expanded):
        raise InstanceRuntimeConfigError(f"{field} entries must be absolute paths: {stripped!r}")
    # Only expand "~"; os.path.abspath/realpath would rewrite an already-absolute
    # POSIX-style path (e.g. "/repo-one") into a drive-rooted Windows path on that
    # platform, which is not what "expand ~" was asking for.
    return expanded


def _optional_str(value: object) -> str | None:
    """Coerce env values: non-strings and blank strings are treated as unset."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _config_optional_str(value: object, field: str) -> str | None:
    """Read an optional string field from the config file.

    Wrong types are hard errors so a corrupted onboarding write is not
    silently folded into "unconfigured".
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise InstanceRuntimeConfigError(
            f"{field} must be a string or null in the instance runtime config"
        )
    stripped = value.strip()
    return stripped or None
