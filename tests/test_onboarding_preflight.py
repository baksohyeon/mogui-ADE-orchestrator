"""Tests for scripts/onboarding-preflight.sh.

The script had no test of its own, which is the same defect class it exists to
prevent: a gate whose green light is indistinguishable from silence. These
tests drive it against a stubbed host so each verdict is measured, not assumed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
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


def _host(
    tmp_path: Path,
    *,
    rules: str | None = "id|description|abc[0-9]+",
    worker_runtimes: tuple[str, ...] = ("codex", "cursor-agent"),
    sanitized_path: bool = False,
) -> dict:
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
    for name in ("claude", "git", "gitleaks", "ctx", *worker_runtimes):
        _write_stub(bin_dir / name, TRUE_STUB)

    env = dict(os.environ)
    # Sanitized PATH keeps a runtime absent even when the developer's machine has
    # it installed; the system directories stay because the script uses sed,
    # grep, dirname, realpath, and python3.
    path = (
        f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin"
        if sanitized_path
        else f"{bin_dir}:{env['PATH']}"
    )
    env.update(
        {
            "HOME": str(home),
            "PATH": path,
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

    python3 no longer needs an exemption here: presence is the whole check, and
    version floors belong to the tools that have them, stated at their runtime.
    """

    result = _run(_host(tmp_path), tmp_path)
    assert not _labels(result.stdout, "FAIL"), result.stdout
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


def test_waived_failure_is_labeled_and_stops_blocking(tmp_path: Path) -> None:
    """The escape exists so the whole preflight is not skipped, and it is loud."""

    env = _host(tmp_path, rules=None)
    env["PREFLIGHT_WAIVE"] = "redaction-extra"
    result = _run(env, tmp_path)
    assert "redaction-extra" not in _labels(result.stdout, "FAIL"), result.stdout
    assert "WAIVED" in result.stdout
    assert "downgraded from FAIL by PREFLIGHT_WAIVE" in result.stdout
    assert "READY WITH WAIVERS" in result.stdout
    assert "downgraded, not satisfied" in result.stdout
    assert result.returncode == 0, result.stdout


def test_waiver_that_matched_nothing_keeps_the_check_enforced(tmp_path: Path) -> None:
    """A typo'd waiver must not read as a waiver."""

    env = _host(tmp_path, rules=None)
    env["PREFLIGHT_WAIVE"] = "redaction-extras"
    result = _run(env, tmp_path)
    assert "redaction-extra" in _labels(result.stdout, "FAIL"), result.stdout
    assert "named checks that did not run: redaction-extras" in result.stdout
    assert "still enforced" in result.stdout
    assert result.returncode == 1


def test_one_missing_worker_runtime_warns_when_another_is_present(
    tmp_path: Path,
) -> None:
    env = _host(tmp_path, worker_runtimes=("codex",), sanitized_path=True)
    result = _run(env, tmp_path)
    assert "worker-runtime" in _labels(result.stdout, "WARN"), result.stdout
    assert "worker-runtime" not in _labels(result.stdout, "FAIL"), result.stdout


def test_no_worker_runtime_at_all_fails(tmp_path: Path) -> None:
    env = _host(tmp_path, worker_runtimes=(), sanitized_path=True)
    result = _run(env, tmp_path)
    assert "worker-runtime" in _labels(result.stdout, "FAIL"), result.stdout
    assert "cannot delegate" in result.stdout


def test_missing_gitleaks_warns_without_blocking(tmp_path: Path) -> None:
    """Publishing needs gitleaks; running a master does not, so its absence warns.

    The essential block still repeats the consequence, because a warning that only
    scrolls past is how this requirement got overstated in the first place.
    """

    env = _host(tmp_path, sanitized_path=True)
    (tmp_path / "bin" / "gitleaks").unlink()
    result = _run(env, tmp_path)
    assert "gitleaks" in _labels(result.stdout, "WARN"), result.stdout
    assert "gitleaks" not in _labels(result.stdout, "FAIL"), result.stdout
    assert "brew install gitleaks" in result.stdout
    assert "ESSENTIAL COMPONENTS MISSING" in result.stdout


