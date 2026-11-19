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
#   scripts/redaction-scan.sh --repo-root PATH         # scan PATH's repository instead of this one
#   REDACTION_REPO_ROOT=PATH scripts/redaction-scan.sh # same, when a flag cannot be passed
#   An empty REDACTION_REPO_ROOT is treated as unset (today's behaviour); an empty
#   or missing --repo-root operand is a usage error (exit 2).
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
#   When REDACTION_EXTRA_PATTERNS is unset or empty, the loader checks the
#   workspace-root .redaction-extra.txt first, then ~/.config/redaction-extra.txt.
#   REDACTION_WORKSPACE_ROOT overrides the detected workspace root when a host's
#   checkout layout cannot expose its main checkout location.
#   REDACTION_PROFILE accepts internal or export and defaults to export; internal
#   skips workspace_ rules and counts them as export-only-skipped. A non-empty
#   value outside those choices exits 2.
#   With REDACTION_REQUIRE_EXTRA=1, a missing or empty file exits 2 instead of
#   scanning with generic rules only.
#
# Exemptions use gitleaks' own mechanisms: a .gitleaksignore fingerprint for one
# finding, or config/gitleaks.toml for a whole class.
set -euo pipefail

# Inherited GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_COMMON_DIR,
# GIT_OBJECT_DIRECTORY, or GIT_ALTERNATE_OBJECT_DIRECTORIES would make every git
# call below use the caller's repository, or its object store, instead of the
# resolved target's.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR \
  GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BASE_CONFIG="${REPO_ROOT}/config/gitleaks.toml"
LEGACY_ALLOWLIST="${REDACTION_ALLOWLIST:-${SCRIPT_DIR}/redaction-allowlist.txt}"
MODE="tracked"
RANGE=""
COMMIT_RANGE=""
VERBOSE=0
REQUIRE_EXTRA="${REDACTION_REQUIRE_EXTRA:-0}"
TARGET_ROOT_INPUT="${REDACTION_REPO_ROOT:-}"
COMMIT_MESSAGES_SCANNED="not-scanned"
EXTRA_RULE_COUNT=0
EXTRA_UNUSABLE=0
EXTRA_CONSIDERED=0
EXTRA_EXPORT_ONLY_SKIPPED=0
EXTRA_SOURCE="none"
REDACTION_PROFILE="${REDACTION_PROFILE:-export}"
case "${REDACTION_PROFILE}" in
  internal|export) ;;
  *)
    echo "redaction-scan: REDACTION_PROFILE must be internal or export (received: ${REDACTION_PROFILE})" >&2
    exit 2
    ;;
esac

