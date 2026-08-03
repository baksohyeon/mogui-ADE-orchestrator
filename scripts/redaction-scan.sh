#!/usr/bin/env bash
# redaction-scan.sh — fail-closed pre-push / CI scan for secrets and internal identifiers.
#
# gitleaks is the matching engine. This script is what gitleaks does not do: scope
# the scan to tracked content, scan commit messages, translate the organization
# rules file into a gitleaks config, and state what was covered.
#
# Usage:
#   scripts/redaction-scan.sh                 # all tracked files (default)
#   scripts/redaction-scan.sh --staged        # index / staged only
#   scripts/redaction-scan.sh --range A..B    # files changed in a range, and those commits' messages
#   scripts/redaction-scan.sh --commit-messages A..B   # message scan in any mode
#   scripts/redaction-scan.sh --help
#
# Exit: 0 clean, 1 findings, 2 cannot decide (missing tool, missing required rules, usage)
#
# Organization-specific rules (REDACTION_EXTRA_PATTERNS)
#   Real company, product, and personal identifiers are deliberately not committed
#   here: this repository is public, so committing them would publish what they
#   protect. Supply them per checkout, one rule per line:
#
#     id|description|regex
#
#   Blank lines and lines beginning with # are skipped. Only the first two pipes
#   separate fields, so a regex may contain a pipe. Every regex must compile.
#   With REDACTION_REQUIRE_EXTRA=1, a missing or empty file exits 2 instead of
#   scanning with generic rules only.
#
# Exemptions use gitleaks' own mechanisms: a .gitleaksignore fingerprint for one
# finding, or config/gitleaks.toml for a whole class.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

BASE_CONFIG="${REPO_ROOT}/config/gitleaks.toml"
LEGACY_ALLOWLIST="${REDACTION_ALLOWLIST:-${SCRIPT_DIR}/redaction-allowlist.txt}"
MODE="tracked"
RANGE=""
COMMIT_RANGE=""
VERBOSE=0
REQUIRE_EXTRA="${REDACTION_REQUIRE_EXTRA:-0}"
COMMIT_MESSAGES_SCANNED="not-scanned"
EXTRA_RULE_COUNT=0
EXTRA_UNUSABLE=0
EXTRA_CONSIDERED=0

usage() {
  sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged) MODE="staged"; shift ;;
    --range)
      MODE="range"
      RANGE="${2:-}"
      if [[ -z "${RANGE}" || "${RANGE}" != *..* ]]; then
        echo "redaction-scan: --range requires A..B" >&2
        exit 2
      fi
      shift 2
      ;;
    --commit-messages)
      COMMIT_RANGE="${2:-}"
      if [[ -z "${COMMIT_RANGE}" ]]; then
        echo "redaction-scan: --commit-messages requires a git range" >&2
        exit 2
      fi
      shift 2
      ;;
    --allowlist)
      LEGACY_ALLOWLIST="${2:-}"
      shift 2
      ;;
    --require-extra) REQUIRE_EXTRA=1; shift ;;
    -v|--verbose) VERBOSE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "redaction-scan: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "redaction-scan: FAIL — gitleaks is not on PATH; install it (brew install gitleaks) or see https://gitleaks.io" >&2
  exit 2
fi
if [[ ! -f "${BASE_CONFIG}" ]]; then
  echo "redaction-scan: FAIL — missing ${BASE_CONFIG}" >&2
  exit 2
fi

# The previous allowlist format is no longer interpreted. Refuse loudly rather
# than ignore it: an installation whose exemptions stopped applying should hear it
# from the gate, not discover it when a finding it had accepted comes back.
if [[ -f "${LEGACY_ALLOWLIST}" ]] \
  && grep -qvE '^[[:space:]]*(#|$)' "${LEGACY_ALLOWLIST}" 2>/dev/null; then
  echo "redaction-scan: FAIL — ${LEGACY_ALLOWLIST} has entries in the retired format." >&2
  echo "redaction-scan: migrate each to a .gitleaksignore fingerprint, or to an allowlist in config/gitleaks.toml, then empty this file." >&2
  exit 2
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT
CONFIG="${BASE_CONFIG}"

