import json
import os
import subprocess
from pathlib import Path


from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "scripts" / "claude-worker-pretrust"


def run_pretrust(
    worktree_path: str,
    config_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy() if env is None else env
    run_env["CLAUDE_CONFIG_PATH"] = str(config_path)
    return subprocess.run(
        [str(SCRIPT), worktree_path],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


def test_fresh_add_to_existing_config(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    config_path.write_text(json.dumps({"userID": "abc"}, indent=2), encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert "Summary: added" in result.stdout
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["userID"] == "abc"
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True


def test_fresh_add_when_config_file_is_absent(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert "Summary: added" in result.stdout
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = {
        "projects": {
            "/tmp/worktree": {"hasTrustDialogAccepted": True, "allowedTools": []}
        }
    }
    config_path.write_text(json.dumps(original, indent=2), encoding="utf-8")
    before = config_path.read_bytes()

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert "Summary: already trusted" in result.stdout
    assert config_path.read_bytes() == before


def test_existing_project_without_trust_is_updated_in_place(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = {
        "projects": {
            "/tmp/worktree": {
                "hasTrustDialogAccepted": False,
                "allowedTools": ["Bash"],
            },
            "/tmp/other": {"hasTrustDialogAccepted": True},
        }
    }
    config_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert "Summary: updated" in result.stdout
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True
    assert data["projects"]["/tmp/worktree"]["allowedTools"] == ["Bash"]
    assert data["projects"]["/tmp/other"] == {"hasTrustDialogAccepted": True}


def test_malformed_file_is_refused_without_writing(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = "{not json"
    config_path.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 2
    assert "cannot parse JSON" in result.stderr
    assert config_path.read_text(encoding="utf-8") == original


def test_other_project_entries_are_untouched(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = {
        "anonymousId": "xyz",
        "projects": {
            "/tmp/alpha": {"hasTrustDialogAccepted": True, "allowedTools": ["Edit"]},
            "/tmp/beta": {"hasTrustDialogAccepted": False},
        },
    }
    config_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["anonymousId"] == "xyz"
    assert data["projects"]["/tmp/alpha"] == original["projects"]["/tmp/alpha"]
    assert data["projects"]["/tmp/beta"] == original["projects"]["/tmp/beta"]
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True


def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    config_path.write_text("{}", encoding="utf-8")

    result = run_pretrust("relative/worktree", config_path)

    assert result.returncode != 0
    assert "worktree path must be absolute" in result.stderr


def test_malformed_top_level_is_refused_without_writing(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = "[]"
    config_path.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 2
    assert "top-level value is not an object" in result.stderr
    assert config_path.read_text(encoding="utf-8") == original


def test_invalid_utf8_is_refused_without_writing(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = b"\x80\x81invalid"
    config_path.write_bytes(original)

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 2
    assert "cannot parse JSON" in result.stderr
    assert config_path.read_bytes() == original


def test_nan_constant_is_refused_without_writing(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = '{"x": NaN}'
    config_path.write_text(original, encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 2
    assert "cannot parse JSON" in result.stderr
    assert config_path.read_text(encoding="utf-8") == original


def test_non_ascii_content_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    original = {"fullName": "José Müller \U0001F600", "projects": {}}
    config_path.write_text(
        json.dumps(original, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    raw = config_path.read_text(encoding="utf-8")
    assert original["fullName"] in raw
    assert "\\u00e9" not in raw
    data = json.loads(raw)
    assert data["fullName"] == original["fullName"]
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True


def test_write_does_not_leave_a_temp_file_behind(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    config_path.write_text("{}", encoding="utf-8")

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [".claude.json"]


def test_existing_file_mode_is_preserved(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"
    config_path.write_text("{}", encoding="utf-8")
    config_path.chmod(0o600)

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert (config_path.stat().st_mode & 0o777) == 0o600


def test_fresh_file_is_created_with_a_restrictive_mode(tmp_path: Path) -> None:
    config_path = tmp_path / ".claude.json"

    result = run_pretrust("/tmp/worktree", config_path)

    assert result.returncode == 0
    assert (config_path.stat().st_mode & 0o777) == 0o600


def test_symlinked_config_path_updates_the_real_target(tmp_path: Path) -> None:
    real_target = tmp_path / "real-home" / ".claude.json"
    real_target.parent.mkdir()
    real_target.write_text("{}", encoding="utf-8")
    link_path = tmp_path / "link.json"
    link_path.symlink_to(real_target)

    result = run_pretrust("/tmp/worktree", link_path)

    assert result.returncode == 0
    assert link_path.is_symlink()
    data = json.loads(real_target.read_text(encoding="utf-8"))
    assert data["projects"]["/tmp/worktree"]["hasTrustDialogAccepted"] is True
