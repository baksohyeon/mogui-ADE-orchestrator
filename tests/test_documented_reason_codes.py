"""Documentation can name dispatch gate reason codes, but only real ones.

The audit that added this test found prose using plausible reason labels as if
they were source constants. This pins reason code shaped tokens in reason code
contexts to `ReasonCode` and deliberately does not cover flags, exit codes,
script names, historical changelog removals, or other SCREAMING_SNAKE tokens
that are not dispatch gate reasons.
"""

from __future__ import annotations

import re
from pathlib import Path

from master_runtime.core.dispatch_gate import ReasonCode

REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_ROOTS = (
    REPO_ROOT / "docs",
    REPO_ROOT / "master-ops",
)
ROOT_MARKDOWN = tuple(
    path
    for path in REPO_ROOT.iterdir()
    if path.is_file() and (path.suffix == ".md" or path.name == "CHANGELOG.md")
)

CODE_SPAN = re.compile(r"`([^`]+)`")
SCREAMING_SNAKE = re.compile(r"\b[A-Z][A-Z0-9_]{1,}\b")
REASON_CONTEXT = re.compile(
    r"\b("
    r"reason(?:s| code)?|"
    r"GateDecision|"
    r"den(?:y|ies|ial)|"
    r"warn(?:s|ing|ings)?"
    r")\b",
    re.IGNORECASE,
)
NON_REASON_TOKENS = {
    "MODEL_IDENTITY_EXPECT",
    "PREFLIGHT_WAIVE",
    "WORKSPACE_ROOT",
    "ORCA_AGENT_CLI",
}


def _documentation_files() -> list[Path]:
    files = [
        path
        for root in DOC_ROOTS
        for path in root.rglob("*.md")
        if path.is_file()
    ]
    files.extend(ROOT_MARKDOWN)
    return sorted(set(files))


def _documented_reason_tokens() -> set[tuple[str, int, str]]:
    tokens: set[tuple[str, int, str]] = set()
    for path in _documentation_files():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not REASON_CONTEXT.search(line):
                continue
            for span in CODE_SPAN.findall(line):
                for token in SCREAMING_SNAKE.findall(span):
                    if "_" not in token and token != "OK":
                        continue
                    if token in NON_REASON_TOKENS:
                        continue
                    tokens.add((rel_path, line_number, token))
    return tokens


def test_documented_reason_codes_exist_in_source_enum() -> None:
    documented = _documented_reason_tokens()
    source = {reason.value for reason in ReasonCode}

    missing = sorted(
        (path, line, token)
        for path, line, token in documented
        if token not in source
    )

    assert not missing, (
        "documentation names dispatch-gate reason codes that are not in "
        f"ReasonCode: {missing}"
    )


def test_the_reason_code_check_can_fail() -> None:
    """A fabricated reason proves the comparison would catch drift."""

    source = {reason.value for reason in ReasonCode}
    assert "CANNOT_DECIDE" not in source
