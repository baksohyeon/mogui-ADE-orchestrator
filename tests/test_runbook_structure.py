from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from master_runtime.core.dispatch_gate import (
    DispatchGate,
    DispatchGateConfig,
    DispatchRequest,
    FRONT_MATTER_KNOWN_KEYS,
    ReasonCode,
    _parse_front_matter,
    _section_body,
)
from windows_exec_surface import skip_windows_exec_surface


REPO_ROOT = Path(__file__).resolve().parents[1]


def policy(tmp_path: Path) -> Path:
    path = tmp_path / "model-tier-policy.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "worker_allowed": ["gpt-5.6-luna"],
                "worker_denied_tiers": [],
                "unknown_model": "deny",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def runbook_dir(tmp_path: Path, *, brief: bool = True) -> Path:
    directory = tmp_path / "runbooks"
    directory.mkdir()
    brief_block = "\n## Brief\n\nRemember the evidence boundary.\n" if brief else ""
    (directory / "research-workflow.md").write_text(
        "---\nstatus: active\ntriggers: [research report]\n---\n"
        "# Research workflow\n"
        + brief_block,
        encoding="utf-8",
    )
    (directory / "retired.md").write_text(
        "---\nstatus: retired\n---\n# Retired\n", encoding="utf-8"
    )
    (directory / "merge-ready.md").write_text(
        "---\nstatus: active\n---\n# Merge ready\n", encoding="utf-8"
    )
    return directory


def gate(tmp_path: Path, directory: Path) -> DispatchGate:
    return DispatchGate(
        DispatchGateConfig(
            ledger_path=tmp_path / "ledger.jsonl",
            ticket_dir=tmp_path / "tickets",
            known_roots_path=tmp_path / "known-roots.json",
            tier_policy_path=policy(tmp_path),
            runbook_dir=directory,
        )
    )


def request(tmp_path: Path, body: str, **kwargs: object) -> DispatchRequest:
    contract = tmp_path / "contract.md"
    contract.write_text(body, encoding="utf-8")
    return DispatchRequest(
        runtime="codex",
        model="gpt-5.6-luna",
        contract_path=contract,
        est_input_chars=len(body),
        n_agents=1,
        completion_channel="orchestration",
        **kwargs,
    )


def frontmatter(*, runbooks: str = "", waived: str = "") -> str:
    lines = ["---", "tier: unknown", "runtime: codex", "repo: example"]
    if runbooks:
        lines.append(f"runbooks: [{runbooks}]")
    if waived:
        lines.append(f"runbooks_waived: [{waived}]")
    lines.append("---")
    return "\n".join(lines) + "\n"