resolve_user_path() {
  local value="$1"
  local invocation_pwd="$2"
  case "${value}" in
    "~") printf '%s\n' "${HOME:-}" ;;
    "~/"*) printf '%s/%s\n' "${HOME:-}" "${value#\~/}" ;;
    /*) printf '%s\n' "${value}" ;;
    *) printf '%s/%s\n' "${invocation_pwd}" "${value}" ;;
  esac
}

resolve_workspace_root() {
  local target_root="$1"
  local invocation_pwd="$2"
  local common_dir
  local main_checkout
  if [[ -n "${REDACTION_WORKSPACE_ROOT:-}" ]]; then
    resolve_user_path "${REDACTION_WORKSPACE_ROOT}" "${invocation_pwd}"
  elif common_dir="$(git -C "${target_root}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    && [[ -n "${common_dir}" ]]; then
    main_checkout="$(dirname "${common_dir}")"
    printf '%s\n' "$(dirname "${main_checkout}")"
  else
    printf '%s\n' "$(dirname "${target_root}")"
  fi
}

usage() {
  sed -n '2,41p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
    --repo-root)
      if [[ -z "${2:-}" ]]; then
        echo "redaction-scan: --repo-root requires a path" >&2
        exit 2
      fi
      TARGET_ROOT_INPUT="${2}"
      shift 2
      ;;
    --require-extra) REQUIRE_EXTRA=1; shift ;;
    -v|--verbose) VERBOSE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "redaction-scan: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The target to scan: this script's own repository unless told otherwise. The
# gitleaks config (config/gitleaks.toml) stays anchored to REPO_ROOT, since that
# is the scanner's own policy and the target cannot be expected to carry it.
TARGET_ROOT="${REPO_ROOT}"
if [[ -n "${TARGET_ROOT_INPUT}" ]]; then
  if ! TARGET_ROOT="$(git -C "${TARGET_ROOT_INPUT}" rev-parse --show-toplevel 2>/dev/null)"; then
    echo "redaction-scan: --repo-root (or REDACTION_REPO_ROOT) is not inside a git work tree: ${TARGET_ROOT_INPUT}" >&2
    exit 2
  fi
fi

INVOCATION_PWD="${PWD}"
WORKSPACE_ROOT="$(resolve_workspace_root "${TARGET_ROOT}" "${INVOCATION_PWD}")"
WORKSPACE_EXTRA="${WORKSPACE_ROOT}/.redaction-extra.txt"
LEGACY_EXTRA="${HOME:-}/.config/redaction-extra.txt"
if [[ -n "${REDACTION_EXTRA_PATTERNS:-}" ]]; then
  EXTRA_SOURCE="env"
elif [[ -f "${WORKSPACE_EXTRA}" ]]; then
  REDACTION_EXTRA_PATTERNS="${WORKSPACE_EXTRA}"
  EXTRA_SOURCE="workspace-root"
elif [[ -f "${LEGACY_EXTRA}" ]]; then
  REDACTION_EXTRA_PATTERNS="${LEGACY_EXTRA}"
  EXTRA_SOURCE="legacy-home"
else
  REDACTION_EXTRA_PATTERNS=""
fi

# A relative REDACTION_EXTRA_PATTERNS, --allowlist, or REDACTION_PYTHON value
# is what the caller typed at the invocation directory, not at REPO_ROOT or
# TARGET_ROOT: resolve all three before the cd below changes what a relative
# path would mean. A REDACTION_PYTHON with no slash is a bare command name
# (for example python3.11) and stays as-is so it keeps resolving through PATH.
if [[ -n "${REDACTION_EXTRA_PATTERNS:-}" && "${REDACTION_EXTRA_PATTERNS}" != /* ]]; then
  REDACTION_EXTRA_PATTERNS="$(resolve_user_path "${REDACTION_EXTRA_PATTERNS}" "${INVOCATION_PWD}")"
fi
if [[ "${LEGACY_ALLOWLIST}" != /* ]]; then
  LEGACY_ALLOWLIST="${INVOCATION_PWD}/${LEGACY_ALLOWLIST}"
fi
if [[ -n "${REDACTION_PYTHON:-}" && "${REDACTION_PYTHON}" == */* && "${REDACTION_PYTHON}" != /* ]]; then
  REDACTION_PYTHON="${INVOCATION_PWD}/${REDACTION_PYTHON}"
fi
cd "${TARGET_ROOT}"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "redaction-scan: FAIL — gitleaks is not on PATH; install it (brew install gitleaks) or see https://gitleaks.io" >&2
  exit 2
fi

# Resolve one interpreter for every heredoc call below. REDACTION_PYTHON lets
# a caller that already knows which interpreter to use say so (a relative path
# in it was already anchored to the invocation directory above). Absent an
# override, fall back to python3, unless that name -- or the python fallback
# -- resolves under WindowsApps, which opens an installer prompt instead of
# running; the match is case-insensitive because Windows paths are.
PYTHON="${REDACTION_PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="python3"
  if command -v python3 >/dev/null 2>&1; then
    case "$(command -v python3)" in
      */[Ww][Ii][Nn][Dd][Oo][Ww][Ss][Aa][Pp][Pp][Ss]/python3*)
        PYTHON="python"
        if command -v python >/dev/null 2>&1; then
          case "$(command -v python)" in
            */[Ww][Ii][Nn][Dd][Oo][Ww][Ss][Aa][Pp][Pp][Ss]/python*) PYTHON="" ;;
          esac
        fi
        ;;
    esac
  else
    PYTHON="python"
  fi
fi
if [[ -z "${PYTHON}" ]]; then
  echo "redaction-scan: FAIL - no usable python3 is on PATH (python3 and python both resolve under WindowsApps); install Python 3 or set REDACTION_PYTHON" >&2
  exit 2
