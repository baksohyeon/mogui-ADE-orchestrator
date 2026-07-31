"""JSON config loading for acceptance runs.

JSON rather than TOML: this repository targets Python 3.10+ and stays stdlib-only,
so `tomllib` is not available across the supported range.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union

from master_runtime.core.acceptance.casebook import CaseBook, RegressionLog, load_casebook
from master_runtime.core.acceptance.models import AcceptanceConfig
from master_runtime.core.acceptance.proposer import (
    DEFAULT_PROPOSER_TIMEOUT_SECONDS,
    ProposerError,
    require_sync_cli_profile,
)


class AcceptanceConfigError(ValueError):
    """Raised when an acceptance config cannot be loaded."""


@dataclass(frozen=True)
class LoadedConfig:
    """One decoded acceptance config plus its case book."""

    config: AcceptanceConfig
    casebook: CaseBook
    regression_log: Optional[RegressionLog] = None


def load_acceptance_config(path: Union[str, Path]) -> LoadedConfig:
    """Load one acceptance config, resolving paths against the config file."""

    config_path = Path(path).resolve()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AcceptanceConfigError("cannot read config: {0}".format(config_path)) from exc
    except ValueError as exc:
        raise AcceptanceConfigError("invalid config JSON: {0}".format(config_path)) from exc
    if not isinstance(payload, Mapping):
        raise AcceptanceConfigError("config must be a JSON object")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AcceptanceConfigError("config requires a non-empty 'name'")

    base = config_path.parent
    workspace_root = _resolve(base, payload.get("workspace_root", "."))
    run_dir = _resolve(base, payload.get("run_dir", "runs/{0}".format(name.strip())))

    proposer = payload.get("proposer", {})
    if not isinstance(proposer, Mapping):
        raise AcceptanceConfigError("'proposer' must be an object")
    runtime = str(proposer.get("runtime", "")).strip().lower()
    # One rejection rule for runtime names: does a CLI profile resolve?
    try:
        require_sync_cli_profile(runtime)
    except ProposerError as exc:
        raise AcceptanceConfigError(str(exc)) from exc
    model = proposer.get("model")
    if model is not None and not isinstance(model, str):
        raise AcceptanceConfigError("'proposer.model' must be a string or null")

    config = AcceptanceConfig(
        name=name.strip(),
        run_dir=run_dir,
        workspace_root=workspace_root,
        max_iterations=_positive_int(payload.get("max_iterations", 3), "max_iterations"),
        proposer_runtime=runtime,
        proposer_model=model,
        proposer_timeout_seconds=_positive_int(
            proposer.get("timeout_seconds", DEFAULT_PROPOSER_TIMEOUT_SECONDS),
            "proposer.timeout_seconds",
        ),
    )

    casebook = load_casebook(payload)
    casebook.validate()

    regression_log = None
    raw_log = payload.get("regression_log")
    if isinstance(raw_log, str) and raw_log.strip():
        regression_log = RegressionLog(_resolve(base, raw_log))

    return LoadedConfig(config=config, casebook=casebook, regression_log=regression_log)


def _resolve(base: Path, raw: object) -> Path:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AcceptanceConfigError("'{0}' must be a positive integer".format(field))
    return value