def ledger(tmp_path: Path) -> dict[str, object]:
    return json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def test_unknown_runbook_is_refused_and_recorded(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    decision = gate(tmp_path, directory).check(
        request(tmp_path, frontmatter(runbooks="missing"), runbook_inject_supported=True)
    )
    assert decision.reason is ReasonCode.RUNBOOK_UNKNOWN
    assert ledger(tmp_path)["reason"] == "RUNBOOK_UNKNOWN"


def test_retired_runbook_is_unknown_and_recorded(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    decision = gate(tmp_path, directory).check(
        request(tmp_path, frontmatter(runbooks="retired"), runbook_inject_supported=True)
    )
    assert decision.reason is ReasonCode.RUNBOOK_UNKNOWN
    assert ledger(tmp_path)["reason"] == "RUNBOOK_UNKNOWN"


def test_trigger_without_listing_is_refused(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    body = frontmatter() + "The research report must retain its sources.\n"
    decision = gate(tmp_path, directory).check(request(tmp_path, body))
    assert decision.reason is ReasonCode.RUNBOOK_TRIGGER_UNLISTED
    assert ledger(tmp_path)["reason"] == "RUNBOOK_TRIGGER_UNLISTED"


def test_trigger_matching_ignores_fenced_and_inline_code(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    (directory / "literature-review.md").write_text(
        "---\nstatus: active\ntriggers: [literature review]\n---\n"
        "# Literature review\n",
        encoding="utf-8",
    )

    fenced = (
        frontmatter()
        + "```shell\nrg -n \"literature review\" docs/\n```\n"
    )
    inline = frontmatter() + "Use `literature review` as a command example.\n"
    multiline_inline = frontmatter() + "`\nliterature review\n`\n"
    separated_inline = frontmatter() + "Use literature`ignored` review as prose.\n"
    invalid_fence_info = frontmatter() + "```a``` runs a command.\nPlease complete the literature review.\n"
    indented_tilde = frontmatter() + "    ~~~\nPlease complete the literature review.\n"
    for body in (fenced, inline, multiline_inline, separated_inline):
        decision = gate(tmp_path, directory).check(request(tmp_path, body))
        assert decision.allow

    for body in (invalid_fence_info, indented_tilde):
        decision = gate(tmp_path, directory).check(request(tmp_path, body))
        assert decision.reason is ReasonCode.RUNBOOK_TRIGGER_UNLISTED
        assert "runbooks: [literature-review]" in decision.message
        assert "runbooks_waived: [literature-review]" in decision.message


@skip_windows_exec_surface
def test_section_extractors_ignore_headings_inside_fences(tmp_path: Path) -> None:
    section = (
        "---\nstatus: active\n---\n"
        "## Brief\n\nvisible before\n"
        "```markdown\n## Not a section\nhidden\n```\n"
        "visible after\n## Next\nafter\n"
    )
    runbook = tmp_path / "runbook.md"
    runbook.write_text(section, encoding="utf-8")
    expected = "visible before\n```markdown\n## Not a section\nhidden\n```\nvisible after"
    assert _section_body(section, "Brief") == expected

    dispatch = (REPO_ROOT / "master-ops" / "scripts" / "dispatch").read_text(
        encoding="utf-8"
    )
    start = dispatch.index("markdown_section() {")
    end = dispatch.index("\n}\n\n# Body text", start) + 2
    shell_function = dispatch[start:end]
    shell = subprocess.run(
        ["bash", "-c", shell_function + "\nmarkdown_section \"$1\" Brief\n", "bash", str(runbook)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert shell.returncode == 0, shell.stderr
    assert shell.stdout.rstrip("\n") == expected


@skip_windows_exec_surface
def test_dispatch_probe_skips_flag_for_old_gate_and_surfaces_diagnostics(tmp_path: Path) -> None:
    dispatch = (REPO_ROOT / "master-ops" / "scripts" / "dispatch").read_text(
        encoding="utf-8"
    )
    probe_start = dispatch.index("gate_supports_runbook_injection() {")
    probe_end = dispatch.index("\n}\n\n# Keep stdout", probe_start) + 2
    output_start = dispatch.index("gate_output_is_json() {")
    output_end = dispatch.index("\n}\n\nresolve_token_budget", output_start) + 2
    old_gate = tmp_path / "old-gate"
    old_gate.write_text(
        "#!/bin/bash\n"
        "if [ \"${1:-}\" = check ] && [ \"${2:-}\" = --help ]; then\n"
        "  echo 'usage: old gate'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'old gate failed before JSON' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    old_gate.chmod(0o755)
    diagnostics = tmp_path / "diagnostics"
    script = (
        "set +e\n"
        + dispatch[probe_start:probe_end]
        + "\n"
        + dispatch[output_start:output_end]
        + "\n"
        + f"GATE={old_gate}\n"
        + "if gate_supports_runbook_injection; then echo supported; else echo unsupported; fi\n"
        + f"GATE_STDERR_FILE={diagnostics}\n"
        + "CHK=$(\"$GATE\" check 2>\"$GATE_STDERR_FILE\") || true\n"
        + "gate_output_is_json\n"
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert "unsupported" in result.stdout
    assert "old gate failed before JSON" in result.stderr


def test_runbook_list_requires_wrapper_support(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    decision = gate(tmp_path, directory).check(
        request(tmp_path, frontmatter(runbooks="research-workflow"))
    )
    assert decision.reason is ReasonCode.RUNBOOK_INJECT_UNSUPPORTED
    assert ledger(tmp_path)["reason"] == "RUNBOOK_INJECT_UNSUPPORTED"


def test_missing_brief_is_a_warning_and_is_ledgered(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path, brief=False)
    decision = gate(tmp_path, directory).check(
        request(
            tmp_path,
            frontmatter(runbooks="research-workflow"),
            runbook_inject_supported=True,
        )
    )
    assert decision.allow
    assert ReasonCode.RUNBOOK_BRIEF_MISSING in decision.warnings
    assert "RUNBOOK_BRIEF_MISSING" in ledger(tmp_path)["warnings"]


def test_waiver_allows_trigger_and_records_both_keys(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    body = frontmatter(waived="research-workflow") + "The research report remains unlisted by design.\n"
    decision = gate(tmp_path, directory).check(request(tmp_path, body))
    assert decision.allow
    entry = ledger(tmp_path)
    assert entry["front_matter"]["runbooks_waived"] == ["research-workflow"]


def test_listed_and_waived_runbooks_are_both_recorded(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    body = frontmatter(runbooks="research-workflow", waived="merge-ready")
    decision = gate(tmp_path, directory).check(
        request(tmp_path, body, runbook_inject_supported=True)
    )
    assert decision.allow
    entry = ledger(tmp_path)
    assert entry["front_matter"]["runbooks"] == ["research-workflow"]
    assert entry["front_matter"]["runbooks_waived"] == ["merge-ready"]


def test_missing_frontmatter_keeps_trigger_as_warning(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    decision = gate(tmp_path, directory).check(
        request(tmp_path, "The research report has no contract front matter.\n")
    )
    assert decision.allow
    assert ReasonCode.RUNBOOK_TRIGGER_UNLISTED in decision.warnings


def test_missing_frontmatter_without_trigger_preserves_allow(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    decision = gate(tmp_path, directory).check(request(tmp_path, "ordinary work\n"))
    assert decision.allow
    assert decision.reason is ReasonCode.OK


def test_preserved_contract_without_frontmatter_warns_and_allows(tmp_path: Path) -> None:
    decision = gate(tmp_path, runbook_dir(tmp_path)).check(
        request(tmp_path, "ordinary work\n")
    )
    assert decision.allow
    assert ReasonCode.CONTRACT_FRONT_MATTER_MISSING in decision.warnings


def test_preserved_unknown_frontmatter_key_is_refused(tmp_path: Path) -> None:
    body = "---\ntier: unknown\nruntime: codex\nrepo: example\nunknown: value\n---\n"
    decision = gate(tmp_path, runbook_dir(tmp_path)).check(request(tmp_path, body))
    assert decision.reason is ReasonCode.CONTRACT_FRONT_MATTER


def test_preserved_unknown_standing_rule_is_refused(tmp_path: Path) -> None:
    body = (
        "---\ntier: unknown\nruntime: codex\nrepo: example\n"
        "standing_rules: [missing-rule]\n---\nordinary work\n"
    )
    decision = gate(tmp_path, runbook_dir(tmp_path)).check(request(tmp_path, body))
    assert decision.reason is ReasonCode.STANDING_RULE_UNKNOWN


def test_preserved_frontmatter_without_runbooks_and_without_trigger_allows(
    tmp_path: Path,
) -> None:
    decision = gate(tmp_path, runbook_dir(tmp_path)).check(
        request(tmp_path, frontmatter() + "ordinary work\n")
    )
    assert decision.allow
    assert decision.reason is ReasonCode.OK


def test_old_gate_new_contract_refuses_runbook_key(tmp_path: Path) -> None:
    del tmp_path
    old_keys = frozenset(FRONT_MATTER_KNOWN_KEYS - {"runbooks", "runbooks_waived"})
    parsed, error = _parse_front_matter(
        frontmatter(runbooks="research-workflow"), known_keys=old_keys
    )
    assert parsed is None
    assert error == "unknown key: runbooks"


def test_new_gate_old_wrapper_refuses_before_injection(tmp_path: Path) -> None:
    decision = gate(tmp_path, runbook_dir(tmp_path)).check(
        request(tmp_path, frontmatter(runbooks="research-workflow"))
    )
    assert decision.reason is ReasonCode.RUNBOOK_INJECT_UNSUPPORTED


def test_dispatch_gate_cli_accepts_named_runbook_with_injection_support(tmp_path: Path) -> None:
    directory = runbook_dir(tmp_path)
    contract = tmp_path / "contract.md"
    contract.write_text(frontmatter(runbooks="research-workflow") + "ordinary work\n", encoding="utf-8")
    script = REPO_ROOT / "scripts" / "dispatch-gate"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "check",
            "--runtime",
            "codex",
            "--model",
            "gpt-5.6-luna",
            "--tier-policy",
            str(policy(tmp_path)),
            "--contract",
            str(contract),
            "--agents",
            "1",
            "--est-chars",
            "100",
            "--completion-channel",
            "orchestration",
            "--runbook-inject-supported",
            "--no-record",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "DISPATCH_RUNBOOKS_DIR": str(directory)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["allow"] is True


def test_founding_install_seeds_index_and_passes_check(tmp_path: Path) -> None:
    template = REPO_ROOT / "master-ops"
    install = tmp_path / "master-ops"
    manifest = json.loads((template / "MANIFEST.json").read_text(encoding="utf-8"))
    assert "docs/runbooks/README.md" in manifest["files"]
    assert "docs/runbooks/README.md" in manifest["instance_owned"]
    for relative in manifest["files"]:
        source = template / relative
        target = install / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    result = subprocess.run(
        [sys.executable, str(install / "scripts" / "runbook-index"), "--check"],
        cwd=install,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_index_check_detects_deleted_line_and_recovers(tmp_path: Path) -> None:
    index = REPO_ROOT / "master-ops" / "scripts" / "runbook-index"
    check = subprocess.run(
        [sys.executable, str(index), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr

    readme = REPO_ROOT / "master-ops" / "docs" / "runbooks" / "README.md"
    original = readme.read_text(encoding="utf-8")
    try:
        deleted = next(line for line in original.splitlines() if "(land.md)" in line)
        readme.write_text(original.replace(deleted + "\n", "", 1), encoding="utf-8")
        stale = subprocess.run(
            [sys.executable, str(index), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert stale.returncode == 1
    finally:
        readme.write_text(original, encoding="utf-8")