fi
if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "redaction-scan: FAIL - ${PYTHON} is not on PATH (python3, or REDACTION_PYTHON); install Python 3 (e.g. brew install python or apt install python3)" >&2
  exit 2
fi
if ! "${PYTHON}" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
  echo "redaction-scan: FAIL - could not decide: ${PYTHON} did not run a basic Python 3 check" >&2
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
  if "${PYTHON}" - "${REDACTION_EXTRA_PATTERNS}" "${BASE_CONFIG}" "${ORG_CONFIG}" "${REDACTION_PROFILE}" > "${WORK_DIR}/counts" <<'PY'
import re
import sys

source, base, target, profile = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
rules, unusable, considered, export_only_skipped = [], 0, 0, 0
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
        if profile == "internal" and rule_id.startswith("workspace_"):
            export_only_skipped += 1
            continue
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
print(f"{len(rules)} {unusable} {considered} {native} {export_only_skipped}")
PY
  then
    read -r EXTRA_RULE_COUNT EXTRA_UNUSABLE EXTRA_CONSIDERED EXTRA_NATIVE EXTRA_EXPORT_ONLY_SKIPPED < "${WORK_DIR}/counts"
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
    bad_ids=$("${PYTHON}" - "${REDACTION_EXTRA_PATTERNS}" "${WORK_DIR}" "${REDACTION_PROFILE}" <<'PY'
import subprocess
import sys

source, work_dir, profile = sys.argv[1], sys.argv[2], sys.argv[3]
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
        if profile == "internal" and rule_id.startswith("workspace_"):
            continue
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
  if [[ "${EXTRA_SOURCE}" == "none" ]]; then
    echo "redaction-scan: WARNING - organization-specific rules not loaded (REDACTION_EXTRA_PATTERNS unset or empty; looked at ${WORKSPACE_EXTRA} and ${LEGACY_EXTRA}); this scan covers generic patterns only" >&2
  else
    echo "redaction-scan: WARNING - organization-specific rules not loaded (source=${EXTRA_SOURCE}, profile=${REDACTION_PROFILE}); this scan covers generic patterns only" >&2
  fi
  if [[ "${REQUIRE_EXTRA}" == "1" ]]; then
    echo "redaction-scan: FAIL — required organization rules were not loaded" >&2
    exit 2
  fi
fi

list_scan_files() {
  case "${MODE}" in
    tracked) git ls-files -z ;;
    staged)  git diff --cached --name-only -z --diff-filter=ACMR ;;
    range)   git diff --no-renames --name-only -z --diff-filter=ACMR "${RANGE}" ;;
  esac
}

# A range endpoint that cannot resolve is not an empty range. Git can print a
# fatal to stderr while returning no commits, which must never read as clean.
# A range that cannot be enumerated is exit 2 with a named reason.
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

annotate_report() {
  local report_path="$1"
  local origin="$2"
  local file_label="${3:-}"
  "${PYTHON}" - "${report_path}" "${origin}" "${file_label}" <<'PY'
import json
import sys

path, origin, file_label = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    rows = json.load(handle)
for row in rows:
    row["Origin"] = origin
    if file_label:
        row["File"] = file_label
with open(path, "w", encoding="utf-8") as handle:
    json.dump(rows, handle)
PY
}

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
  if grep -q '"RuleID"' "${REPORTS}/${report_index}.json"; then
    annotate_report "${REPORTS}/${report_index}.json" "file_content"
  fi
}

scan_commit_messages() {
  # gitleaks does not read commit messages: a key present only in a message
  # returns no findings while the same key in file content is found. Measured,
  # which is why this loop exists.
  local range="$1"
  local count=0 sha
  local sha_list="${WORK_DIR}/commits-to-scan"
  local list_rc=0
  git log --format=%H "${range}" > "${sha_list}" 2>/dev/null || list_rc=$?
  if [[ "${list_rc}" -ne 0 ]]; then
    echo "redaction-scan: FAIL: cannot list commits for range=${range} (git exit ${list_rc})" >&2
    exit 2
  fi
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
      annotate_report "${REPORTS}/${report_index}.json" "commit_message" "commit:${sha:0:12}"
    fi
    count=$((count + 1))
  done < "${sha_list}"
  COMMIT_MESSAGES_SCANNED="${count}"
}

