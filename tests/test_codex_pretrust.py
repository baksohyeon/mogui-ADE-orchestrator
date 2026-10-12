import os
from pathlib import Path
import subprocess
import tomllib


from windows_exec_surface import skip_windows_exec_surface
pytestmark = skip_windows_exec_surface

SCRIPT = Path(__file__).parents[1] / "scripts" / "codex-worker-pretrust"


def run_pretrust(
    worktree_path: str,
    accounts_dir: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy() if env is None else env.copy()
    if env is None or "CODEX_HOME" not in env:
        child_env["CODEX_HOME"] = str(accounts_dir.parent / "absent-codex-home")
    return subprocess.run(
        [str(SCRIPT), worktree_path, "--accounts-dir", str(accounts_dir)],
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )


def make_config(accounts_dir: Path, account: str, content: bytes = b"") -> Path:
    config = accounts_dir / account / "home" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_bytes(content)
    return config


def test_fresh_add_trusts_every_account(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    configs = [
        make_config(accounts_dir, "first", b'model = "gpt"\n'),
        make_config(accounts_dir, "second"),
    ]

    result = run_pretrust("/tmp/orca worker", accounts_dir)

    assert result.returncode == 0
    assert result.stdout.count("trusted (added)") == 2
    assert "Summary: 2 added, 0 updated, 0 already trusted" in result.stdout
    for config in configs:
        assert '[projects."/tmp/orca worker"]\ntrust_level = "trusted"\n' in config.read_text()


def test_regular_case_ignores_developer_codex_home(
    tmp_path: Path, monkeypatch
) -> None:
    accounts_dir = tmp_path / "accounts"
    account_config = make_config(accounts_dir, "primary", b'model = "account"\n')
    developer_codex_home = tmp_path / "developer-codex-home"
    developer_codex_home.mkdir()
    host_config = developer_codex_home / "config.toml"
    host_original = b'model = "developer"\n'
    host_config.write_bytes(host_original)
    monkeypatch.setenv("CODEX_HOME", str(developer_codex_home))

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 0
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert tomllib.loads(account_config.read_text(encoding="utf-8"))["projects"][
        "/tmp/worktree"
    ]["trust_level"] == "trusted"
    assert host_config.read_bytes() == host_original


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    config = make_config(accounts_dir, "primary", b'model = "gpt"\n')

    first = run_pretrust("/tmp/worktree", accounts_dir)
    after_first = config.read_bytes()
    second = run_pretrust("/tmp/worktree", accounts_dir)

    assert first.returncode == 0
    assert second.returncode == 0
    assert config.read_bytes() == after_first
    assert "already trusted" in second.stdout
    assert "Summary: 0 added, 0 updated, 1 already trusted" in second.stdout


def test_existing_project_without_trust_level_is_updated_in_place(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = (
        b'model = "gpt"\n'
        b'[projects."/tmp/worktree"]\n'
        b'model_reasoning_effort = "high"\n'
        b'[projects."/tmp/other"]\n'
        b'trust_level = "trusted"\n'
    )
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 0
    assert result.stdout.count("trusted (updated)") == 1
    assert "Summary: 0 added, 1 updated, 0 already trusted" in result.stdout
    assert config.read_bytes() == original.replace(
        b'[projects."/tmp/worktree"]\n',
        b'[projects."/tmp/worktree"]\ntrust_level = "trusted"\n',
        1,
    )


def test_existing_untrusted_project_is_updated_without_touching_other_lines(
    tmp_path: Path,
) -> None:
    accounts_dir = tmp_path / "accounts"
    original = (
        b'# preserve before\n'
        b'[projects."/tmp/worktree"]\n'
        b'feature = "preserve in table"\n'
        b'  trust_level = "untrusted"\n'
        b'[notice]\n'
        b'value = "preserve after"'
    )
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 0
    assert "trusted (updated)" in result.stdout
    assert "Summary: 0 added, 1 updated, 0 already trusted" in result.stdout
    assert config.read_bytes() == original.replace(
        b'  trust_level = "untrusted"\n',
        b'  trust_level = "trusted"\n',
        1,
    )


def test_host_config_is_trusted_when_accounts_directory_is_absent(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config = codex_home / "config.toml"
    config.write_text('model = "gpt"\n', encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    result = run_pretrust("/tmp/worktree", missing, env=env)

    assert result.returncode == 0
    assert "accounts directory not found" in result.stdout
    assert "trusted (added)" in result.stdout
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    assert tomllib.loads(config.read_text(encoding="utf-8"))["projects"][
        "/tmp/worktree"
    ]["trust_level"] == "trusted"


def test_host_config_second_run_is_idempotent_without_accounts(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config = codex_home / "config.toml"
    config.write_text('model = "gpt"\n', encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    first = run_pretrust("/tmp/worktree", missing, env=env)
    after_first = config.read_bytes()
    second = run_pretrust("/tmp/worktree", missing, env=env)

    assert first.returncode == 0
    assert second.returncode == 0
    assert config.read_bytes() == after_first
    assert "already trusted" in second.stdout
    assert "Summary: 0 added, 0 updated, 1 already trusted" in second.stdout


def test_account_and_host_configs_are_both_trusted(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    account_config = make_config(accounts_dir, "primary", b'model = "account"\n')
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    host_config = codex_home / "config.toml"
    host_config.write_text('model = "host"\n', encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    result = run_pretrust("/tmp/worktree", accounts_dir, env=env)

    assert result.returncode == 0
    assert result.stdout.count("trusted (added)") == 2
    assert "Summary: 2 added, 0 updated, 0 already trusted" in result.stdout
    for config in (account_config, host_config):
        assert tomllib.loads(config.read_text(encoding="utf-8"))["projects"][
            "/tmp/worktree"
        ]["trust_level"] == "trusted"


def test_absent_accounts_and_host_config_are_informational_without_creation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config = codex_home / "config.toml"
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    result = run_pretrust("/tmp/worktree", missing, env=env)

    assert result.returncode == 0
    assert "nothing to pre-trust" in result.stdout
    assert "host config not found" in result.stdout
    assert "Summary: 0 added, 0 updated, 0 already trusted" in result.stdout
    assert not config.exists()


def test_accounts_only_without_home_or_codex_home_is_informational(
    tmp_path: Path, monkeypatch
) -> None:
    accounts_dir = tmp_path / "accounts"
    config = make_config(accounts_dir, "primary", b'model = "account"\n')
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 3
    assert "INFO Codex host config not found" in result.stdout
    assert "/.codex/config.toml" not in result.stdout
    assert "trusted (added)" in result.stdout
    assert tomllib.loads(config.read_text(encoding="utf-8"))["projects"][
        "/tmp/worktree"
    ]["trust_level"] == "trusted"


def test_relative_worktree_path_is_rejected(tmp_path: Path) -> None:
    result = run_pretrust("relative/worktree", tmp_path / "accounts")

    assert result.returncode != 0
    assert "worktree path must be absolute" in result.stderr


def test_unrelated_content_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = b'# keep this exactly\nmodel = "gpt-5"\nsetting = [1, 2, 3]'
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust('/tmp/quoted "worker"', accounts_dir)

    assert result.returncode == 0
    assert config.read_bytes() == (
        original
        + b'\n[projects."/tmp/quoted \\"worker\\""]\n'
        + b'trust_level = "trusted"\n'
    )


def test_multiline_strings_with_table_like_lines_are_not_edited(
    tmp_path: Path,
) -> None:
    accounts_dir = tmp_path / "accounts"
    basic_original = (
        b'banner = """\n'
        b'[projects."/tmp/worktree"]\n'
        b'trust_level = "untrusted"\n'
        b'"""\n'
        b'[projects."/tmp/worktree"]\n'
        b'note = """\n'
        b'[not.a.real.table]\n'
        b'keep this basic string intact\n'
        b'"""\n'
        b'trust_level = "untrusted"\n'
    )
    literal_original = (
        b"banner = '''\n"
        b'[projects."/tmp/worktree"]\n'
        b'trust_level = "untrusted"\n'
        b"'''\n"
        b'[projects."/tmp/worktree"]\n'
        b"note = '''\n"
        b"[not.a.real.table]\n"
        b"keep this literal string intact\n"
        b"'''\n"
        b'trust_level = "untrusted"\n'
    )
    configs = (
        (make_config(accounts_dir, "basic", basic_original), basic_original),
        (make_config(accounts_dir, "literal", literal_original), literal_original),
    )

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 0
    assert "Summary: 0 added, 2 updated, 0 already trusted" in result.stdout
    for config, original in configs:
        updated = config.read_bytes()
        assert updated == original.rsplit(
            b'trust_level = "untrusted"', 1
        )[0] + b'trust_level = "trusted"\n'
        parsed = tomllib.loads(updated.decode("utf-8"))
        assert parsed["projects"]["/tmp/worktree"]["trust_level"] == "trusted"
        assert parsed["banner"] == tomllib.loads(original.decode("utf-8"))["banner"]
        assert parsed["projects"]["/tmp/worktree"]["note"] == (
            tomllib.loads(original.decode("utf-8"))["projects"]["/tmp/worktree"][
                "note"
            ]
        )


def test_unparseable_config_aborts_without_writing(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = b'model = "unterminated\n'
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 2
    assert f"ERROR {config}: cannot parse TOML" in result.stderr
    assert config.read_bytes() == original


def test_no_tomllib_interpreter_skips_without_writing(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = b'model = "gpt"\n'
    config = make_config(accounts_dir, "primary", original)
    import_shim = tmp_path / "import-shim"
    import_shim.mkdir()
    (import_shim / "tomllib.py").write_text(
        'raise ImportError("tomllib unavailable for regression test")\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(import_shim)

    result = run_pretrust("/tmp/worktree", accounts_dir, env=env)

    assert result.returncode == 0
    assert "SKIP no Python with tomllib found" in result.stdout
    assert "SKIP no Python with tomllib found" in result.stderr
    assert "trust prompt" in result.stderr
    assert "Summary: skipped — 0 added, 0 updated, 0 already trusted" in result.stdout
    assert config.read_bytes() == original


def test_resolver_skips_disqualified_candidate_and_first_qualifier_wins(
    tmp_path: Path,
) -> None:
    import sys

    accounts_dir = tmp_path / "accounts"
    config = make_config(accounts_dir, "primary", b'model = "gpt"\n')

    # A PATH where python3 exists but cannot import tomllib, python3.14/13 do
    # not exist, and python3.12 is the first qualifier. Each shim records being
    # probed, which is what pins the candidate order: reordering the loop so a
    # later name wins leaves the python3 marker unwritten and fails below.
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    probe_log = tmp_path / "probes.log"
    for disqualified in ("python3", "python3.14", "python3.13"):
        failing = shim_bin / disqualified
        failing.write_text(
            f'#!/bin/sh\necho {disqualified} >> "{probe_log}"\nexit 1\n',
            encoding="utf-8",
        )
        failing.chmod(0o755)
    qualifying = shim_bin / "python3.12"
    qualifying.write_text(
        f'#!/bin/sh\necho python3.12 >> "{probe_log}"\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    qualifying.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{shim_bin}:/usr/bin:/bin"

    result = run_pretrust("/tmp/worktree", accounts_dir, env=env)

    assert result.returncode == 0, result.stderr
    assert "trusted (added)" in result.stdout
    assert "Summary: 1 added, 0 updated, 0 already trusted" in result.stdout
    probes = probe_log.read_text(encoding="utf-8").split()
    # The qualifier is probed once and then runs again for the edit, so the
    # first four entries pin the exact candidate order.
    assert probes[:4] == ["python3", "python3.14", "python3.13", "python3.12"], probes
    parsed = tomllib.loads(config.read_bytes().decode("utf-8"))
    assert parsed["projects"]["/tmp/worktree"]["trust_level"] == "trusted"


def test_unverifiable_byte_edit_aborts_without_writing(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = b"[ projects . '/tmp/worktree' ]\nsetting = 'keep'\n"
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 2
    assert "could not produce exactly one verified pre-trust edit" in result.stderr
    assert config.read_bytes() == original