# Translate the organization rules file into a gitleaks config that extends the
# committed one. The operator-facing format does not change, so no host has to
# convert anything, and the patterns stay outside version control.
if [[ -n "${REDACTION_EXTRA_PATTERNS:-}" && -f "${REDACTION_EXTRA_PATTERNS}" ]]; then
  ORG_CONFIG="${WORK_DIR}/org.toml"
  if python3 - "${REDACTION_EXTRA_PATTERNS}" "${BASE_CONFIG}" "${ORG_CONFIG}" > "${WORK_DIR}/counts" <<'PY'
import re
import sys

source, base, target = sys.argv[1], sys.argv[2], sys.argv[3]
rules, unusable, considered = [], 0, 0
with open(source, encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        considered += 1
        parts = line.split("|", 2)
        if len(parts) != 3:
            unusable += 1
            continue
        rule_id, description, regex = (part.strip() for part in parts)
        try:
            re.compile(regex)
        except re.error:
            unusable += 1
            continue
        rules.append((rule_id or f"org_rule_{len(rules)}", description, regex))

with open(target, "w", encoding="utf-8") as out:
    out.write('title = "organization rules"\n\n')
    out.write('[extend]\npath = "%s"\n\n' % base)
    for rule_id, description, regex in rules:
        out.write("[[rules]]\n")
        out.write('id = "%s"\n' % rule_id.replace('"', ""))
        out.write('description = "%s"\n' % description.replace('"', ""))
        out.write("regex = '''%s'''\n\n" % regex)

# Only literal characters can express native script in a rule that actually
# scans: this loader's re.compile gate rejects RE2's brace and property forms
# (backslash x brace, backslash p brace), and the engine canary rejects
# Python's backslash u form, so no escape spelling survives both gates.
native = sum(
    1 for _, _, regex in rules if any(ord(ch) > 127 for ch in regex)
)

# Counts only. This file's contents are what the scan protects, so nothing from it
# is printed here or anywhere else.
print(f"{len(rules)} {unusable} {considered} {native}")
PY
  then
    read -r EXTRA_RULE_COUNT EXTRA_UNUSABLE EXTRA_CONSIDERED EXTRA_NATIVE < "${WORK_DIR}/counts"
  else
    echo "redaction-scan: FAIL — could not read the organization rules file" >&2
    exit 2
  fi
  if [[ "${EXTRA_RULE_COUNT}" -gt 0 ]]; then
    CONFIG="${ORG_CONFIG}"
  else
    # The count describes what was loaded, never what the file happened to hold.
    # Reporting a number the scan did not use is the same defect this gate exists
    # to catch, one level up.
    EXTRA_RULE_COUNT=0
  fi
  if [[ "${EXTRA_UNUSABLE}" -gt 0 ]]; then
    echo "redaction-scan: WARNING — ${EXTRA_UNUSABLE} of ${EXTRA_CONSIDERED} organization rule lines are unusable and were skipped" >&2
  fi
  if [[ "${EXTRA_RULE_COUNT}" -gt 0 && "${EXTRA_NATIVE:-0}" -eq 0 ]]; then
    # A romanization only rule set misses the same identifier in its native
    # spelling; measured live when a Korean name passed a scan whose rules
    # only knew its romanization.
    echo "redaction-scan: WARNING — organization rules contain no native script pattern; romanization only identifier rules miss native spellings" >&2
  fi
fi

# The organization rules were validated by Python's re, and Python is not the
# engine. gitleaks compiles RE2, which rejects constructs Python accepts
# (lookarounds, most visibly), and it rejects them by panicking at config load.
# Every scan under a panicking config finds nothing, which reads as clean.
# Measured live: a lookbehind rule turned the whole scan into a green no-op
# while the summary reported the rules as loaded. So the merged config is
# proven against the actual engine before anything is scanned, and a failure
# names the rule ids only, never the patterns they protect.
if [[ "${CONFIG}" != "${BASE_CONFIG}" ]]; then
  if ! printf 'redaction-scan engine self-test\n' \
    | gitleaks stdin --config "${CONFIG}" --no-banner --exit-code 0 >/dev/null 2>&1; then
    # One Python pass isolates the offending rules: it reuses the same parse
    # the translator applied and probes each rule alone through gitleaks, so
    # the rules file format lives in one shape and an id indented with a tab cannot
    # slip the net. Ids only, never patterns.
    bad_ids=$(python3 - "${REDACTION_EXTRA_PATTERNS}" "${WORK_DIR}" <<'PY'
import subprocess
import sys

source, work_dir = sys.argv[1], sys.argv[2]
bad = []
with open(source, encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        rule_id, _description, regex = (part.strip() for part in parts)
        single = f"{work_dir}/single-rule.toml"
        with open(single, "w", encoding="utf-8") as out:
            out.write('title = "single rule probe"\n\n')
            out.write("[[rules]]\n")
            out.write('id = "%s"\n' % rule_id.replace('"', ""))
            out.write('description = "probe"\n')
            out.write("regex = '''%s'''\n" % regex)
        probe = subprocess.run(
            ["gitleaks", "stdin", "--config", single, "--no-banner", "--exit-code", "0"],
            input="x\n", capture_output=True, text=True,
        )
        if probe.returncode != 0:
            bad.append(rule_id)
print(" ".join(bad))
PY
)
    bad_ids="${bad_ids:+ ${bad_ids}}"
    echo "redaction-scan: FAIL — the merged config crashes the engine; organization rule(s) not supported by RE2:${bad_ids:- (rule not isolated; test the file rule by rule)}" >&2
    echo "redaction-scan: rewrite those regexes without lookarounds or other non-RE2 constructs, then re-run." >&2
    exit 2
  fi
fi

# A green scan must not imply coverage it does not have.
if [[ "${EXTRA_RULE_COUNT}" -eq 0 ]]; then
  echo "redaction-scan: WARNING — organization-specific rules not loaded (REDACTION_EXTRA_PATTERNS unset or empty); this scan covers generic patterns only" >&2
  if [[ "${REQUIRE_EXTRA}" == "1" ]]; then
    echo "redaction-scan: FAIL — required organization rules were not loaded" >&2
    exit 2
  fi
fi

list_scan_files() {
  case "${MODE}" in
    tracked) git ls-files -z ;;
    staged)  git diff --cached --name-only -z --diff-filter=ACMR ;;
    range)   git diff --name-only -z --diff-filter=ACMR "${RANGE}" ;;
  esac
}