def test_missing_ctx_warns_without_blocking(tmp_path: Path) -> None:
    """Agent history is what the records practice queries; a master runs without it."""

    env = _host(tmp_path, sanitized_path=True)
    (tmp_path / "bin" / "ctx").unlink()
    result = _run(env, tmp_path)
    assert "ctx" in _labels(result.stdout, "WARN"), result.stdout
    assert "ctx" not in _labels(result.stdout, "FAIL"), result.stdout
    assert "ctx.rs" in result.stdout


def test_missing_behaviour_packs_warn_with_their_cost(tmp_path: Path) -> None:
    """Behaviour-shaping layers warn: a master runs without them, differently."""

    env = _host(tmp_path)
    home = tmp_path / "home"
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        '{"plugins":{"codex@openai-codex":[{"scope":"user"}]}}', encoding="utf-8"
    )
    result = _run(env, tmp_path)
    assert "skill-stack" in _labels(result.stdout, "WARN"), result.stdout
    assert "skill-stack" not in _labels(result.stdout, "FAIL"), result.stdout
    assert "superpowers" in result.stdout
    assert "ponytail" in result.stdout
    # The consequence travels with the warning, not in a separate document.
    assert "advice rather than procedure" in result.stdout
    assert "pairs with the methodology layer" in result.stdout


def test_present_behaviour_packs_pass(tmp_path: Path) -> None:
    env = _host(tmp_path)
    home = tmp_path / "home"
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        '{"plugins":{"codex@openai-codex":[{}],"superpowers@official":[{}],'
        '"ponytail@ponytail":[{}]}}',
        encoding="utf-8",
    )
    result = _run(env, tmp_path)
    assert "skill-stack" in _labels(result.stdout, "PASS"), result.stdout
    assert "skill-stack" not in _labels(result.stdout, "WARN"), result.stdout


def test_behaviour_packs_resolve_from_a_neutral_skill_root(tmp_path: Path) -> None:
    """These packs are not one agent's plugins, so detection must not assume that."""

    env = _host(tmp_path)
    home = tmp_path / "home"
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        "{}", encoding="utf-8"
    )
    for pack in ("superpowers", "ponytail"):
        (home / ".claude" / "skills" / pack).mkdir(parents=True, exist_ok=True)
    result = _run(env, tmp_path)
    assert "skill-stack" in _labels(result.stdout, "PASS"), result.stdout
    assert "skill-stack" not in _labels(result.stdout, "WARN"), result.stdout


def test_install_hint_follows_the_selected_agent(tmp_path: Path) -> None:
    env = _host(tmp_path)
    (tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json").write_text(
        "{}", encoding="utf-8"
    )
    env["ORCA_AGENT_CLI"] = "codex"
    (tmp_path / "bin" / "codex").chmod(0o755)
    result = _run(env, tmp_path)
    assert "skill-stack" in _labels(result.stdout, "WARN"), result.stdout
    assert "/plugin install" not in result.stdout, result.stdout
    assert "skill pack for codex" in result.stdout, result.stdout


def test_essential_gaps_are_repeated_loudly_with_their_consequence(
    tmp_path: Path,
) -> None:
    """Fifteen lines of output is where the important line gets skimmed past."""

    env = _host(tmp_path, rules=None)
    result = _run(env, tmp_path)
    assert "ESSENTIAL COMPONENTS MISSING" in result.stdout, result.stdout
    assert "redaction-extra" in result.stdout
    assert "not preferences" in result.stdout


def test_no_essential_block_when_nothing_essential_is_missing(tmp_path: Path) -> None:
    """The loud block must stay rare, or it becomes decoration."""

    env = _host(tmp_path)
    home = tmp_path / "home"
    for pack in ("superpowers", "ponytail"):
        (home / ".claude" / "skills" / pack).mkdir(parents=True, exist_ok=True)
    result = _run(env, tmp_path)
    assert "ESSENTIAL COMPONENTS MISSING" not in result.stdout, result.stdout
