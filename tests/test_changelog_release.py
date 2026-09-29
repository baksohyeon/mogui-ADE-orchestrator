"""scripts/changelog-release: fold changelog.d/ fragments into CHANGELOG.md."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "changelog-release"

CHANGELOG_BODY = (
    "# fixture changelog\n\n## Unreleased\n\nOld entry that was already there.\n\n"
    "## v0.1.0\n\nFirst release.\n"
)


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
    )


def _seed(root: Path, fragments: dict[str, str]) -> None:
    master_ops = root / "master-ops"
    changelog_d = master_ops / "changelog.d"
    changelog_d.mkdir(parents=True)
    (master_ops / "CHANGELOG.md").write_text(CHANGELOG_BODY, encoding="utf-8")
    for name, body in fragments.items():
        (changelog_d / name).write_text(body, encoding="utf-8")


def test_fold_order_three_fragments_two_dates(tmp_path: Path):
    _seed(
        tmp_path,
        {
            "2026-01-02-second.md": "Second thing (2026-01-02):\n\n- did second\n",
            "2026-01-01-alpha.md": "Alpha on day one (2026-01-01):\n\n- did alpha\n",
            "2026-01-01-beta.md": "Beta on day one (2026-01-01):\n\n- did beta\n",
        },
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "3 fragments"

    changelog = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    second_at = changelog.find("Second thing")
    alpha_at = changelog.find("Alpha on day one")
    beta_at = changelog.find("Beta on day one")
    old_at = changelog.find("Old entry that was already there.")
    # Newest date first; same-date fragments in name order; old content stays last.
    assert 0 <= second_at < alpha_at < beta_at < old_at

    changelog_d = tmp_path / "master-ops" / "changelog.d"
    assert list(changelog_d.glob("*.md")) == []

    second_result = _run(tmp_path)
    assert second_result.returncode == 0
    assert second_result.stdout.strip() == "0 fragments"


def test_empty_directory_prints_zero_and_touches_nothing(tmp_path: Path):
    _seed(tmp_path, {})
    before = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "0 fragments"
    after = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert before == after


def test_malformed_name_refused(tmp_path: Path):
    _seed(tmp_path, {"NotDated.md": "Some body.\n"})
    before = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "NotDated.md" in result.stderr
    after = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert before == after


def test_empty_fragment_body_refused(tmp_path: Path):
    _seed(tmp_path, {"2026-01-01-empty.md": "   \n"})
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "2026-01-01-empty.md" in result.stderr


def test_dry_run_leaves_tree_unchanged(tmp_path: Path):
    _seed(tmp_path, {"2026-01-01-alpha.md": "Alpha (2026-01-01):\n\n- did alpha\n"})
    before_changelog = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog_d = tmp_path / "master-ops" / "changelog.d"
    before_fragments = sorted(p.name for p in changelog_d.glob("*.md"))

    result = _run(tmp_path, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "## Unreleased" in result.stdout
    assert "Alpha (2026-01-01)" in result.stdout
    assert "Old entry that was already there." in result.stdout
    # The dry-run block stops before the next release heading.
    assert "First release." not in result.stdout

    after_changelog = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    after_fragments = sorted(p.name for p in changelog_d.glob("*.md"))
    assert before_changelog == after_changelog
    assert before_fragments == after_fragments