if [[ -z "${COMMIT_RANGE}" && "${MODE}" == "range" ]]; then
  COMMIT_RANGE="${RANGE}"
fi
if [[ -n "${COMMIT_RANGE}" ]]; then
  scan_commit_messages "${COMMIT_RANGE}"
fi

FILES_LIST="${WORK_DIR}/files-to-scan"
list_rc=0
list_scan_files > "${FILES_LIST}" || list_rc=$?
if [[ "${list_rc}" -ne 0 ]]; then
  echo "redaction-scan: FAIL: cannot list files for mode=${MODE} (git exit ${list_rc})" >&2
  exit 2
fi

# Range mode uses gitleaks' commit-aware scan for the blocking set. The tip
# file scan below supplies only warnings for findings that are absent from this
# set. A separate filter-path list keeps smudged content blocking because git
# mode reads the pointer blob rather than the working-tree content.
RANGE_GIT_REPORT="${WORK_DIR}/range-git.json"
FILTERED_PATHS="${WORK_DIR}/filtered-paths.json"
if [[ "${MODE}" == "range" ]]; then
  if ! "${PYTHON}" - "${FILES_LIST}" "${FILTERED_PATHS}" > "${WORK_DIR}/filter-paths-error" <<'PY'
import json
import subprocess
import sys

files_list_path, output_path = sys.argv[1:3]
with open(files_list_path, "rb") as handle:
    paths = [path.decode("utf-8") for path in handle.read().split(b"\0") if path]

