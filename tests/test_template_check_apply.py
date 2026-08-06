"""template-check and template-apply: report sets, refusals, clean apply."""

from __future__ import annotations

import json
import importlib.util
import importlib.machinery
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


def test_template_check_unreadable_template_version_exit_2(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": []}) + "\n",
        encoding="utf-8",
    )
    template = tmp_path / "template"
    template.mkdir()
    (template / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": []}) + "\n",
        encoding="utf-8",
    )
    # Invalid UTF-8 in TEMPLATE-VERSION must fail closed (exit 2), not look clean.
    (template / "TEMPLATE-VERSION").write_bytes(b"\xff\xfe not-utf8")
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(template),
            "--json",
        ],
    )
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert any("VERSION" in q for q in report["questions_unanswered"])


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


def test_template_check_empty_manifest_still_reports_unknown_paths(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": []}) + "\n",
        encoding="utf-8",
    )
    (ops / "unexpected.txt").write_text("x\n", encoding="utf-8")
    result = _run([sys.executable, str(TEMPLATE_CHECK), "--ops", str(ops), "--json"])
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["unknown_present"] == ["unexpected.txt"]


def test_template_check_rejects_symlink_and_bad_changelog(tmp_path: Path):
    ops = tmp_path / "ops"
    template = tmp_path / "template"
    ops.mkdir()
    template.mkdir()
    (ops / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": ["required.md"]}) + "\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (ops / "required.md").symlink_to(outside)
    (template / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (template / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": ["required.md"]}) + "\n",
        encoding="utf-8",
    )
    (template / "CHANGELOG.md").write_bytes(b"\xff")
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(template),
            "--json",
        ]
    )
    report = json.loads(result.stdout)
    assert result.returncode == 2
    assert report["invalid_paths"] == ["required.md"]
    assert any("CHANGELOG" in item for item in report["questions_unanswered"])


def test_template_check_compares_version_without_template_manifest(tmp_path: Path):
    ops = tmp_path / "ops"
    template = tmp_path / "template"
    ops.mkdir()
    template.mkdir()
    (ops / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": []}) + "\n",
        encoding="utf-8",
    )
    (template / "TEMPLATE-VERSION").write_text("v1.0.0\n", encoding="utf-8")
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_CHECK),
            "--ops",
            str(ops),
            "--template",
            str(template),
            "--json",
        ]
    )
    assert result.returncode == 1


def test_template_apply_rejects_overlap_and_invalid_destinations(tmp_path: Path):
    template = tmp_path / "template"
    ops = tmp_path / "ops"
    template.mkdir()
    ops.mkdir()
    (template / "TEMPLATE-VERSION").write_text("v0.0.0\n", encoding="utf-8")
    (template / "file.txt").write_text("new\n", encoding="utf-8")
    (template / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": ["file.txt", "dir"]}) + "\n",
        encoding="utf-8",
    )
    (ops / "dir").mkdir()
    external = tmp_path / "external.txt"
    external.write_text("keep\n", encoding="utf-8")
    (ops / "file.txt").symlink_to(external)

    result = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(template),
            "--json",
        ]
    )
    assert result.returncode == 1
    actions = {item["path"]: item["action"] for item in json.loads(result.stdout)["actions"]}
    assert actions["file.txt"] == "error-invalid-path"
    assert actions["dir"] == "error-invalid-path"
    assert external.read_text(encoding="utf-8") == "keep\n"

    overlap = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(template),
            "--template",
            str(template),
        ]
    )
    assert overlap.returncode == 2


def test_template_apply_preflight_rechecks_destination_after_plan(tmp_path: Path):
    loader = importlib.machinery.SourceFileLoader("template_apply_under_test", str(TEMPLATE_APPLY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    template = tmp_path / "template"
    ops = tmp_path / "ops"
    template.mkdir()
    ops.mkdir()
    (template / "file.txt").write_text("new\n", encoding="utf-8")
    manifest = {"template_version": "v0.0.0", "files": ["file.txt"]}
    actions = module.plan_actions(template, ops, manifest, None)
    external = tmp_path / "external.txt"
    external.write_text("keep\n", encoding="utf-8")
    (ops / "file.txt").symlink_to(external)

    with pytest.raises(RuntimeError, match="preflight failed"):
        module.apply_planned(template, ops, actions, {})
    assert external.read_text(encoding="utf-8") == "keep\n"


def test_template_apply_invalid_template_version_is_controlled_error(tmp_path: Path):
    template = tmp_path / "template"
    ops = tmp_path / "ops"
    template.mkdir()
    ops.mkdir()
    (template / "TEMPLATE-VERSION").write_bytes(b"\xff")
    (template / "MANIFEST.json").write_text(
        json.dumps({"template_version": "v0.0.0", "files": []}) + "\n",
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
        ]
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_frame_hygiene_guards_use_explicit_template_and_shared_skeleton_name():
    harness = (SKELETON / "scripts" / "harness-selfcheck.sh").read_text(encoding="utf-8")
    spawn = (SKELETON / "scripts" / "spawn-test").read_text(encoding="utf-8")
    assert "OPS_DIR/../mogui-ADE-orchestrator" not in harness
    assert "Fallback text match" not in harness
    assert "while IFS= read -r tracker_line" in harness
    assert 'if [ ! -d "$tracker_candidate" ]' in harness
    assert '*:[[:space:]]*) tracker_candidate="${tracker_candidate#*:}"' in harness
    assert "basename" not in harness[harness.index("# --- Tracker check ---") : harness.index("# --- Template currency check ---")]
    assert 'SKELETON_DIR="master"$\'-\'"ops"' in spawn
    assert 'local ade_clone_path="$sandbox_dir/$ADE_REPO_NAME"' in spawn


def test_onboarding_docs_name_template_root_and_placeholder_flags():
    upgrade = (SKELETON / "onboarding" / "upgrade.md").read_text(encoding="utf-8")
    reverify = (SKELETON / "onboarding" / "reverify.md").read_text(encoding="utf-8")
    assert "--placeholder WORKSPACE_NAME" in upgrade
    assert "ops-side" in upgrade
    assert '"{{RUNTIME_ROOT}}/master-ops/scripts/template-check"' in reverify
    assert "do not guess a sibling directory" in reverify
    assert "The ops-side" in upgrade and "{{REPO_LIST}}" in upgrade
