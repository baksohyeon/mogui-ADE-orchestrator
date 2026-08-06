from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "master-ops/scripts/onboarding-rehearsal"


def make_install(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    ops = tmp_path / "ops"
    shutil.copytree(REPO / "master-ops", ops)
    for path in ops.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".txt"}:
            text = path.read_text(encoding="utf-8")
            path.write_text(re.sub(r"\{\{(?!\.\.\.\}\})[^}]+\}\}", "filled", text), encoding="utf-8")
    (workspace / "config").mkdir(parents=True)
    (workspace / "CLAUDE.md").write_bytes((ops / "workspace-card/CLAUDE.md").read_bytes())
    (ops / "CLAUDE.md").write_text("same\n", encoding="utf-8")
    (ops / "AGENTS.md").write_text("same\n", encoding="utf-8")
    (workspace / "config/workspace-descriptor.json").write_text(json.dumps({
        "workspace_root": str(workspace.resolve()),
        "workspace_root_is_plain_folder": True,
        "master_seat": "id:folder:test",
        "repositories": [{"name": "ops", "path": ".", "remote": "", "role": "ops",
                           "capabilities": [], "prohibited": []}],
    }), encoding="utf-8")
    (workspace / "config/instance-runtime.json").write_text(json.dumps({
        "master_host_runtime": "codex",
    }), encoding="utf-8")
    (ops / "docs/runbooks/role-state.md").parent.mkdir(parents=True, exist_ok=True)
    (ops / "docs/runbooks/role-state.md").write_text("role\n", encoding="utf-8")
    (ops / "docs/lineage/MASTER-LINEAGE.md").parent.mkdir(parents=True, exist_ok=True)
    (ops / "docs/lineage/MASTER-LINEAGE.md").write_text("lineage\n", encoding="utf-8")
    return workspace, ops


def run(workspace: Path, ops: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    # Windows cannot execute a shebang script as a native application (WinError
    # 193). GitHub's Windows runner provides bash, so invoke the same script
    # through bash on every OS; bash then invokes the Python interpreter rather
    # than treating this Python source as a shell program.
    # On Windows, Git Bash's Python/WSL shim intercepted every bash -> cmd
    # route even when given the setup-python path (measured in CI stdout).
    # Invoke the concrete setup-python interpreter directly on Windows; Unix
    # keeps the explicit bash path used by the script's executable surface.
    if os.name == "nt":
        command = [sys.executable, str(SCRIPT), "--workspace-root", str(workspace),
                   "--ops-repo", str(ops), *extra]
        return subprocess.run(command, capture_output=True, text=True,
                              env=os.environ.copy())
    else:
        command = [sys.executable, SCRIPT.as_posix(), "--workspace-root", str(workspace),
                   "--ops-repo", str(ops), *extra]
        shell_command = shlex.join(command)
    return subprocess.run(["bash", "-c", shell_command], capture_output=True,
                          text=True, env=os.environ.copy())


def report(completed: subprocess.CompletedProcess[str]) -> dict:
    """Parse JSON only after exposing the real subprocess failure context."""
    assert completed.returncode == 1, (
        f"rehearsal exit={completed.returncode}; stderr:\n{completed.stderr}\n"
        f"stdout:\n{completed.stdout}"
    )
    assert completed.stdout, (
        f"rehearsal produced empty stdout; exit={completed.returncode}; "
        f"stderr:\n{completed.stderr}"
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"rehearsal emitted invalid JSON; exit={completed.returncode}; "
            f"stderr:\n{completed.stderr}\nstdout:\n{completed.stdout}"
        ) from error


def test_rehearsal_reports_passes_and_honest_live_gaps(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    completed = run(workspace, ops, "--json")
    payload = report(completed)
    statuses = {row["id"]: row["status"] for row in payload["results"]}
    assert all(statuses[row] == "PASS" for row in ("P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08"))
    assert statuses["L01"] == "GAP"
    assert statuses["L02"] == "GAP"
    assert {row["id"] for row in payload["gaps"]} == {"L01", "L02"}
    assert payload["failures"] == []


def test_rehearsal_detects_card_drift(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    (workspace / "CLAUDE.md").write_text("drift\n", encoding="utf-8")
    completed = run(workspace, ops, "--json")
    payload = report(completed)
    row = next(row for row in payload["results"] if row["id"] == "P04")
    assert row["status"] == "FAIL"
    assert row["observed"] == "missing or different"


def test_live_check_is_gap_when_orca_is_unavailable(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    completed = run(workspace, ops, "--live", "--orca-cli", "definitely-not-an-orca-cli", "--json")
    payload = report(completed)
    row = next(row for row in payload["results"] if row["id"] == "L01")
    assert row["status"] == "GAP"


def test_rehearsal_excludes_metadata_and_measures_invalid_utf8(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    (ops / ".beads").mkdir()
    (ops / ".beads/issue.md").write_text("{{UNRESOLVED}}", encoding="utf-8")
    (ops / ".git").mkdir()
    (ops / ".git/metadata.md").write_text("{{UNRESOLVED}}", encoding="utf-8")
    (ops / "bad.md").write_bytes(b"\xff\xfe")
    payload = report(run(workspace, ops, "--json"))
    p02 = next(row for row in payload["results"] if row["id"] == "P02")
    assert p02["status"] == "FAIL"
    assert "bad.md (invalid UTF-8)" in p02["observed"]
    assert ".beads" not in p02["observed"]
    assert ".git" not in p02["observed"]


def test_rehearsal_rejects_incomplete_descriptor_and_blank_runtime(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    descriptor = json.loads((workspace / "config/workspace-descriptor.json").read_text())
    descriptor["workspace_root_is_plain_folder"] = False
    (workspace / "config/workspace-descriptor.json").write_text(json.dumps(descriptor))
    (workspace / "config/instance-runtime.json").write_text(json.dumps({"master_host_runtime": "  "}))
    payload = report(run(workspace, ops, "--json"))
    statuses = {row["id"]: row["status"] for row in payload["results"]}
    assert statuses["P05"] == "FAIL"
    assert statuses["P06"] == "FAIL"


def test_rehearsal_rejects_empty_descriptor_fields(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    descriptor = json.loads((workspace / "config/workspace-descriptor.json").read_text())
    descriptor["repositories"] = [{}]
    (workspace / "config/workspace-descriptor.json").write_text(json.dumps(descriptor))
    payload = report(run(workspace, ops, "--json"))
    statuses = {row["id"]: row["status"] for row in payload["results"]}
    assert statuses["P05"] == "FAIL"


def test_rehearsal_accepts_null_capabilities_default(tmp_path: Path):
    workspace, ops = make_install(tmp_path)
    descriptor = json.loads((workspace / "config/workspace-descriptor.json").read_text())
    descriptor["repositories"][0]["capabilities"] = None
    (workspace / "config/workspace-descriptor.json").write_text(json.dumps(descriptor))
    payload = report(run(workspace, ops, "--json"))
    statuses = {row["id"]: row["status"] for row in payload["results"]}
    assert statuses["P05"] == "PASS"
