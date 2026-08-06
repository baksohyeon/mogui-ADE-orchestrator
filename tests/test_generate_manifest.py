"""Manifest generator: regenerate is a no-op; frame hygiene fails the build."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "generate-manifest"
MANIFEST = REPO_ROOT / "master-ops" / "MANIFEST.json"
SKELETON = REPO_ROOT / "master-ops"


def test_committed_manifest_matches_regenerate():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_check_accepts_crlf_checkout(tmp_path: Path):
    """Windows checkouts may present MANIFEST.json with CRLF; --check must not flinch."""
    skeleton = tmp_path / "master-ops"
    skeleton.mkdir()
    (skeleton / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (skeleton / "ok.md").write_text("clean\n", encoding="utf-8")
    write = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton)],
        capture_output=True,
        text=True,
    )
    assert write.returncode == 0, write.stderr
    manifest = skeleton / "MANIFEST.json"
    lf = manifest.read_text(encoding="utf-8")
    manifest.write_text(lf.replace("\n", "\r\n"), encoding="utf-8", newline="")
    check = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton), "--check"],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr


def test_manifest_carries_template_version_and_sorted_files():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = (SKELETON / "TEMPLATE-VERSION").read_text(encoding="utf-8").strip()
    assert data["template_version"] == version
    assert data["files"] == sorted(data["files"])
    assert "MANIFEST.json" in data["files"]
    assert "scripts/template-check" in data["files"]
    assert "scripts/template-apply" in data["files"]
    # Excluded template-side paths never install.
    assert "TEMPLATE-VERSION" not in data["files"]
    assert "CHANGELOG.md" not in data["files"]
    assert "ONBOARDING.md" not in data["files"]
    assert not any(p.startswith("onboarding/") for p in data["files"])
    assert not any(p.startswith("docs/lineage/") for p in data["files"])


def test_generator_skips_symlinks_and_refuses_symlink_output(tmp_path: Path):
    skeleton = tmp_path / "master-ops"
    skeleton.mkdir()
    (skeleton / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (skeleton / "real.md").write_text("ok\n", encoding="utf-8")
    for directory in (".git", ".beads", ".pytest_cache", "build", "dist"):
        local_artifact = skeleton / directory
        local_artifact.mkdir()
        (local_artifact / "secret.txt").write_text("local\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (skeleton / "linked.md").symlink_to(outside)

    generated = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert generated.returncode == 0, generated.stderr
    assert "linked.md" not in json.loads(generated.stdout)["files"]
    assert not any(
        path.startswith((".git/", ".beads/", ".pytest_cache/", "build/", "dist/"))
        for path in json.loads(generated.stdout)["files"]
    )

    output = skeleton / "MANIFEST.json"
    output.symlink_to(outside)
    refused = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--skeleton",
            str(skeleton),
            "--out",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 1
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_frame_hygiene_rejects_master_ops_path(tmp_path: Path):
    skeleton = tmp_path / "master-ops"
    skeleton.mkdir()
    (skeleton / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (skeleton / "ok.md").write_text("clean\n", encoding="utf-8")
    (skeleton / "bad.md").write_text("see master-ops/model-tier-policy.json\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "bad.md" in result.stderr
    assert "master-ops/" in result.stderr


def test_frame_hygiene_rejects_authoring_ops_name(tmp_path: Path):
    skeleton = tmp_path / "master-ops"
    skeleton.mkdir()
    (skeleton / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (skeleton / "bad.sh").write_text('OPS="mogui-master-ops"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "mogui-master-ops" in result.stderr


def test_frame_hygiene_exempts_excluded_files(tmp_path: Path):
    skeleton = tmp_path / "master-ops"
    skeleton.mkdir()
    (skeleton / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (skeleton / "CHANGELOG.md").write_text("see master-ops/ONBOARDING.md\n", encoding="utf-8")
    (skeleton / "ONBOARDING.md").write_text("route via mogui-master-ops\n", encoding="utf-8")
    onboarding = skeleton / "onboarding"
    onboarding.mkdir()
    (onboarding / "note.md").write_text("copy from master-ops/\n", encoding="utf-8")
    (skeleton / "ok.md").write_text("clean\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--skeleton", str(skeleton), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["files"] == ["MANIFEST.json", "ok.md"]