result = subprocess.run(
    ["git", "check-attr", "-z", "--stdin", "filter"],
    input="\0".join(paths),
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print(
        f"could not read filter attributes (git exit {result.returncode}): "
        f"{result.stderr.strip()[:200]}"
    )
    sys.exit(1)

fields = result.stdout.split("\0")[:-1] if result.stdout else []
filtered = {
    fields[index]
    for index in range(0, len(fields), 3)
    if index + 2 < len(fields)
    and fields[index + 2] not in ("unspecified", "unset")
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(sorted(filtered), handle)
PY
  then
    reason="$(cat "${WORK_DIR}/filter-paths-error" 2>/dev/null)"
    echo "redaction-scan: FAIL — could not determine filtered paths${reason:+: ${reason}}" >&2
    exit 2
  fi

  if ! gitleaks git \
    --log-opts="${RANGE}" \
    --config "${CONFIG}" \
    --no-banner \
    --exit-code 0 \
    --report-format json \
    --report-path "${RANGE_GIT_REPORT}" \
    "${TARGET_ROOT}" \
    >/dev/null 2>&1; then
    echo "redaction-scan: FAIL — gitleaks git could not scan range ${RANGE} (engine error, not a finding)" >&2
    exit 2
  fi
  if [[ ! -f "${RANGE_GIT_REPORT}" ]]; then
    echo "redaction-scan: FAIL — gitleaks git returned no report for range ${RANGE}" >&2
    exit 2
  fi
fi

file_count=0
while IFS= read -r -d '' path; do
  [[ -z "${path}" ]] && continue
  file_count=$((file_count + 1))
  scan_path "${path}"
done < "${FILES_LIST}"

# Stale .gitleaksignore fingerprints (tracked mode only; a staged or range
# subset would make an untouched file's still-valid fingerprint read as
# stale purely because this run never scanned that file). A fingerprint is
# path:rule:line: it drifts as soon as a line above it shifts, so this reruns
# the same files — and, when this run also scanned commit messages, those
# same commits — with ignore-matching turned off, and reports any listed
# fingerprint that now matches nothing live. This never fails the scan on
# its own: the finding the drift exposes, if any, already fails on its own
# in the normal pass above, uncovered by any fingerprint that still matches
# it. A malformed .gitleaksignore (for example, a non-UTF-8 byte) is a
# distinct problem from drift and fails closed with its own named reason.
GITLEAKSIGNORE="${TARGET_ROOT}/.gitleaksignore"
STALE_FINGERPRINTS_FILE="${WORK_DIR}/stale-fingerprints.txt"
: > "${STALE_FINGERPRINTS_FILE}"
if [[ "${MODE}" == "tracked" && -f "${GITLEAKSIGNORE}" ]] \
  && grep -qvE '^[[:space:]]*(#|$)' "${GITLEAKSIGNORE}"; then
  UNFILTERED_REPORTS="${WORK_DIR}/reports-unfiltered"
  mkdir -p "${UNFILTERED_REPORTS}"
  NO_IGNORE_DIR="${WORK_DIR}/no-ignore"
  mkdir -p "${NO_IGNORE_DIR}"
  ufi_index=0
  while IFS= read -r -d '' path; do
    [[ -z "${path}" ]] && continue
    [[ -f "${path}" ]] || continue
    ufi_index=$((ufi_index + 1))
    if ! gitleaks dir "${path}" \
      --config "${CONFIG}" \
      --no-banner \
      --exit-code 0 \
      --report-format json \
      --report-path "${UNFILTERED_REPORTS}/${ufi_index}.json" \
      -i "${NO_IGNORE_DIR}" \
      >/dev/null 2>&1; then
      echo "redaction-scan: FAIL — gitleaks failed on ${path} during the fingerprint-staleness check (engine error, not a finding)" >&2
      exit 2
    fi
    if grep -q '"RuleID"' "${UNFILTERED_REPORTS}/${ufi_index}.json"; then
      annotate_report "${UNFILTERED_REPORTS}/${ufi_index}.json" "file_content"
    fi
  done < "${FILES_LIST}"

  # Commit-message findings (scan_commit_messages above) use gitleaks' stdin
  # fingerprint shape (no file, so "" instead of a path) and never appear in
  # the dir rescan above: without this, every .gitleaksignore entry exempting
  # one would always read as stale, even while actively suppressing a live
  # secret in the same run (measured with --commit-messages). `gitleaks
  # stdin` has no source directory of its own, so -i does not replace its
  # default "." lookup the way it does for `dir`: it reads from both the
  # working directory's real .gitleaksignore AND -i (measured with -l
  # debug, two "found .gitleaksignore file" lines). Running it with its
  # working directory set to NO_IGNORE_DIR, which holds no .gitleaksignore,
  # is what actually disables it.
  if [[ -n "${COMMIT_RANGE}" ]]; then
    ufm_index=0
    while IFS= read -r sha; do
      [[ -z "${sha}" ]] && continue
      ufm_index=$((ufm_index + 1))
      if ! ( cd "${NO_IGNORE_DIR}" && git -C "${TARGET_ROOT}" log -1 --format=%B "${sha}" \
        | gitleaks stdin \
            --config "${CONFIG}" \
            --no-banner \
            --exit-code 0 \
            --report-format json \
            --report-path "${UNFILTERED_REPORTS}/commit-${ufm_index}.json" \
            -i "${NO_IGNORE_DIR}" \
            >/dev/null 2>&1 ); then
        echo "redaction-scan: FAIL — gitleaks failed on commit ${sha:0:12} message during the fingerprint-staleness check (engine error, not a finding)" >&2
        exit 2
      fi
      if grep -q '"RuleID"' "${UNFILTERED_REPORTS}/commit-${ufm_index}.json"; then
        annotate_report "${UNFILTERED_REPORTS}/commit-${ufm_index}.json" "commit_message" "commit:${sha:0:12}"
      fi
    done < "${WORK_DIR}/commits-to-scan"
  fi

  STALE_CHECK_ERROR="${WORK_DIR}/stale-check-error"
  if ! "${PYTHON}" - "${GITLEAKSIGNORE}" "${UNFILTERED_REPORTS}" "${STALE_FINGERPRINTS_FILE}" \
    "${COMMIT_RANGE:+1}" \
    > "${STALE_CHECK_ERROR}" <<'PY'
import json
import pathlib
import sys

ignore_path, reports_dir, out_path = (
    pathlib.Path(sys.argv[1]),
    pathlib.Path(sys.argv[2]),
    pathlib.Path(sys.argv[3]),
)
commit_messages_scanned = len(sys.argv) > 4 and sys.argv[4] == "1"

try:
    ignore_text = ignore_path.read_text(encoding="utf-8")
except (OSError, UnicodeDecodeError) as exc:
    print(f"cannot read {ignore_path}: {exc}")
    sys.exit(1)

listed = []
for line in ignore_text.splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    # A commit-message fingerprint has no file, so it starts with the
    # separator (":rule:line"). This run only rescans commit messages when
    # it scanned them in the first place: without that, such an entry
    # cannot be told apart from stale, so it is left unchecked rather than
    # reported stale on an absence this run never looked at (the same
    # principle a staged/range file subset already gets, above).
    if stripped.startswith(":") and not commit_messages_scanned:
        continue
    path, separator, remainder = stripped.partition(":")
    normalized = f"{path.replace(chr(92), '/')}{separator}{remainder}"
    listed.append((stripped, normalized))

live = set()
for report in sorted(pathlib.Path(reports_dir).glob("*.json")):
    try:
        rows = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    for row in rows:
        fingerprint = row.get("Fingerprint")
        if fingerprint:
            path, separator, remainder = fingerprint.partition(":")
            live.add(f"{path.replace(chr(92), '/')}{separator}{remainder}")

stale = [original for original, normalized in listed if normalized not in live]
out_path.write_text("".join(f"{fp}\n" for fp in stale), encoding="utf-8")
PY
  then
    reason="$(cat "${STALE_CHECK_ERROR}" 2>/dev/null)"
    echo "redaction-scan: FAIL — could not check .gitleaksignore for stale fingerprints${reason:+: ${reason}}" >&2
    exit 2
  fi
fi

STALE_COUNT="$(wc -l < "${STALE_FINGERPRINTS_FILE}" | tr -d ' ')"
if [[ "${STALE_COUNT}" -gt 0 ]]; then
  echo "redaction-scan: WARNING — ${STALE_COUNT} .gitleaksignore fingerprint(s) match no current finding (stale; the exempted line likely shifted or was removed); review ${GITLEAKSIGNORE}:" >&2
  cat "${STALE_FINGERPRINTS_FILE}" >&2
fi

FINDINGS_FILE="${WORK_DIR}/findings.txt"
PREEXISTING_FILE="${WORK_DIR}/preexisting.txt"
"${PYTHON}" - "${REPORTS}" "${FINDINGS_FILE}" "${PREEXISTING_FILE}" "${MODE}" "${RANGE_GIT_REPORT}" "${FILTERED_PATHS}" > /dev/null <<'PY'
import hashlib
import json
import pathlib
import re
import sys

reports, findings_path, preexisting_path, mode, range_report_path, filtered_path = (
    pathlib.Path(sys.argv[1]),
    pathlib.Path(sys.argv[2]),
    pathlib.Path(sys.argv[3]),
    sys.argv[4],
    pathlib.Path(sys.argv[5]),
    pathlib.Path(sys.argv[6]),
)
MASKS = (
    (re.compile(r"(AKIA)[0-9A-Z]{16}"), r"\1****************"),
    (re.compile(r"(gh[pousr]_)[A-Za-z0-9]{8,}"), r"\1********"),
    (re.compile(r"(xox[baprs]-)[A-Za-z0-9-]{8,}"), r"\1********"),
    (re.compile(r"(sk-ant-)[A-Za-z0-9_-]{8,}"), r"\1********"),
    (re.compile(r"(sk-)[A-Za-z0-9]{8,}"), r"\1********"),
    (re.compile(r"(Bearer )[A-Za-z0-9._-]{8,}"), r"\1********"),
    (re.compile(r"""(=\s*["'])[^"']{8,}(["'])"""), r"\1***\2"),
)


def canonical_path(value):
    value = (value or "").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def finding_key(row):
    fingerprint = row.get("Fingerprint")
    commit = row.get("Commit")
    if isinstance(fingerprint, str) and fingerprint:
        if isinstance(commit, str) and commit and fingerprint.startswith(commit + ":"):
            fingerprint = fingerprint[len(commit) + 1 :]
        return ("fingerprint", canonical_path(fingerprint))

    # Gitleaks normally supplies Fingerprint. Keep a fail-closed fallback for
    # engine output that omits it, while avoiding the secret in the key itself.
    secret = row.get("Secret")
    secret_hash = hashlib.sha256(str(secret).encode("utf-8")).hexdigest()
    return (
        "fields",
        canonical_path(row.get("File")),
        row.get("RuleID"),
        row.get("StartLine"),
        row.get("EndLine"),
        secret_hash,
    )


def render(row):
    file_ = row.get("File", "?")
    start_value = row.get("StartLine")
    start = start_value if isinstance(start_value, int) and not isinstance(start_value, bool) else 0
    snippet = (row.get("Match") or "").strip()
    for pattern, replacement in MASKS:
        snippet = pattern.sub(replacement, snippet)
    return "  {file}:{line}  [{rule}] {desc}  :: {snippet}".format(
        file=file_,
        line=start,
        rule=row.get("RuleID", "?"),
        desc=row.get("Description", ""),
        snippet=snippet[:160],
    )


range_rows = []
filtered_paths = set()
if mode == "range":
    try:
        range_rows = json.loads(range_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        range_rows = []
    try:
        filtered_paths = {
            canonical_path(path)
            for path in json.loads(filtered_path.read_text(encoding="utf-8"))
        }
    except (OSError, json.JSONDecodeError):
        filtered_paths = set()

range_keys = {finding_key(row) for row in range_rows if row.get("File")}

blocking = set()
preexisting = set()

# The gitleaks git report is the blocking set. This includes findings in files
# that were added and deleted inside the range, which the tip scan cannot see.
if mode == "range":
    for row in range_rows:
        if row.get("File"):
            blocking.add(render(row))

for report in sorted(reports.glob("*.json")):
    try:
        rows = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    for row in rows:
        line_text = render(row)
        if mode != "range" or row.get("Origin") == "commit_message":
            blocking.add(line_text)
            continue

        file_ = canonical_path(row.get("File"))
        if file_ in filtered_paths or finding_key(row) in range_keys:
            blocking.add(line_text)
        else:
            preexisting.add(line_text)

findings_path.write_text(
    "".join(f"{line}\n" for line in sorted(blocking)), encoding="utf-8"
)
preexisting_path.write_text(
    "".join(f"{line}\n" for line in sorted(preexisting)), encoding="utf-8"
)
PY

FINDINGS="$(wc -l < "${FINDINGS_FILE}" | tr -d ' ')"
PREEXISTING_COUNT="$(wc -l < "${PREEXISTING_FILE}" | tr -d ' ')"

if [[ "${VERBOSE}" -eq 1 ]]; then
  echo "redaction-scan: mode=${MODE} range=${RANGE:-none} files=${file_count} commit-messages=${COMMIT_MESSAGES_SCANNED} org-rules=${EXTRA_RULE_COUNT} org-rules-source=${EXTRA_SOURCE} profile=${REDACTION_PROFILE} export-only-skipped=${EXTRA_EXPORT_ONLY_SKIPPED} pre-existing=${PREEXISTING_COUNT} stale-fingerprints=${STALE_COUNT} config=$(basename "${CONFIG}") engine=$(gitleaks version 2>/dev/null | head -1) root=${TARGET_ROOT}"
fi

if [[ "${PREEXISTING_COUNT}" -gt 0 ]]; then
  echo "redaction-scan: WARNING — ${PREEXISTING_COUNT} pre-existing finding(s) absent from the range's gitleaks git report (not blocking in range mode, still exempt only via .gitleaksignore):" >&2
  cat "${PREEXISTING_FILE}" >&2
fi

if [[ "${FINDINGS}" -gt 0 ]]; then
  echo "redaction-scan: FAIL: ${FINDINGS} finding(s) (profile=${REDACTION_PROFILE}, fail-closed, pre-existing=${PREEXISTING_COUNT}, stale-fingerprints=${STALE_COUNT}, root=${TARGET_ROOT})" >&2
  cat "${FINDINGS_FILE}" >&2
  echo "redaction-scan: fix, or exempt with a .gitleaksignore fingerprint, then re-run." >&2
  exit 1
fi

echo "redaction-scan: OK: 0 findings (mode=${MODE}, files=${file_count}, commit-messages=${COMMIT_MESSAGES_SCANNED}, org-rules=${EXTRA_RULE_COUNT}, org-rules-source=${EXTRA_SOURCE}, profile=${REDACTION_PROFILE}, export-only-skipped=${EXTRA_EXPORT_ONLY_SKIPPED}, pre-existing=${PREEXISTING_COUNT}, stale-fingerprints=${STALE_COUNT}, read-proof-tokens ack-<12 hex> are allowlisted, root=${TARGET_ROOT})"
exit 0
