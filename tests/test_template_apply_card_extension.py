"""The workspace card's local extension seat: instance-owned, never written by template-apply."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKELETON = REPO_ROOT / "master-ops"
TEMPLATE_APPLY = SKELETON / "scripts" / "template-apply"
TEMPLATE_CHECK = SKELETON / "scripts" / "template-check"
MANIFEST = SKELETON / "MANIFEST.json"
EXTENSION = "workspace-card/LOCAL.md"

sys.path.insert(0, str(SKELETON / "scripts"))
from template_common import is_instance_owned  # noqa: E402


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _full_placeholders(ops: Path) -> list[str]:
    pairs = {
        "WORKSPACE_NAME": "fixture",
        "WORKSPACE_ROOT": "/tmp/ws",
        "OPS_REPO": str(ops),
        "MONITOR_NS": "fixture",
        "MODEL_ID": "test-model",
        "REPO_LIST": "none",
        "RUNTIME_ROOT": str(REPO_ROOT),
    }
    args: list[str] = []
    for key, value in pairs.items():
        args.extend(["--placeholder", f"{key}={value}"])
    return args


def _seed_extension(ops: Path) -> Path:
    dest = ops / EXTENSION
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("mine\n", encoding="utf-8")
    return dest


def test_card_pair_names_the_extension_path_and_it_is_instance_owned():
    for name in ("CLAUDE.md", "AGENTS.md"):
        card = (SKELETON / "workspace-card" / name).read_text(encoding="utf-8")
        assert "{{OPS_REPO}}/" + EXTENSION in card, name
    assert is_instance_owned(EXTENSION)
    assert EXTENSION not in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    assert not (SKELETON / EXTENSION).exists(), "the template ships no extension file"


def test_template_apply_refuses_the_extension_by_name(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    extension = _seed_extension(ops)
    result = _run(
        [
            sys.executable,
            str(TEMPLATE_APPLY),
            "--ops",
            str(ops),
            "--template",
            str(SKELETON),
            "--attempt",
            EXTENSION,
            "--json",
        ]
    )
    assert result.returncode == 1, result.stdout + result.stderr
    actions = {a["path"]: a["action"] for a in json.loads(result.stdout)["actions"]}
    assert actions[EXTENSION] == "skipped-as-instance-owned"
    assert extension.read_text(encoding="utf-8") == "mine\n"


def test_template_check_does_not_list_the_extension_as_unknown(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    _seed_extension(ops)
    result = _run(
        [sys.executable, str(TEMPLATE_CHECK), "--ops", str(ops), "--template", str(SKELETON), "--json"]
    )
    assert result.returncode in (0, 1), result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert EXTENSION not in report.get("unknown_present", [])
