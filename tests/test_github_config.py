"""Coherence between the GitHub-native label config and scripts/labels-create."""

from __future__ import annotations

import re
from pathlib import Path

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
