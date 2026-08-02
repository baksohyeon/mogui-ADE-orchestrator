"""Tests for scripts/onboarding-preflight.sh.

The script had no test of its own, which is the same defect class it exists to
prevent: a gate whose green light is indistinguishable from silence. These
tests drive it against a stubbed host so each verdict is measured, not assumed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "onboarding-preflight.sh"

ORCA_STUB = """#!/usr/bin/env bash
case "$*" in
  "status --json") printf '%s\\n' '{"ok":true}' ;;
  "orchestration run-current --json") printf '%s\\n' "$STUB_RUN_CURRENT" ;;
  *) printf '%s\\n' '{"ok":false}' ; exit 1 ;;
esac
"""

BD_STUB = """#!/usr/bin/env bash
case "$1" in
  where) printf '%s\\n' "$STUB_OPS_REPO/.beads" ;;
  *) exit 1 ;;
esac
"""

GH_STUB = """#!/usr/bin/env bash
if [[ "$1" == "auth" && "$2" == "status" ]]; then
  printf '%s\\n' "  Logged in to github.com account tester"
  printf '%s\\n' "  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'"
  exit 0
fi
exit 0
"""

TRUE_STUB = "#!/usr/bin/env bash\nexit 0\n"

RUN_BOUND = '{"ok":true,"result":{"run":{"id":"run_test","legacy":0}}}'
RUN_NULL = '{"ok":true,"result":{"run":null}}'
RUN_LEGACY_READ_ONLY = (
    '{"ok":false,"error":{"code":"legacy_read_only",'
    '"message":"retained legacy coordinator","data":{"effectsApplied":false}}}'
)
RUN_BOUND_LEGACY = '{"ok":true,"result":{"run":{"id":"run_old","legacy":1}}}'


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _host(tmp_path: Path, *, rules: str | None = "id|description|abc[0-9]+") -> dict:
    """Provision a stub host and return the env for running the preflight."""

    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    ops_repo = tmp_path / "ops"
    (home / ".claude" / "skills" / "orca-cli").mkdir(parents=True)
    (home / ".claude" / "skills" / "orchestration").mkdir(parents=True)
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        '{"plugins":{"codex@openai-codex":[{"scope":"user"}]}}', encoding="utf-8"
    )
    (home / ".config").mkdir(parents=True)
    if rules is not None:
        (home / ".config" / "redaction-extra.txt").write_text(
            rules + "\n", encoding="utf-8"
        )
    (ops_repo / "docs").mkdir(parents=True)
    (ops_repo / "docs" / "MASTER-OPERATIONS.md").write_text("ops\n", encoding="utf-8")
    (ops_repo / ".beads").mkdir()

    bin_dir.mkdir()
    _write_stub(bin_dir / "orca", ORCA_STUB)
    _write_stub(bin_dir / "bd", BD_STUB)
    _write_stub(bin_dir / "gh", GH_STUB)
    for name in ("codex", "cursor-agent", "claude", "git"):
        _write_stub(bin_dir / name, TRUE_STUB)

    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ORCA_AGENT_CLI": "claude",
            "ORCA_CLI_COMMAND": "",
            "ORCA_DEV_REPO_ROOT": "",
            "STUB_RUN_CURRENT": RUN_BOUND,
            "STUB_OPS_REPO": str(ops_repo),
            "DISPATCH_GATE_LEDGER": str(tmp_path / "ledger" / "dispatch.jsonl"),
            "REDACTION_EXTRA_PATTERNS": str(
                home / ".config" / "redaction-extra.txt"
            ),
        }
    )
    env.pop("ORCA_SKILLS_DIRS", None)
    return env


def _run(env: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(PREFLIGHT)],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


def _labels(output: str, verdict: str) -> set[str]:
    return set(re.findall(rf"^{verdict} +(\S+)", output, re.MULTILINE))


def test_provisioned_host_reports_no_failure_it_can_act_on(tmp_path: Path) -> None:
    """A correctly provisioned host must be able to pass.

    python3 is exempted from the assertion because the interpreter running the
    suite is not under this test's control, and the check compares it against
    the floor README declares.
    """

    result = _run(_host(tmp_path), tmp_path)
    assert _labels(result.stdout, "FAIL") <= {"python3"}, result.stdout
    assert {
        "orchestration",
        "skills",
        "redaction-extra",
        "agent-cli",
        "gate-ledger",
        "bd",
    } <= _labels(result.stdout, "PASS"), result.stdout


def test_skills_pass_without_the_installer_cli(tmp_path: Path) -> None:
    """The artifact is the subject; the installer listing is only a fallback."""

    env = _host(tmp_path)
    result = _run(env, tmp_path)
    assert "skills" in _labels(result.stdout, "PASS"), result.stdout
    assert "skills" not in _labels(result.stdout, "FAIL"), result.stdout


def test_legacy_read_only_coordinator_is_named(tmp_path: Path) -> None:
    env = _host(tmp_path)
    env["STUB_RUN_CURRENT"] = RUN_LEGACY_READ_ONLY
    result = _run(env, tmp_path)
    assert "orchestration" in _labels(result.stdout, "FAIL"), result.stdout
    assert "retained legacy coordinator" in result.stdout
    assert "run-create" in result.stdout


def test_unbound_run_fails_even_though_rpc_answers(tmp_path: Path) -> None:
    env = _host(tmp_path)
    env["STUB_RUN_CURRENT"] = RUN_NULL
    result = _run(env, tmp_path)
    assert "orchestration" in _labels(result.stdout, "FAIL"), result.stdout
    assert "no Run is bound" in result.stdout


def test_bound_legacy_run_fails(tmp_path: Path) -> None:
    env = _host(tmp_path)
    env["STUB_RUN_CURRENT"] = RUN_BOUND_LEGACY
    result = _run(env, tmp_path)
    assert "orchestration" in _labels(result.stdout, "FAIL"), result.stdout
    assert "inspect-only" in result.stdout


def test_missing_agent_cli_selection_fails(tmp_path: Path) -> None:
    env = _host(tmp_path)
    env["ORCA_AGENT_CLI"] = ""
    result = _run(env, tmp_path)
    assert "agent-cli" in _labels(result.stdout, "FAIL"), result.stdout


def test_missing_rules_file_blocks_instead_of_warning(tmp_path: Path) -> None:
    env = _host(tmp_path, rules=None)
    result = _run(env, tmp_path)
    assert "redaction-extra" in _labels(result.stdout, "FAIL"), result.stdout
    assert "redaction-extra" not in _labels(result.stdout, "WARN"), result.stdout
    assert result.returncode == 1


def test_malformed_rule_fails_and_nothing_from_the_file_is_printed(
    tmp_path: Path,
) -> None:
    """Report counts, never content: the file is what the scanner protects."""

    env = _host(
        tmp_path,
        rules="canary|canary description|abc(unclosed\ngood|good description|xyz[0-9]",
    )
    result = _run(env, tmp_path)
    output = result.stdout + result.stderr
    assert "redaction-extra" in _labels(result.stdout, "FAIL"), output
    assert "1 of 2" in output, output
    for leaked in ("canary", "abc(unclosed", "xyz[0-9]"):
        assert leaked not in output, output
