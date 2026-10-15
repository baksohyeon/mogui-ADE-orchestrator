"""role-state-inject reads an instance-owned Execution rule line, else the default."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "master-ops/scripts/hooks/role-state-inject.sh"


def _inject(tmp_path: Path, role_state: str) -> str:
    rs = tmp_path / "role-state.md"
    rs.write_text(role_state)
    hook = tmp_path / "hook.sh"
    hook.write_text("\n".join(
        f"RS={shlex.quote(str(rs))}" if line.startswith("RS=") else line for line in HOOK.read_text().splitlines()
    ))
    return subprocess.run(["bash", str(hook)], input="{}", capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}).stdout


def test_default_execution_rule(tmp_path: Path):
    out = _inject(tmp_path, "Current Role: Maintenance\nRole Lock: ENABLED\n")
    assert "Execution rule: Proposal -> Approval -> Execution." in out


def test_instance_execution_rule_wins(tmp_path: Path):
    out = _inject(tmp_path, "Current Role: Maintenance\nRole Lock: ENABLED\nExecution rule: Ask first only for deploy.\n")
    assert "Execution rule: Ask first only for deploy." in out
    assert "Proposal -> Approval -> Execution" not in out
