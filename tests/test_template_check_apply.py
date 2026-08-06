"""template-check and template-apply: report sets, refusals, clean apply."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKELETON = REPO_ROOT / "master-ops"
TEMPLATE_CHECK = SKELETON / "scripts" / "template-check"
TEMPLATE_APPLY = SKELETON / "scripts" / "template-apply"
MANIFEST = SKELETON / "MANIFEST.json"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _seed_ops_from_manifest(ops: Path, *, drop: list[str] | None = None) -> None:
    """Copy a minimal install from the real skeleton using the committed manifest."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    drop_set = set(drop or [])
    for rel in data["files"]:
        if rel in drop_set:
            continue
        src = SKELETON / rel
        if not src.is_file():
            continue
        dest = ops / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    # Always install the manifest itself with the listed version.
    if "MANIFEST.json" not in drop_set:
        shutil.copy2(MANIFEST, ops / "MANIFEST.json")


def test_template_check_install_manifest_set_on_current_shape(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    _seed_ops_from_manifest(ops)
    result = _run(
        [sys.executable, str(TEMPLATE_CHECK), "--ops", str(ops), "--json"],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["report_set"] == "install-manifest"
    assert report["manifest_status"] == "ok"
    assert report["absent_required"] == []
    assert report["installed_version"] == json.loads(MANIFEST.read_text())["template_version"]


def test_template_check_template_compare_states_report_set(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    _seed_ops_from_manifest(ops, drop=["workspace-card/CLAUDE.md"])
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--json",
        ],
    )
    assert result.returncode == 1, result.stdout
    report = json.loads(result.stdout)
    assert report["report_set"] == "template-compare"
    assert "workspace-card/CLAUDE.md" in report["absent_required"]
    assert report["template_version"] == json.loads(MANIFEST.read_text())["template_version"]


def test_template_check_manifest_absent(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "AGENTS.md").write_text("x\n", encoding="utf-8")
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--json",
        ],
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["manifest_status"] == "absent"
    assert report["installed_version"] is None
    assert report["report_set"] == "template-compare"
    assert any("undeterminable" in q for q in report["questions_unanswered"])


def test_template_check_malformed_manifest_exit_2(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "MANIFEST.json").write_text("{not-json", encoding="utf-8")
    result = _run(
        [sys.executable, str(TEMPLATE_CHECK), "--ops", str(ops), "--json"],
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["manifest_status"] == "malformed"


def test_template_apply_refuses_instance_owned_and_unknown(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    # Pre-create instance-owned paths that must never be written.
    (ops / "docs" / "lineage").mkdir(parents=True)
    (ops / "docs" / "lineage" / "MASTER-LINEAGE.md").write_text("mine\n", encoding="utf-8")
    (ops / "docs" / "runbooks").mkdir(parents=True)
    (ops / "docs" / "runbooks" / "role-state.md").write_text("mine\n", encoding="utf-8")
    (ops / "config").mkdir()
    (ops / "config" / "local.json").write_text("{}\n", encoding="utf-8")
    (ops / "contracts").mkdir()
    (ops / "contracts" / "note.md").write_text("mine\n", encoding="utf-8")
    beads = ops / ".beads"
    beads.mkdir()
    (beads / "issues.jsonl").write_text("", encoding="utf-8")

    result = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--attempt",
            "docs/lineage/MASTER-LINEAGE.md",
            "--attempt",
            "docs/runbooks/role-state.md",
            "--attempt",
            "config/local.json",
            "--attempt",
            "contracts/note.md",
            "--attempt",
            ".beads/issues.jsonl",
            "--attempt",
            "not-in-manifest-ever.txt",
            "--json",
        ],
    )
    # Refusal on attempted instance-owned / unknown paths → exit 1
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    actions = {a["path"]: a["action"] for a in payload["actions"]}
    assert actions["docs/lineage/MASTER-LINEAGE.md"] == "skipped-as-instance-owned"
    assert actions["docs/runbooks/role-state.md"] == "skipped-as-instance-owned"
    assert actions["config/local.json"] == "skipped-as-instance-owned"
    assert actions["contracts/note.md"] == "skipped-as-instance-owned"
    assert actions[".beads/issues.jsonl"] == "skipped-as-instance-owned"
    assert actions["not-in-manifest-ever.txt"] == "refused-not-in-manifest"
    # Instance-owned content unchanged.
    assert (ops / "docs" / "lineage" / "MASTER-LINEAGE.md").read_text() == "mine\n"
    assert (ops / "docs" / "runbooks" / "role-state.md").read_text() == "mine\n"


