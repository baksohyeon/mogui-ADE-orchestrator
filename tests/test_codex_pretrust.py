from pathlib import Path
import subprocess


SCRIPT = Path(__file__).parents[1] / "scripts" / "codex-worker-pretrust"


def run_pretrust(worktree_path: str, accounts_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), worktree_path, "--accounts-dir", str(accounts_dir)],
        capture_output=True,
        text=True,
        check=False,
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
    assert "Summary: 2 added, 0 already trusted" in result.stdout
    for config in configs:
        assert '[projects."/tmp/orca worker"]\ntrust_level = "trusted"\n' in config.read_text()


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
    assert "Summary: 0 added, 1 already trusted" in second.stdout


def test_absent_accounts_directory_is_informational(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = run_pretrust("/tmp/worktree", missing)

    assert result.returncode == 0
    assert "nothing to pre-trust" in result.stdout
    assert "Summary: 0 added, 0 already trusted" in result.stdout


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
