import json
import os
import subprocess
from pathlib import Path

from windows_exec_surface import skip_windows_exec_surface


pytestmark = skip_windows_exec_surface


SCRIPT = Path(__file__).parents[1] / "scripts" / "agy-worker-pretrust"


def run_pretrust(
    worktree_path: str,
    config_home: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy() if env is None else env.copy()
    if env is None:
        run_env.pop("AGY_SETTINGS_PATH", None)
    run_env["AGY_CONFIG_HOME"] = str(config_home)
    return subprocess.run(
        [str(SCRIPT), worktree_path],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


def settings_path(config_home: Path) -> Path:
    return config_home / "antigravity-cli" / "settings.json"


def test_fresh_add_preserves_existing_settings(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"keep": True, "trustedWorkspaces": ["/tmp/other"]}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data == {"keep": True, "trustedWorkspaces": ["/tmp/other", "/tmp/worktree"]}


def test_fresh_add_creates_settings_file(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert json.loads(settings_path(config_home).read_text(encoding="utf-8")) == {
        "trustedWorkspaces": ["/tmp/worktree"]
    }


def test_second_run_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)

    first = run_pretrust("/tmp/worktree", config_home)
    assert first.returncode == 0, first.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in first.stdout
    before = settings.read_bytes()

    second = run_pretrust("/tmp/worktree", config_home)

    assert second.returncode == 0, second.stderr
    assert "Summary: 0 added, 0 updated, 1 already trusted" in second.stdout
    assert settings.read_bytes() == before


def test_existing_trusted_file_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"trustedWorkspaces": ["/tmp/worktree"], "keep": "yes"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    before = settings.read_bytes()

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 0 added, 0 updated, 1 already trusted" in result.stdout
    assert settings.read_bytes() == before


def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust("relative/worktree", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "worktree path must be absolute" in result.stderr


def test_malformed_settings_are_refused_without_writing(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = "{not json"
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 2
    assert "cannot parse JSON" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_non_array_trusted_workspaces_are_refused(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = json.dumps({"trustedWorkspaces": {"/tmp/worktree": True}})
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 2
    assert "trustedWorkspaces must be an array of strings" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_null_trusted_workspaces_are_refused(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = json.dumps({"trustedWorkspaces": None})
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_home)

    assert result.returncode == 2
    assert "trustedWorkspaces must be an array of strings" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_explicit_settings_path_override_is_used(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    explicit_settings = tmp_path / "explicit-settings.json"
    explicit_settings.write_text('{"trustedWorkspaces": []}\n', encoding="utf-8")
    run_env = os.environ.copy()
    run_env["AGY_SETTINGS_PATH"] = str(explicit_settings)

    result = run_pretrust("/tmp/worktree", config_home, env=run_env)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert json.loads(explicit_settings.read_text(encoding="utf-8"))["trustedWorkspaces"] == [
        "/tmp/worktree"
    ]
    assert not settings_path(config_home).exists()