# A range neither end of which resolves is not an empty range. git prints a
# fatal to stderr and this script used to keep going with zero files and zero
# messages, which read as clean. Measured with an unresolvable left side: OK,
# exit 0. A range that cannot be enumerated is exit 2.
if [[ -n "${RANGE}" ]] && ! git rev-list --max-count=0 "${RANGE}" >/dev/null 2>&1; then
  echo "redaction-scan: FAIL — range does not resolve in this repository: ${RANGE}" >&2
  exit 2
fi
if [[ -n "${COMMIT_RANGE}" && "${COMMIT_RANGE}" != "${RANGE}" ]] \
  && ! git rev-list --max-count=0 "${COMMIT_RANGE}" >/dev/null 2>&1; then
  echo "redaction-scan: FAIL — message range does not resolve: ${COMMIT_RANGE}" >&2
  exit 2
fi

REPORTS="${WORK_DIR}/reports"
mkdir -p "${REPORTS}"
report_index=0

scan_path() {
  # One path per invocation. gitleaks scopes a single path argument reliably and
  # falls back to the whole directory when given several, which would drag in
  # untracked files and make a tracked scan depend on local scratch.
  local path="$1"
  [[ -f "${path}" ]] || return 0
  report_index=$((report_index + 1))
  if ! gitleaks dir "${path}" \
    --config "${CONFIG}" \
    --no-banner \
    --exit-code 0 \
    --report-format json \
    --report-path "${REPORTS}/${report_index}.json" \
    >/dev/null 2>&1; then
    # --exit-code 0 makes findings exit 0, so nonzero here is the engine
    # failing, and a failed engine must not read as a clean file.
    echo "redaction-scan: FAIL — gitleaks failed on ${path} (engine error, not a finding)" >&2
    exit 2
  fi
}

