"""A founding fill replaces every documented placeholder across the ops tree.

Sentinel checks that compare against a literal placeholder must survive that
fill; otherwise the comparison inverts (product-path-guard then blocks every
call because the real runtime root now matches its own "unsubstituted" test).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_OPS = REPO_ROOT / "master-ops"
sys.path.insert(0, str(MASTER_OPS / "scripts"))
from template_common import PLACEHOLDERS  # noqa: E402

TOKEN = re.compile(r"\{\{[^}]+\}\}")


def _filled_ops(tmp_path: Path) -> tuple[Path, Path]:
    ops = tmp_path / "ops"
    runtime = tmp_path / "runtime"
    (runtime / "config").mkdir(parents=True)
    (runtime / "config" / "instance-runtime.json").write_text(
        json.dumps({"master_host_runtime": "claude", "product_repositories": [str(tmp_path / "product")]})
    )
    values = {
        "WORKSPACE_NAME": "fixture",
        "WORKSPACE_ROOT": str(tmp_path),
        "OPS_REPO": str(ops),
        "MONITOR_NS": "fixture",
        "MODEL_ID": "fixture-model",
        "REPO_LIST": "product",
        "RUNTIME_ROOT": str(runtime),
        "TEMPLATE_VERSION": "v0.0.0",
    }
    for rel in json.loads((MASTER_OPS / "MANIFEST.json").read_text())["files"]:
        dest = ops / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MASTER_OPS / rel, dest)
        try:
            text = dest.read_text()
        except UnicodeDecodeError:
            continue
        for key in PLACEHOLDERS:
            text = text.replace(key, values[key[2:-2]])
        dest.write_text(text)
    return ops, runtime


def test_fill_leaves_no_placeholder_tokens(tmp_path: Path):
    ops, _ = _filled_ops(tmp_path)
    leftovers = [
        f"{p.relative_to(ops)}: {m}"
        for p in ops.rglob("*")
        if p.is_file()
        for m in TOKEN.findall(p.read_text(errors="ignore"))
    ]
    assert leftovers == []


def test_filled_product_path_guard_passes_benign_call(tmp_path: Path):
    ops, _ = _filled_ops(tmp_path)
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "elsewhere.txt")}})
    result = subprocess.run(
        ["bash", str(ops / "scripts/hooks/product-path-guard.sh")],
        input=payload, capture_output=True, text=True, cwd=tmp_path,
        env={**{k: v for k, v in os.environ.items() if k != "MOGUI_INSTANCE_RUNTIME_CONFIG"},
             "MOGUI_EVENT_LOG": str(tmp_path / "event-log.jsonl"),
             "MOGUI_HOOK_FIRE_LOG": str(tmp_path / "hook-fire-log.jsonl")},
    )
    assert result.returncode == 0, result.stderr
