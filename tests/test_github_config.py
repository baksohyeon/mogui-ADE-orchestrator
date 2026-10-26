"""Coherence between the GitHub-native label config and scripts/labels-create."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from windows_exec_surface import skip_windows_exec_surface

REPO_ROOT = Path(__file__).resolve().parents[1]
GITHUB_DIR = REPO_ROOT / ".github"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _labels_create_names() -> set[str]:
    text = (REPO_ROOT / "scripts" / "labels-create").read_text(encoding="utf-8")
    block = text.split("<<'LABELS'\n", 1)[1].split("\nLABELS", 1)[0]
    return {line.split("\t", 1)[0] for line in block.splitlines() if line}


def _labeler_yml_top_level_keys() -> set[str]:
    text = (GITHUB_DIR / "labeler.yml").read_text(encoding="utf-8")
    keys = set()
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            keys.add(line.rstrip()[:-1])
    return keys


def _issue_form_labels(filename: str) -> set[str]:
    text = (GITHUB_DIR / "ISSUE_TEMPLATE" / filename).read_text(encoding="utf-8")
    match = re.search(r'^labels:\s*\[(.*)\]', text, re.MULTILINE)
    assert match, f"no labels: line in {filename}"
    return {name.strip().strip('"\'') for name in match.group(1).split(",")}


def test_every_label_name_is_replayed_by_labels_create():
    expected = set()
    expected |= _labeler_yml_top_level_keys()
    expected |= _issue_form_labels("bug_report.yml")
    expected |= _issue_form_labels("feature_request.yml")
    expected |= {"os:linux", "os:macos", "os:windows"}
    expected |= {"size/xs", "size/s", "size/m", "size/l", "size/xl"}
    expected.add("locked")

    missing = expected - _labels_create_names()
    assert not missing, f"labels missing from scripts/labels-create: {sorted(missing)}"


PERMISSIONS_BLOCK_RE = re.compile(r"^[ \t]*permissions:\n((?:[ \t]+\S.*\n?)*)", re.MULTILINE)


def _write_token_workflow_names() -> set[str]:
    """Every file under .github/workflows/ with `write` inside a permissions: block."""
    names = set()
    for path in sorted((GITHUB_DIR / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if any("write" in block for block in PERMISSIONS_BLOCK_RE.findall(text)):
            names.add(path.name)
    return names


def test_write_token_workflows_pin_actions_to_a_commit_sha():
    names = _write_token_workflow_names()
    assert names == {"issue-os-labeler.yml", "labeler.yml", "lock.yml"}
    for name in sorted(names):
        text = (GITHUB_DIR / "workflows" / name).read_text(encoding="utf-8")
        uses_lines = [line for line in text.splitlines() if "uses:" in line]
        assert uses_lines, f"no uses: lines in {name}"
        for line in uses_lines:
            ref = line.split("uses:", 1)[1].strip().split()[0]
            sha = ref.rsplit("@", 1)[-1]
            assert SHA_RE.match(sha), f"{name}: {ref} is not pinned to a commit sha"


def test_pull_request_target_workflows_have_no_checkout():
    for name in ("labeler.yml", "issue-os-labeler.yml"):
        text = (GITHUB_DIR / "workflows" / name).read_text(encoding="utf-8")
        assert "actions/checkout" not in text


def test_gates_yml_has_top_level_permissions():
    text = (GITHUB_DIR / "workflows" / "gates.yml").read_text(encoding="utf-8")
    assert re.search(r"^permissions:", text, re.MULTILINE)


def test_os_labeler_gates_on_the_bug_label():
    text = (GITHUB_DIR / "workflows" / "issue-os-labeler.yml").read_text(encoding="utf-8")
    assert "contains(github.event.issue.labels.*.name, 'bug')" in text


def test_assignee_follows_the_turn_step_reconciles_from_current_state():
    text = (GITHUB_DIR / "workflows" / "labeler.yml").read_text(encoding="utf-8")

    types_match = re.search(r"pull_request_target:\n\s*types:\s*\[(.*?)\]", text)
    assert types_match, "no pull_request_target types line in labeler.yml"
    types = {t.strip() for t in types_match.group(1).split(",")}
    assert {"labeled", "unlabeled"} <= types

    assert not re.search(r"^concurrency:", text, re.MULTILINE), "workflow-level concurrency key present"

    label_job_match = re.search(r"\n  label:\n(.*?)(?=\n  \S|\Z)", text, re.DOTALL)
    assert label_job_match, "no 'label' job in labeler.yml"
    label_concurrency_match = re.search(
        r"concurrency:\n\s*group:\s*(.+)\n\s*cancel-in-progress:\s*(\S+)", label_job_match.group(1)
    )
    assert label_concurrency_match, "no concurrency block in the label job"
    assert label_concurrency_match.group(1) == "labeler-${{ github.event.pull_request.number }}"
    assert label_concurrency_match.group(2) == "true"

    job_match = re.search(r"\n  assignee:\n(.*?)(?=\n  \S|\Z)", text, re.DOTALL)
    assert job_match, "no 'assignee' job in labeler.yml"
    job_text = job_match.group(1)

    permissions_match = re.search(r"permissions:\n((?:[ \t]+\S.*\n?)*)", job_text)
    assert permissions_match, "no permissions block in the assignee job"
    permissions_text = permissions_match.group(1)
    assert "pull-requests: write" in permissions_text
    assert "issues: write" in permissions_text
    assert "contents" not in permissions_text

    concurrency_match = re.search(
        r"concurrency:\n\s*group:\s*(.+)\n\s*cancel-in-progress:\s*(\S+)", job_text
    )
    assert concurrency_match, "no concurrency block in the assignee job"
    assert concurrency_match.group(1) == "assignee-${{ github.event.pull_request.number }}"
    assert concurrency_match.group(2) == "false"

    step_match = re.search(
        r"- name: assignee follows the turn\n(.*?)(?=\n      - name:|\Z)", job_text, re.DOTALL
    )
    assert step_match, "no step named 'assignee follows the turn' in the assignee job"
    step_text = step_match.group(1)

    assert "context.payload.action" not in step_text, "assignee step still reads the event action"
    assert "context.payload.label" not in step_text, "assignee step still reads the event label"
    assert "currentPr.labels" in step_text, "assignee step does not read current labels"
    assert 'author.endsWith("[bot]")' in step_text, "assignee step lost its bot-author guard"


@skip_windows_exec_surface
def test_labels_create_help_exits_zero_without_gh():
    with tempfile.TemporaryDirectory() as empty_dir:
        env = {**os.environ, "PATH": f"{empty_dir}{os.pathsep}{os.environ['PATH']}"}
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "labels-create"), "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 0
    assert result.stdout.startswith("usage:")