scan_commit_messages() {
  # gitleaks does not read commit messages: a key present only in a message
  # returns no findings while the same key in file content is found. Measured,
  # which is why this loop exists.
  local range="$1"
  local count=0 sha
  while IFS= read -r sha; do
    [[ -z "${sha}" ]] && continue
    report_index=$((report_index + 1))
    if ! git log -1 --format=%B "${sha}" \
      | gitleaks stdin \
          --config "${CONFIG}" \
          --no-banner \
          --exit-code 0 \
          --report-format json \
          --report-path "${REPORTS}/${report_index}.json" \
          >/dev/null 2>&1; then
      echo "redaction-scan: FAIL — gitleaks failed on commit ${sha:0:12} message (engine error, not a finding)" >&2
      exit 2
    fi
    if [[ -s "${REPORTS}/${report_index}.json" ]]; then
      python3 - "${REPORTS}/${report_index}.json" "commit:${sha:0:12}" <<'PY'
import json
import sys

path, label = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    rows = json.load(handle)
for row in rows:
    row["File"] = label
with open(path, "w", encoding="utf-8") as handle:
    json.dump(rows, handle)
PY
    fi
    count=$((count + 1))
  done < <(git log --format=%H "${range}" 2>/dev/null || true)
  COMMIT_MESSAGES_SCANNED="${count}"
}

if [[ -z "${COMMIT_RANGE}" && "${MODE}" == "range" ]]; then
  COMMIT_RANGE="${RANGE}"
fi
if [[ -n "${COMMIT_RANGE}" ]]; then
  scan_commit_messages "${COMMIT_RANGE}"
fi

file_count=0
while IFS= read -r -d '' path; do
  [[ -z "${path}" ]] && continue
  file_count=$((file_count + 1))
  scan_path "${path}"
done < <(list_scan_files)

FINDINGS_FILE="${WORK_DIR}/findings.txt"
python3 - "${REPORTS}" "${FINDINGS_FILE}" > /dev/null <<'PY'
import json
import pathlib
import re
import sys

reports, out_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
MASKS = (
    (re.compile(r"(AKIA)[0-9A-Z]{16}"), r"\1****************"),
    (re.compile(r"(gh[pousr]_)[A-Za-z0-9]{8,}"), r"\1********"),
    (re.compile(r"(xox[baprs]-)[A-Za-z0-9-]{8,}"), r"\1********"),
    (re.compile(r"(sk-ant-)[A-Za-z0-9_-]{8,}"), r"\1********"),
    (re.compile(r"(sk-)[A-Za-z0-9]{8,}"), r"\1********"),
    (re.compile(r"(Bearer )[A-Za-z0-9._-]{8,}"), r"\1********"),
    (re.compile(r"""(=\s*["'])[^"']{8,}(["'])"""), r"\1***\2"),
)

lines = set()
for report in sorted(reports.glob("*.json")):
    try:
        rows = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    for row in rows:
        snippet = (row.get("Match") or "").strip()
        for pattern, replacement in MASKS:
            snippet = pattern.sub(replacement, snippet)
        lines.add(
            "  {file}:{line}  [{rule}] {desc}  :: {snippet}".format(
                file=row.get("File", "?"),
                line=row.get("StartLine", 0),
                rule=row.get("RuleID", "?"),
                desc=row.get("Description", ""),
                snippet=snippet[:160],
            )
        )
out_path.write_text("".join(f"{line}\n" for line in sorted(lines)), encoding="utf-8")
PY

FINDINGS="$(wc -l < "${FINDINGS_FILE}" | tr -d ' ')"

if [[ "${VERBOSE}" -eq 1 ]]; then
  echo "redaction-scan: mode=${MODE} range=${RANGE:-none} files=${file_count} commit-messages=${COMMIT_MESSAGES_SCANNED} org-rules=${EXTRA_RULE_COUNT} config=$(basename "${CONFIG}") engine=$(gitleaks version 2>/dev/null | head -1)"
fi

if [[ "${FINDINGS}" -gt 0 ]]; then
  echo "redaction-scan: FAIL — ${FINDINGS} finding(s) (fail-closed)" >&2
  cat "${FINDINGS_FILE}" >&2
  echo "redaction-scan: fix, or exempt with a .gitleaksignore fingerprint, then re-run." >&2
  exit 1
fi

echo "redaction-scan: OK — 0 findings (mode=${MODE}, files=${file_count}, commit-messages=${COMMIT_MESSAGES_SCANNED}, org-rules=${EXTRA_RULE_COUNT})"
exit 0
