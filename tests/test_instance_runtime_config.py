"""Instance runtime config: parsing and env → file → unconfigured fallback."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from master_runtime.core.instance_runtime_config import (
    CONFIG_PATH_ENV,
    MASTER_HOST_RUNTIME_ENV,
    MASTER_HOST_RUNTIME_ENV_ALT,
    PRODUCT_REPO_ENV,
    TRANSCRIPT_GLOB_ENV,
    InstanceRuntimeConfigError,
    load_instance_runtime_config,
)

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "model-identity-probe"
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLE = ROOT / "config" / "instance-runtime.example.json"


def _write_config(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_example_file_is_valid_json_with_documented_keys() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert "master_host_runtime" in payload
    assert "transcript_globs" in payload
    docs = payload.get("_docs")
    assert isinstance(docs, dict)
    for key in ("master_host_runtime", "transcript_globs", "product_repo"):
        assert key in docs
        assert docs[key].strip()


def test_env_overrides_file_for_master_host_runtime(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {
            "master_host_runtime": "codex",
            "transcript_globs": {"codex": "/tmp/codex/*.jsonl"},
        },
    )
    loaded = load_instance_runtime_config(
        config_path,
        environ={MASTER_HOST_RUNTIME_ENV: "claude"},
    )
    assert loaded.require_master_host_runtime() == "claude"


def test_file_value_used_when_env_absent(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {
            "master_host_runtime": "grok",
            "transcript_globs": {"grok": "/tmp/grok/*.jsonl"},
            "product_repo": "/tmp/product",
        },
    )
    loaded = load_instance_runtime_config(config_path, environ={})
    assert loaded.require_master_host_runtime() == "grok"
    assert loaded.require_transcript_glob("grok") == "/tmp/grok/*.jsonl"
    assert loaded.require_product_repo() == "/tmp/product"


def test_missing_file_and_env_is_honest_unconfigured(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    loaded = load_instance_runtime_config(missing, environ={})
    with pytest.raises(InstanceRuntimeConfigError, match="unconfigured"):
        loaded.require_master_host_runtime()
    with pytest.raises(InstanceRuntimeConfigError, match="unconfigured"):
        loaded.require_transcript_glob("claude")
    with pytest.raises(InstanceRuntimeConfigError, match="unconfigured"):
        loaded.require_product_repo()


def test_transcript_glob_env_overrides_file(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {
            "master_host_runtime": "claude",
            "transcript_globs": {"claude": "/from-file/*.jsonl"},
        },
    )
    loaded = load_instance_runtime_config(
        config_path,
        environ={TRANSCRIPT_GLOB_ENV: "/from-env/*.jsonl"},
    )
    assert loaded.require_transcript_glob("claude") == "/from-env/*.jsonl"


def test_product_repo_env_overrides_file(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {"product_repo": "/from-file"},
    )
    loaded = load_instance_runtime_config(
        config_path,
        environ={PRODUCT_REPO_ENV: "/from-env"},
    )
    assert loaded.require_product_repo() == "/from-env"


def test_underscore_doc_keys_are_ignored(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {
            "_docs": {"master_host_runtime": "documentation only"},
            "master_host_runtime": "cursor-agent",
            "transcript_globs": {
                "_note": "ignore me",
                "cursor-agent": "/tmp/cursor/*.jsonl",
            },
        },
    )
    loaded = load_instance_runtime_config(config_path, environ={})
    assert loaded.require_master_host_runtime() == "cursor-agent"
    assert loaded.transcript_globs == {"cursor-agent": "/tmp/cursor/*.jsonl"}


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(InstanceRuntimeConfigError, match="valid JSON"):
        load_instance_runtime_config(path, environ={})


def test_config_path_env_selects_file(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "elsewhere.json",
        {"master_host_runtime": "codex"},
    )
    loaded = load_instance_runtime_config(
        environ={CONFIG_PATH_ENV: str(config_path)},
    )
    assert loaded.require_master_host_runtime() == "codex"


def test_probe_resolves_transcript_from_config(tmp_path: Path) -> None:
    transcript_dir = tmp_path / "sessions"
    transcript_dir.mkdir()
    older = transcript_dir / "old.jsonl"
    newer = transcript_dir / "new.jsonl"
    older.write_text(
        json.dumps({"role": "assistant", "model": "stale-model"}) + "\n",
        encoding="utf-8",
    )
    newer.write_text(
        (FIXTURES / "model_identity_probe_ok.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {
            "master_host_runtime": "claude",
            "transcript_globs": {"claude": str(transcript_dir / "*.jsonl")},
        },
    )
    env = os.environ.copy()
    env.pop("MODEL_IDENTITY_EXPECT", None)
    env.pop(TRANSCRIPT_GLOB_ENV, None)
    env.pop(MASTER_HOST_RUNTIME_ENV, None)

    result = subprocess.run(
        [
            sys.executable,
            str(PROBE),
            "--config",
            str(config_path),
            "--expect",
            "claude-fable-5",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODEL-PROBE OK claude-fable-5" in result.stdout


def test_probe_reports_unconfigured_without_transcript_or_config(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        CONFIG_PATH_ENV: str(tmp_path / "missing.json"),
    }
    result = subprocess.run(
        [sys.executable, str(PROBE)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 2
    assert "unconfigured" in result.stdout


def test_probe_uses_transcript_glob_env_without_master_host(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        (FIXTURES / "model_identity_probe_ok.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("MODEL_IDENTITY_EXPECT", None)
    env.pop(MASTER_HOST_RUNTIME_ENV, None)
    env.pop(MASTER_HOST_RUNTIME_ENV_ALT, None)
    env[TRANSCRIPT_GLOB_ENV] = str(transcript)
    env[CONFIG_PATH_ENV] = str(tmp_path / "missing.json")

    result = subprocess.run(
        [
            sys.executable,
            str(PROBE),
            "--expect",
            "claude-fable-5",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),  # not the repo root
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODEL-PROBE OK claude-fable-5" in result.stdout


def test_wrong_type_for_master_host_runtime_is_hard_error(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "instance-runtime.json",
        {"master_host_runtime": ["claude"]},
    )
    with pytest.raises(InstanceRuntimeConfigError, match="must be a string"):
        load_instance_runtime_config(config_path, environ={})


def test_default_config_path_is_repo_relative_not_cwd(tmp_path: Path, monkeypatch) -> None:
    from master_runtime.core import instance_runtime_config as mod

    monkeypatch.chdir(tmp_path)
    path = mod.default_config_path()
    assert path == (ROOT / "config" / "instance-runtime.json").resolve()
