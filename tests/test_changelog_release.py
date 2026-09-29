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
    before = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "2026-01-01-empty.md" in result.stderr
    after = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert before == after


def test_impossible_date_refused(tmp_path: Path):
    _seed(tmp_path, {"2026-02-30-alpha.md": "Alpha (2026-02-30):\n\n- did alpha\n"})
    before = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "2026-02-30-alpha.md" in result.stderr
    after = (tmp_path / "master-ops" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert before == after


def test_missing_changelog_reports_clean_error(tmp_path: Path):
    _seed(tmp_path, {"2026-01-01-alpha.md": "Alpha (2026-01-01):\n\n- did alpha\n"})
    (tmp_path / "master-ops" / "CHANGELOG.md").unlink()
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "changelog-release" in result.stderr
    assert "CHANGELOG.md" in result.stderr


def test_dry_run_preview_not_truncated_by_fenced_heading(tmp_path: Path):
    _seed(
        tmp_path,
        {
            "2026-01-01-alpha.md": (
                "Alpha (2026-01-01):\n\n```\n## not a real heading\n```\n\n- did alpha\n"
            )
        },
    )
    result = _run(tmp_path, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "Alpha (2026-01-01)" in result.stdout
    assert "not a real heading" in result.stdout
    assert "Old entry that was already there." in result.stdout
    assert "First release." not in result.stdout


def test_rerun_after_failed_deletion_reports_already_folded(tmp_path: Path):
    # Simulate the state left by an interrupted first run: the changelog was
    # written but this fragment's deletion failed, so it is still on disk
    # with a body that already appears under Unreleased.
    body = "Alpha (2026-01-01):\n\n- did alpha\n"
    changelog_body = (
        "# fixture changelog\n\n## Unreleased\n\n"
        f"{body}\nOld entry that was already there.\n\n## v0.1.0\n\nFirst release.\n"
    )
    master_ops = tmp_path / "master-ops"
    changelog_d = master_ops / "changelog.d"
    changelog_d.mkdir(parents=True)
    (master_ops / "CHANGELOG.md").write_text(changelog_body, encoding="utf-8")
    (changelog_d / "2026-01-01-alpha.md").write_text(body, encoding="utf-8")

    before = (master_ops / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "2026-01-01-alpha.md: already folded" in result.stdout
    after = (master_ops / "CHANGELOG.md").read_text(encoding="utf-8")
    assert before == after
    assert list(changelog_d.glob("*.md")) == []


def test_rerun_does_not_drop_new_fragment_overlapping_existing_text(tmp_path: Path):
    # A new, distinct fragment whose body is a substring of unrelated existing
    # Unreleased text must still fold: containment alone is not "already
    # folded", only a whole matching paragraph block is.
    changelog_body = (
        "# fixture changelog\n\n## Unreleased\n\n"
        "This entry mentions did alpha in passing.\n\n"
        "Old entry that was already there.\n\n## v0.1.0\n\nFirst release.\n"
    )
    master_ops = tmp_path / "master-ops"
    changelog_d = master_ops / "changelog.d"
    changelog_d.mkdir(parents=True)
    (master_ops / "CHANGELOG.md").write_text(changelog_body, encoding="utf-8")
    (changelog_d / "2026-01-01-alpha.md").write_text("did alpha\n", encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "already folded" not in result.stdout
    assert "1 fragments" in result.stdout

    after = (master_ops / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "did alpha" in after
    assert "This entry mentions did alpha in passing." in after
    assert list(changelog_d.glob("*.md")) == []


def test_rerun_mixed_new_and_already_folded_fragments(tmp_path: Path):
    already_body = "Alpha (2026-01-01):\n\n- did alpha\n"
    new_body = "Beta (2026-01-02):\n\n- did beta\n"
    changelog_body = (
        "# fixture changelog\n\n## Unreleased\n\n"
        f"{already_body}\nOld entry that was already there.\n\n## v0.1.0\n\nFirst release.\n"
    )
    master_ops = tmp_path / "master-ops"
    changelog_d = master_ops / "changelog.d"
    changelog_d.mkdir(parents=True)
    (master_ops / "CHANGELOG.md").write_text(changelog_body, encoding="utf-8")
    (changelog_d / "2026-01-01-alpha.md").write_text(already_body, encoding="utf-8")
    (changelog_d / "2026-01-02-beta.md").write_text(new_body, encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "2026-01-01-alpha.md: already folded" in result.stdout
    assert "1 fragments" in result.stdout

    after = (master_ops / "CHANGELOG.md").read_text(encoding="utf-8")
    assert after.count("Alpha (2026-01-01)") == 1
    assert "Beta (2026-01-02)" in after
    assert list(changelog_d.glob("*.md")) == []


def test_fragment_name_grammar_matches_template_common():
    """FRAGMENT_RE here and in changelog-fragment-check must stay identical
    to master-ops/scripts/template_common.py's canonical FRAGMENT_NAME_RE:
    a fragment name the release script folds must be one the gate accepts
    and template-check previews."""
    import importlib.util
    import sys as _sys
    from importlib.machinery import SourceFileLoader

    def _load(name: str, path: Path):
        loader = SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(name, loader)
        module = importlib.util.module_from_spec(spec)
        _sys.modules[name] = module
        loader.exec_module(module)
        return module

    release = _load("_changelog_release_grammar_check", SCRIPT)
    fragment_check = _load(
        "_changelog_fragment_check_grammar_check",
        REPO_ROOT / "scripts" / "changelog-fragment-check",
    )
    template_common = _load(
        "_template_common_grammar_check",
        REPO_ROOT / "master-ops" / "scripts" / "template_common.py",
    )

    assert release.FRAGMENT_RE.pattern == template_common.FRAGMENT_NAME_RE.pattern
    assert fragment_check.FRAGMENT_RE.pattern == template_common.FRAGMENT_NAME_RE.pattern


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
