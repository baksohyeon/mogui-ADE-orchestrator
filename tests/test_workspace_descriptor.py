"""Workspace descriptor: parsing, env → file → unconfigured, prohibition check."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from master_runtime.core.workspace_descriptor import (
    CONFIG_PATH_ENV,
    WorkspaceDescriptorError,
    action_is_prohibited,
    load_workspace_descriptor,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config" / "workspace-descriptor.example.json"
CHECK = ROOT / "scripts" / "workspace-descriptor-check"


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_example_file_is_valid_json_with_documented_floor_fields() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert payload["workspace_root_is_plain_folder"] is True
    assert isinstance(payload["master_seat"], str) and payload["master_seat"]
    assert isinstance(payload["repositories"], list) and payload["repositories"]
    docs = payload["_docs"]
    for key in (
        "workspace_root_is_plain_folder",
        "master_seat",
        "repositories",
        "name",
        "path",
        "remote",
        "role",
        "capabilities",
        "prohibited",
    ):
        assert key in docs and docs[key].strip()
    for repo in payload["repositories"]:
        for field in ("name", "path", "remote", "role", "capabilities", "prohibited"):
            assert field in repo
        assert repo["role"] in {"product", "ops"}


def test_missing_file_is_honest_unconfigured(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    loaded = load_workspace_descriptor(missing, environ={})
    assert loaded.source_path is None
    assert loaded.repositories == ()
    with pytest.raises(WorkspaceDescriptorError, match="unconfigured"):
        action_is_prohibited("product", "direct-main-commit", config_path=missing, environ={})


def test_env_path_overrides_default_location(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "from-env.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "folder-workspace-of-workspace-root",
            "repositories": [
                {
                    "name": "app",
                    "path": "app",
                    "remote": "",
                    "role": "product",
                    "capabilities": ["pr"],
                    "prohibited": ["direct-main-commit", "force-push"],
                }
            ],
        },
    )
    other = _write(
        tmp_path / "other.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "x",
            "repositories": [],
        },
    )
    loaded = load_workspace_descriptor(
        other,
        environ={CONFIG_PATH_ENV: str(config)},
    )
    # Explicit path argument still wins over env (resolve_config_path).
    assert loaded.source_path == other.resolve()
    loaded_env = load_workspace_descriptor(
        None,
        repo_root=tmp_path,
        environ={CONFIG_PATH_ENV: str(config)},
    )
    assert loaded_env.source_path == config.resolve()
    assert loaded_env.require_repositories()[0].name == "app"


def test_product_direct_main_commit_is_prohibited(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "workspace-descriptor.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "folder-workspace-of-workspace-root",
            "repositories": [
                {
                    "name": "widget",
                    "path": "widget",
                    "remote": "https://example.invalid/widget.git",
                    "role": "product",
                    "capabilities": ["pr", "dispatch-target"],
                    "prohibited": ["direct-main-commit", "force-push"],
                },
                {
                    "name": "widget-ops",
                    "path": "widget-ops",
                    "remote": "",
                    "role": "ops",
                    "capabilities": ["pr", "dispatch-target"],
                    "prohibited": ["force-push"],
                },
            ],
        },
    )
    assert action_is_prohibited(
        "widget", "direct-main-commit", config_path=config, environ={}
    )
    # Bare name and declared relative path both resolve; single-segment absolute
    # paths do not suffix-match (would be ambiguous across parents).
    assert action_is_prohibited(
        "widget", "force-push", config_path=config, environ={}
    )
    assert not action_is_prohibited(
        "widget-ops", "direct-main-commit", config_path=config, environ={}
    )
    assert action_is_prohibited(
        "widget-ops", "force-push", config_path=config, environ={}
    )
    # Same basename under another relative parent is unknown → fail closed.
    assert action_is_prohibited(
        "other/widget",
        "direct-main-commit",
        config_path=config,
        environ={},
        default_when_unknown_repo=True,
    )
    assert not action_is_prohibited(
        "other/widget",
        "direct-main-commit",
        config_path=config,
        environ={},
        default_when_unknown_repo=False,
    )


def test_multi_segment_path_suffix_match(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "workspace-descriptor.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "folder-workspace-of-workspace-root",
            "repositories": [
                {
                    "name": "app",
                    "path": "services/app",
                    "remote": "",
                    "role": "product",
                    "capabilities": ["pr"],
                    "prohibited": ["direct-main-commit", "force-push"],
                }
            ],
        },
    )
    assert action_is_prohibited(
        "/workspace/root/services/app",
        "direct-main-commit",
        config_path=config,
        environ={},
    )
    # Different parent with same basename must not match.
    assert not action_is_prohibited(
        "/workspace/root/other/app",
        "direct-main-commit",
        config_path=config,
        environ={},
        default_when_unknown_repo=False,
    )


def test_missing_prohibited_field_is_invalid(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "no-prohibited.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "x",
            "repositories": [
                {
                    "name": "app",
                    "path": "app",
                    "remote": "",
                    "role": "product",
                    "capabilities": ["pr"],
                }
            ],
        },
    )
    with pytest.raises(WorkspaceDescriptorError, match="prohibited"):
        load_workspace_descriptor(config, environ={})


def test_duplicate_path_is_invalid(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "dup.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "x",
            "repositories": [
                {
                    "name": "a",
                    "path": "shared",
                    "remote": "",
                    "role": "product",
                    "capabilities": [],
                    "prohibited": ["direct-main-commit"],
                },
                {
                    "name": "b",
                    "path": "shared",
                    "remote": "",
                    "role": "product",
                    "capabilities": [],
                    "prohibited": [],
                },
            ],
        },
    )
    with pytest.raises(WorkspaceDescriptorError, match="duplicate repository path"):
        load_workspace_descriptor(config, environ={})


def test_invalid_utf8_is_undecidable(tmp_path: Path) -> None:
    path = tmp_path / "bad-utf8.json"
    path.write_bytes(b'{"workspace_root_is_plain_folder": true, "\xff": 1}')
    with pytest.raises(WorkspaceDescriptorError, match="UTF-8"):
        load_workspace_descriptor(path, environ={})


def test_rejects_non_plain_folder_flag(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "bad.json",
        {
            "workspace_root_is_plain_folder": False,
            "master_seat": "x",
            "repositories": [],
        },
    )
    with pytest.raises(WorkspaceDescriptorError, match="plain"):
        load_workspace_descriptor(config, environ={})


def test_rejects_invalid_role(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "bad-role.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "x",
            "repositories": [
                {
                    "name": "x",
                    "path": "x",
                    "remote": "",
                    "role": "library",
                    "capabilities": [],
                    "prohibited": [],
                }
            ],
        },
    )
    with pytest.raises(WorkspaceDescriptorError, match="role"):
        load_workspace_descriptor(config, environ={})


def test_cli_check_exit_codes(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "workspace-descriptor.json",
        {
            "workspace_root_is_plain_folder": True,
            "master_seat": "folder-workspace-of-workspace-root",
            "repositories": [
                {
                    "name": "app",
                    "path": "app",
                    "remote": "",
                    "role": "product",
                    "capabilities": ["pr"],
                    "prohibited": ["direct-main-commit"],
                }
            ],
        },
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    denied = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--config",
            str(config),
            "--path",
            "app",
            "--action",
            "direct-main-commit",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert denied.returncode == 1
    body = json.loads(denied.stdout)
    assert body["prohibited"] is True
    assert body["allow"] is False

    allowed = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--config",
            str(config),
            "--path",
            "app",
            "--action",
            "pr",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["allow"] is True

    missing = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--config",
            str(tmp_path / "missing.json"),
            "--path",
            "app",
            "--action",
            "direct-main-commit",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["decidable"] is False
