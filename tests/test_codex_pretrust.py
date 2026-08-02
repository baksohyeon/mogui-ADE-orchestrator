from pathlib import Path
import subprocess
import tomllib


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
    assert "Summary: 2 added, 0 updated, 0 already trusted" in result.stdout
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


def test_absent_accounts_directory_is_informational(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = run_pretrust("/tmp/worktree", missing)

    assert result.returncode == 0
    assert "nothing to pre-trust" in result.stdout
    assert "Summary: 0 added, 0 updated, 0 already trusted" in result.stdout


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


def test_unverifiable_byte_edit_aborts_without_writing(tmp_path: Path) -> None:
    accounts_dir = tmp_path / "accounts"
    original = b"[ projects . '/tmp/worktree' ]\nsetting = 'keep'\n"
    config = make_config(accounts_dir, "primary", original)

    result = run_pretrust("/tmp/worktree", accounts_dir)

    assert result.returncode == 2
    assert "could not produce exactly one verified pre-trust edit" in result.stderr
    assert config.read_bytes() == original