def test_template_apply_clean_write_after_confirm(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    # Start nearly empty so the write pass has work to do. Instance-owned
    # skeleton files are present (as on a real founded install) and must stay
    # byte-identical through apply.
    (ops / "docs" / "lineage").mkdir(parents=True)
    (ops / "docs" / "lineage" / "MASTER-LINEAGE.md").write_text("keep-me\n", encoding="utf-8")
    # Instance-owned lineage dir may carry additional template files (e.g. README);
    # apply refuses the whole prefix, so a founded install must already hold them.
    (ops / "docs" / "lineage" / "README.md").write_text("lineage-readme\n", encoding="utf-8")
    (ops / "docs" / "runbooks").mkdir(parents=True)
    (ops / "docs" / "runbooks" / "role-state.md").write_text("role-keep\n", encoding="utf-8")

    dry = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--json",
        ],
    )
    assert dry.returncode == 0, dry.stderr
    dry_payload = json.loads(dry.stdout)
    assert dry_payload["phase"] == "dry-run"
    planned = [a for a in dry_payload["actions"] if a["action"] == "planned"]
    assert planned, "expected at least one planned template-layer write"

    write = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--write",
            "--confirm-input",
            "apply",
            "--placeholder",
            f"WORKSPACE_ROOT={tmp_path / 'ws'}",
            "--placeholder",
            f"OPS_REPO={ops}",
            "--placeholder",
            "WORKSPACE_NAME=fixture",
            "--placeholder",
            "MONITOR_NS=fixture",
            "--placeholder",
            "MODEL_ID=test-model",
            "--placeholder",
            "REPO_LIST=none",
            "--placeholder",
            f"RUNTIME_ROOT={REPO_ROOT}",
            "--json",
        ],
    )
    assert write.returncode == 0, write.stderr + write.stdout
    payload = json.loads(write.stdout)
    assert payload["phase"] == "write"
    written = [a for a in payload["actions"] if a["action"] == "written"]
    assert written
    assert (ops / "MANIFEST.json").is_file()
    assert (ops / "scripts" / "template-check").is_file()
    # Instance-owned records preserved.
    assert (ops / "docs" / "lineage" / "MASTER-LINEAGE.md").read_text() == "keep-me\n"
    assert (ops / "docs" / "runbooks" / "role-state.md").read_text() == "role-keep\n"

    # Re-check is clean against template for claimed paths that were written.
    check = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--json",
        ],
    )
    report = json.loads(check.stdout)
    assert report["report_set"] == "template-compare"
    assert report["absent_required"] == []
    assert check.returncode == 0


def test_template_apply_declined_confirmation_writes_nothing(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--write",
            "--confirm-input",
            "nope",
        ],
    )
    assert result.returncode == 2
    assert list(ops.iterdir()) == []


def test_template_apply_rejects_path_escape_and_missing_manifest_file(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    (template / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (template / "ok.md").write_text("ok\n", encoding="utf-8")
    # Claim a missing file and a path-escape entry.
    (template / "MANIFEST.json").write_text(
        json.dumps(
            {
                "template_version": "v0.0.0",
                "files": ["ok.md", "missing.md", "../escape.md"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(template),
            "--json",
        ],
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    actions = {a["path"]: a["action"] for a in payload["actions"]}
    assert actions["missing.md"] == "error-missing-template-file"
    assert actions["../escape.md"] == "error-invalid-path"
    assert not (ops / "ok.md").exists()
