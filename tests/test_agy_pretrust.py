import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from windows_exec_surface import skip_windows_exec_surface


pytestmark = skip_windows_exec_surface


SCRIPT = Path(__file__).parents[1] / "scripts" / "agy-worker-pretrust"


def run_pretrust(
    worktree_path: str,
    config_home: Path,
    *,
    env: dict[str, str] | None = None,
    script: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy() if env is None else env.copy()
    if env is None:
        run_env.pop("AGY_SETTINGS_PATH", None)
    run_env["AGY_CONFIG_HOME"] = str(config_home)
    return subprocess.run(
        [str(SCRIPT if script is None else script), worktree_path],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


def settings_path(config_home: Path) -> Path:
    return config_home / "antigravity-cli" / "settings.json"


def make_worktree(tmp_path: Path, name: str = "worktree") -> Path:
    worktree = tmp_path / name
    worktree.mkdir()
    return worktree


def test_fresh_add_preserves_existing_settings(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"keep": True, "trustedWorkspaces": ["/tmp/other"]}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data == {"keep": True, "trustedWorkspaces": ["/tmp/other", str(worktree)]}


def test_fresh_add_creates_settings_file(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert json.loads(settings_path(config_home).read_text(encoding="utf-8")) == {
        "trustedWorkspaces": [str(worktree)]
    }


def test_second_run_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)

    first = run_pretrust(str(worktree), config_home)
    assert first.returncode == 0, first.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in first.stdout
    before = settings.read_bytes()

    second = run_pretrust(str(worktree), config_home)

    assert second.returncode == 0, second.stderr
    assert "Summary: 0 added, 0 updated, 1 already trusted" in second.stdout
    assert settings.read_bytes() == before


def test_existing_trusted_file_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"trustedWorkspaces": [str(worktree)], "keep": "yes"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    before = settings.read_bytes()

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 0, result.stderr
    assert "Summary: 0 added, 0 updated, 1 already trusted" in result.stdout
    assert settings.read_bytes() == before


def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust("relative/worktree", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "worktree path must be absolute" in result.stderr


def test_malformed_settings_are_refused_without_writing(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = "{not json"
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 2
    assert "cannot parse JSON" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_non_array_trusted_workspaces_are_refused(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = json.dumps({"trustedWorkspaces": {str(worktree): True}})
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 2
    assert "trustedWorkspaces must be an array of strings" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_null_trusted_workspaces_are_refused(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    settings = settings_path(config_home)
    settings.parent.mkdir(parents=True)
    original = json.dumps({"trustedWorkspaces": None})
    settings.write_text(original, encoding="utf-8")

    result = run_pretrust(str(worktree), config_home)

    assert result.returncode == 2
    assert "trustedWorkspaces must be an array of strings" in result.stderr
    assert settings.read_text(encoding="utf-8") == original


def test_explicit_settings_path_override_is_used(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)
    explicit_settings = tmp_path / "explicit-settings.json"
    explicit_settings.write_text('{"trustedWorkspaces": []}\n', encoding="utf-8")
    run_env = os.environ.copy()
    run_env["AGY_SETTINGS_PATH"] = str(explicit_settings)

    result = run_pretrust(str(worktree), config_home, env=run_env)

    assert result.returncode == 0, result.stderr
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert json.loads(explicit_settings.read_text(encoding="utf-8"))["trustedWorkspaces"] == [
        str(worktree)
    ]
    assert not settings_path(config_home).exists()


def test_trailing_slash_is_stripped_and_stored_once(tmp_path: Path) -> None:
    config_home = tmp_path / ".gemini"
    worktree = make_worktree(tmp_path)

    result = run_pretrust(f"{worktree}/", config_home)

    assert result.returncode == 0, result.stderr
    assert json.loads(settings_path(config_home).read_text(encoding="utf-8"))["trustedWorkspaces"] == [
        str(worktree)
    ]


def test_dot_component_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust(f"{tmp_path}/./worktree", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must not contain . or .. components" in result.stderr


def test_dot_dot_component_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust(f"{tmp_path}/../worktree", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must not contain . or .. components" in result.stderr


def test_glob_character_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust(f"{tmp_path}/worktree*", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must not contain glob characters" in result.stderr


def test_nonexistent_directory_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust(str(tmp_path / "missing"), tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must be an existing directory" in result.stderr


def test_filesystem_root_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust("/", tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must not be the filesystem root" in result.stderr


def test_home_directory_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust(str(Path.home()), tmp_path / ".gemini")

    assert result.returncode == 2
    assert "must not be the home directory" in result.stderr


def test_concurrent_runs_preserve_all_entries_and_catch_unlocked_mutant(
    tmp_path: Path,
) -> None:
    count = 30
    worktrees = [make_worktree(tmp_path, f"worktree-{index}") for index in range(count)]

    def run_many(
        config_home: Path,
        script: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> list[subprocess.CompletedProcess[str]]:
        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(
                executor.map(
                    lambda worktree: run_pretrust(
                        str(worktree), config_home, env=env, script=script
                    ),
                    worktrees,
                )
            )

    results = run_many(tmp_path / "locked-home" / ".gemini")
    assert all(result.returncode == 0 for result in results), [
        result.stderr for result in results if result.returncode != 0
    ]
    locked_entries = json.loads(
        settings_path(tmp_path / "locked-home" / ".gemini").read_text(encoding="utf-8")
    )["trustedWorkspaces"]
    assert len(locked_entries) == count
    assert set(locked_entries) == {str(worktree) for worktree in worktrees}

    mutant_source = SCRIPT.read_text(encoding="utf-8")
    mutant_source = mutant_source.replace("import fcntl\n", "import fcntl\nimport time\n", 1)
    mutant_source = mutant_source.replace(
        "    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)\n",
        "    # mutant: lock removed\n",
        1,
    )
    mutant_source = mutant_source.replace(
        '    if "trustedWorkspaces" not in document:\n',
        """    mutant_barrier = os.environ.get(\"AGY_MUTANT_BARRIER\")
    if mutant_barrier:
        marker = Path(mutant_barrier) / f\"ready-{os.getpid()}\"
        marker.touch()
        deadline = time.monotonic() + 10
        expected = int(os.environ[\"AGY_MUTANT_COUNT\"])
        while len(list(Path(mutant_barrier).glob(\"ready-*\"))) < expected:
            if time.monotonic() >= deadline:
                raise RuntimeError(\"mutant barrier timed out\")
            time.sleep(0.01)

    if \"trustedWorkspaces\" not in document:
""",
        1,
    )
    mutant = tmp_path / "agy-worker-pretrust-mutant"
    mutant.write_text(mutant_source, encoding="utf-8")
    mutant.chmod(0o755)
    barrier = tmp_path / "mutant-barrier"
    barrier.mkdir()
    mutant_env = os.environ.copy()
    mutant_env["AGY_MUTANT_BARRIER"] = str(barrier)
    mutant_env["AGY_MUTANT_COUNT"] = str(count)
    mutant_results = run_many(
        tmp_path / "unlocked-home" / ".gemini", mutant, mutant_env
    )
    assert all(result.returncode == 0 for result in mutant_results)
    mutant_entries = json.loads(
        settings_path(tmp_path / "unlocked-home" / ".gemini").read_text(encoding="utf-8")
    )["trustedWorkspaces"]
    assert len(mutant_entries) < count
