from __future__ import annotations

from windows_exec_surface import skip_windows_exec_surface
import json
import subprocess
from pathlib import Path

import pytest

from master_runtime.core.bootstrap import (
    BootstrapConfig,
    BootstrapError,
    bootstrap,
)


ROLE_STATE_BLOCK = """```
Current Role: Reference Implementation
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```"""


def test_parses_role_state_from_handoff(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n\n- Architecture\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    result = bootstrap(BootstrapConfig(charter_path=charter, handoff_path=handoff))

    assert result.role_state is not None
    assert result.role_state.role == "Reference Implementation"
    assert result.role_state.lock_enabled is True
    assert result.role_state.frozen == "all other roles"
    assert result.role_state.unlock == "explicit user instruction only"
    assert result.l0_text == charter.read_text(encoding="utf-8")
    assert result.l1_text == handoff.read_text(encoding="utf-8")
    assert result.warnings == []


def test_rejects_unknown_role_from_handoff(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n\n- Architecture\n")
    handoff = _file(
        tmp_path,
        "handoff.md",
        """```
Current Role: Wizard
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```""",
    )

    with pytest.raises(BootstrapError, match="Unknown role"):
        bootstrap(BootstrapConfig(charter_path=charter, handoff_path=handoff))


def test_truncates_charter_to_budget_with_marker(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "0123456789" * 10)

    result = bootstrap(BootstrapConfig(charter_path=charter, budget_chars=40))

    assert len(result.l0_text) == 40
    assert result.l0_text.endswith("BOOTSTRAP_BUDGET_EXCEEDED]")
    assert result.l1_text == ""
    assert result.budget_used == 40
    assert "BUDGET_TRUNCATED:L0" in result.warnings


def test_missing_handoff_warns_and_returns_l0_only(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")

    result = bootstrap(
        BootstrapConfig(charter_path=charter, handoff_path=tmp_path / "missing.md")
    )

    assert result.role_state is None
    assert result.l0_text == "# Charter\n"
    assert result.l1_text == ""
    assert result.warnings == ["HANDOFF_MISSING"]


def test_detects_dual_instance_from_injected_ps_output(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    ps_output = """USER         PID  %CPU %MEM      VSZ    RSS   TT  STAT STARTED      TIME COMMAND
devuser    33196   0.0  0.0 410724800   2240 s003  S+    2:01PM   0:00.03 /bin/zsh /private/tmp/claude-501/0464cb11-aaaa-bbbb-cccc-dddddddddddd/scratchpad/drift-monitor.sh
devuser    48015   0.0  0.0 410724800   2240 s004  S+    2:02PM   0:00.01 /bin/zsh -lc printf 0464cb11-aaaa-bbbb-cccc-dddddddddddd
devuser    40309   0.0  0.1 410000000  12000 s001  S+    1:23PM   0:01.23 claude --dangerously-skip-permissions --resume 0464cb11-aaaa-bbbb-cccc-dddddddddddd
"""

    result = bootstrap(
        BootstrapConfig(
            charter_path=charter,
            session_id="0464cb11-aaaa-bbbb-cccc-dddddddddddd",
        ),
        process_probe=lambda: ps_output,
    )

    assert result.warnings == ["DUAL_INSTANCE:40309"]


def test_strict_lease_rejects_dual_instance(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    ps_output = "40309 claude --session-id session-abc\n"

    with pytest.raises(BootstrapError, match="DUAL_INSTANCE:40309"):
        bootstrap(
            BootstrapConfig(
                charter_path=charter,
                session_id="session-abc",
                strict_lease=True,
            ),
            process_probe=lambda: ps_output,
        )


@skip_windows_exec_surface
def test_cli_json_outputs_role_state(tmp_path: Path) -> None:
    charter = _file(tmp_path, "charter.md", "# Charter\n")
    handoff = _file(tmp_path, "handoff.md", "## Role State\n\n" + ROLE_STATE_BLOCK + "\n")

    result = subprocess.run(
        [
            str(_script()),
            "--charter",
            str(charter),
            "--handoff",
            str(handoff),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["role_state"]["role"] == "Reference Implementation"
    assert payload["warnings"] == []


def _file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _script() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "master-bootstrap"
