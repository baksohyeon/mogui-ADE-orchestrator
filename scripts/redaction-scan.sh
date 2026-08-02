#!/usr/bin/env bash
# redaction-scan.sh — fail-closed pre-push / CI scan for secrets and internal identifiers.
#
# Usage:
#   scripts/redaction-scan.sh                 # scan all tracked files (default)
#   scripts/redaction-scan.sh --staged        # index / staged only
#   scripts/redaction-scan.sh --range A..B    # files changed in git range, and those commits' messages (pre-push)
#   scripts/redaction-scan.sh --commit-messages A..B  # message scan in any mode
#   scripts/redaction-scan.sh --help
#
# Exit: 0 clean, 1 findings (or usage/tool error), 2 internal error
#
# Allowlist: scripts/redaction-allowlist.txt (or REDACTION_ALLOWLIST env path)
#   # comment
#   path/to/file:LINE          # silence that file:line
#   path/to/file               # silence whole file
#   PREFIX:/Users/dev/         # silence matches whose text contains this prefix
#   RULE:rule_id               # silence a whole rule (use sparingly)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

ALLOWLIST_FILE="${REDACTION_ALLOWLIST:-${SCRIPT_DIR}/redaction-allowlist.txt}"
REQUIRE_EXTRA="${REDACTION_REQUIRE_EXTRA:-0}"
MODE="tracked"   # tracked | staged | range
RANGE=""
VERBOSE=0

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged) MODE="staged"; shift ;;
    --commit-messages)
      COMMIT_RANGE="${2:-}"
      if [[ -z "${COMMIT_RANGE}" ]]; then
        echo "redaction-scan: --commit-messages requires a git range" >&2
        exit 2
      fi
      shift 2
      ;;
    --range)
      MODE="range"
      RANGE="${2:-}"
      if [[ -z "${RANGE}" ]]; then
        echo "redaction-scan: --range requires A..B" >&2
        exit 1
      fi
      shift 2
      ;;
    --allowlist)
      ALLOWLIST_FILE="${2:-}"
      shift 2
      ;;
    --require-extra) REQUIRE_EXTRA=1; shift ;;
    -v|--verbose) VERBOSE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "redaction-scan: unknown arg: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "redaction-scan: git is required" >&2
  exit 2
fi
if ! command -v rg >/dev/null 2>&1 && ! command -v grep >/dev/null 2>&1; then
  echo "redaction-scan: grep or rg is required" >&2
  exit 2
fi

# --- rules: id|description|extended-regex (ERE) ---
# Keep secret patterns specific enough that docs saying "tokens" (LLM budget) pass.
RULES=(
  "private_key|PEM/OpenSSH private key header|BEGIN (RSA |OPENSSH |EC |DSA |OPENSSH )?PRIVATE KEY"
  "aws_access_key|AWS access key id|AKIA[0-9A-Z]{16}"
  "github_token|GitHub personal/access token|gh[pousr]_[A-Za-z0-9]{20,}"
  "slack_token|Slack API token|xox[baprs]-[A-Za-z0-9-]{10,}"
  "openai_sk|OpenAI-style secret key|sk-[A-Za-z0-9]{20,}"
  "anthropic_key|Anthropic-style key|sk-ant-[A-Za-z0-9_-]{20,}"
  "bearer_token|Bearer credential literal|Bearer [A-Za-z0-9._\\-]{24,}"
  "assignment_secret|Hardcoded secret assignment|(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)\\s*[=:]\\s*['\\\"][^'\\\"\\s]{8,}['\\\"]"
  "dotenv_export|Exported env secret|(?i)export\\s+(API_KEY|SECRET_KEY|ACCESS_TOKEN|PASSWORD|AWS_SECRET_ACCESS_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY)\\s*="
  "home_path|Absolute home path /Users/<name>|/Users/[A-Za-z0-9._-]+"
  "internal_ip|Private RFC1918 IP|\\b(10\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}|192\\.168\\.[0-9]{1,3}\\.[0-9]{1,3}|172\\.(1[6-9]|2[0-9]|3[0-1])\\.[0-9]{1,3}\\.[0-9]{1,3})\\b"
  "jira_hf|Internal Jira ticket HF-*|\\bHF-[0-9]{2,}\\b"
  "slack_url|Slack workspace/archive URL|https?://[A-Za-z0-9._-]*slack\\.com/"
  "internal_host|Internal/corp hostname|\\b[A-Za-z0-9._-]+\\.(internal|corp|local)\\b"
)

# Values that look like placeholders / docs — never fail these lines.
# Matched as case-insensitive substrings of the whole line.
# Organization-specific identifiers are not hardcoded here: this repository is public,
# so committing real company or personal names to the scanner would leak what it protects.
# Supply them per checkout via REDACTION_EXTRA_PATTERNS (newline-separated
# "id|description|regex" entries) and keep that file outside version control.
EXTRA_RULE_COUNT=0
if [[ -n "${REDACTION_EXTRA_PATTERNS:-}" && -f "${REDACTION_EXTRA_PATTERNS}" ]]; then
  while IFS= read -r extra_rule; do
    [[ -z "${extra_rule}" || "${extra_rule}" == \#* ]] && continue
    RULES+=("${extra_rule}")
    EXTRA_RULE_COUNT=$((EXTRA_RULE_COUNT + 1))
  done < "${REDACTION_EXTRA_PATTERNS}"
fi

# A green scan must not imply coverage it does not have: say so when the
# organization-specific rules were never loaded.
if [[ "${EXTRA_RULE_COUNT}" -eq 0 ]]; then
  echo "redaction-scan: WARNING — organization-specific rules not loaded (REDACTION_EXTRA_PATTERNS unset or empty); this scan covers generic patterns only" >&2
  if [[ "${REQUIRE_EXTRA}" == "1" ]]; then
    echo "redaction-scan: FAIL — --require-extra set and no organization-specific rules were loaded" >&2
    exit 2
  fi
fi

PLACEHOLDER_HINTS=(
  "example.com"
  "example-product"
  "your_api_key"
  "your-api-key"
  "changeme"
  "placeholder"
  "redacted"
  "xxx"
  "todo"
  "insert_"
  "replace_me"
  "dummy"
  "fake_"
  "test_secret"
  "sk-test-"
  "sk-ant-api03-test"
  "ghp_example"
  "xoxb-example"
  "AKIAIOSFODNN7EXAMPLE"
  "not-a-real"
  "sample only"
)

# Synthetic path prefixes intentionally used as fixtures (still reported under allowlist PREFIX:).
DEFAULT_SYNTHETIC_PREFIXES=(
  "/Users/dev/"
  "/Users/user/"
  "/Users/example/"
  "/Users/runner/"
  "/Users/you/"
  "/home/dev/"
  "/home/user/"
)

declare -a ALLOW_PATHS=()
declare -a ALLOW_PATH_LINES=()
declare -a ALLOW_PREFIXES=()
declare -a ALLOW_RULES=()

load_allowlist() {
  ALLOW_PREFIXES=("${DEFAULT_SYNTHETIC_PREFIXES[@]}")
  [[ -f "${ALLOWLIST_FILE}" ]] || return 0
  while IFS= read -r raw || [[ -n "${raw}" ]]; do
    local line
    line="$(printf '%s' "${raw}" | sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "${line}" ]] && continue
    case "${line}" in
      PREFIX:*)
        ALLOW_PREFIXES+=("${line#PREFIX:}")
        ;;
      RULE:*)
        ALLOW_RULES+=("${line#RULE:}")
        ;;
      *:*)
        # path:LINE
        ALLOW_PATH_LINES+=("${line}")
        ;;
      *)
        ALLOW_PATHS+=("${line}")
        ;;
    esac
  done < "${ALLOWLIST_FILE}"
}

rule_allowed() {
  local rule_id="$1"
  local r
  for r in "${ALLOW_RULES[@]+"${ALLOW_RULES[@]}"}"; do
    [[ "${r}" == "${rule_id}" ]] && return 0
  done
  return 1
}

path_allowed() {
  local path="$1"
  local p
  for p in "${ALLOW_PATHS[@]+"${ALLOW_PATHS[@]}"}"; do
    [[ "${p}" == "${path}" ]] && return 0
  done
  return 1
}

path_line_allowed() {
  local key="$1"
  local p
  for p in "${ALLOW_PATH_LINES[@]+"${ALLOW_PATH_LINES[@]}"}"; do
    [[ "${p}" == "${key}" ]] && return 0
  done
  return 1
}

line_is_placeholder() {
  local text_lc
  text_lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  local h
  for h in "${PLACEHOLDER_HINTS[@]}"; do
    local hl
    hl="$(printf '%s' "${h}" | tr '[:upper:]' '[:lower:]')"
    [[ "${text_lc}" == *"${hl}"* ]] && return 0
  done
  return 1
}

line_has_allowed_prefix() {
  local text="$1"
  local pref
  for pref in "${ALLOW_PREFIXES[@]+"${ALLOW_PREFIXES[@]}"}"; do
    # home_path rule: if the only /Users hits are synthetic prefixes, skip.
    if [[ "${text}" == *"${pref}"* ]]; then
      # If text also contains another /Users/<other> not covered by prefixes, still fail later.
      return 0
    fi
  done
  return 1
}

# For home_path: true if every /Users/<name> occurrence is under an allowed prefix.
home_path_only_synthetic() {
  local text="$1"
  # Extract /Users/name occurrences
  local matches
  matches="$(printf '%s\n' "${text}" | grep -oE '/Users/[A-Za-z0-9._-]+' || true)"
  [[ -z "${matches}" ]] && return 1
  local m
  while IFS= read -r m; do
    [[ -z "${m}" ]] && continue
    local ok=0
    local pref
    for pref in "${ALLOW_PREFIXES[@]+"${ALLOW_PREFIXES[@]}"}"; do
      # pref is like /Users/dev/ — match path start /Users/dev
      local base="${pref%/}"
      if [[ "${m}" == "${base}" || "${text}" == *"${pref}"* ]]; then
        # Check this specific match is under base
        case "${m}" in
          "${base}"|"${base}"/*) ok=1; break ;;
        esac
        # /Users/dev matches /Users/dev/...
        if [[ "${m}" == "${base}"* ]]; then
          ok=1
          break
        fi
      fi
    done
    if [[ "${ok}" -eq 0 ]]; then
      return 1
    fi
  done <<< "${matches}"
  return 0
}

list_scan_files() {
  case "${MODE}" in
    tracked)
      git ls-files -z
      ;;
    staged)
      git diff --cached --name-only -z --diff-filter=ACMR
      ;;
    range)
      git diff --name-only -z --diff-filter=ACMR "${RANGE}"
      ;;
  esac
}

COMMIT_MESSAGES_SCANNED="not-scanned"

scan_commit_messages() {
  # Commit messages are content this repository publishes and the file scan never
  # sees them. An internal workspace name sat in four of them here while the gate
  # stayed green, and a person found it by eye.
  local range="$1"
  local count=0 sha tmp
  while IFS= read -r sha; do
    [[ -z "${sha}" ]] && continue
    tmp="$(mktemp)"
    git log -1 --format=%B "${sha}" > "${tmp}" 2>/dev/null || true
    scan_file "${tmp}" "commit:${sha:0:12}"
    rm -f "${tmp}"
    count=$((count + 1))
  done < <(git log --format=%H "${range}" 2>/dev/null || true)
  COMMIT_MESSAGES_SCANNED="${count}"
}

is_binary_or_skip() {
  local path="$1"
  case "${path}" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.pdf|*.zip|*.gz|*.tgz|*.whl|*.so|*.dylib|*.o|*.a|*.pyc|*.db|*.sqlite)
      return 0
      ;;
  esac
  # skip the scanner / allowlist / result reports themselves if present
  case "${path}" in
    scripts/redaction-scan.sh|scripts/redaction-allowlist.txt|mogui-redact-result.md|mogui-redaction-result.md)
      return 0
      ;;
  esac
  return 1
}

FINDINGS=0
declare -a FINDING_LINES=()

record_finding() {
  local rule_id="$1"
  local desc="$2"
  local path="$3"
  local line_no="$4"
  local snippet="$5"
  # Mask: keep structure, strip long secret-looking runs
  local masked
  masked="$(printf '%s' "${snippet}" \
    | sed -E \
      -e 's/(AKIA)[0-9A-Z]{16}/\1****************/g' \
      -e 's/(gh[pousr]_)[A-Za-z0-9]{8,}/\1********/g' \
      -e 's/(xox[baprs]-)[A-Za-z0-9-]{8,}/\1********/g' \
      -e 's/(sk-ant-)[A-Za-z0-9_-]{8,}/\1********/g' \
      -e 's/(sk-)[A-Za-z0-9]{8,}/\1********/g' \
      -e 's/(Bearer )[A-Za-z0-9._-]{8,}/\1********/g' \
      -e 's/(=[[:space:]]*["'"'"'])[^"'"'"']{8,}(["'"'"'])/\1***\2/g' \
    | cut -c1-160)"
  FINDING_LINES+=("${path}:${line_no}  [${rule_id}] ${desc}  :: ${masked}")
  FINDINGS=$((FINDINGS + 1))
}

scan_file() {
  # $1 is the file to read, $2 is what findings are reported as. They differ when
  # the text did not come from a tracked file, such as a commit message.
  local path="$1"
  local label="${2:-$1}"
  [[ -f "${path}" ]] || return 0
  is_binary_or_skip "${label}" && return 0
  path_allowed "${label}" && return 0

  local rule
  for rule in "${RULES[@]}"; do
    IFS='|' read -r rule_id desc regex <<< "${rule}"
    rule_allowed "${rule_id}" && continue

    # Prefer rg for PCRE (?i); fall back to grep -E (drop unsupported lookarounds lightly).
    local matches=""
    if command -v rg >/dev/null 2>&1; then
      # rg: path with line numbers; PCRE2 for lookaround rules
      matches="$(rg -n --pcre2 -e "${regex}" -- "${path}" 2>/dev/null || true)"
    else
      local gre_regex="${regex}"
      # strip perl-ish (?i) and lookarounds for basic grep -E
      gre_regex="$(printf '%s' "${gre_regex}" | sed -E 's/\(\?i\)//g; s/\(\?<![^)]*\)//g; s/\(\?![^)]*\)//g')"
      matches="$(grep -n -E -e "${gre_regex}" -- "${path}" 2>/dev/null || true)"
    fi
    [[ -z "${matches}" ]] && continue

    while IFS= read -r hit; do
      [[ -z "${hit}" ]] && continue
      local line_no="${hit%%:*}"
      local text="${hit#*:}"
      # Some greps include path:line:text when multi-file; we scan single file.
      if [[ "${text}" == *:* ]] && [[ "${line_no}" == "${path}" ]]; then
        # path:line:text form
        local rest="${hit#*:}"
        line_no="${rest%%:*}"
        text="${rest#*:}"
      fi

      path_line_allowed "${label}:${line_no}" && continue
      line_is_placeholder "${text}" && continue

      if [[ "${rule_id}" == "home_path" ]]; then
        if home_path_only_synthetic "${text}"; then
          continue
        fi
        # also skip if line only mentions allowed prefixes
        if line_has_allowed_prefix "${text}" && home_path_only_synthetic "${text}"; then
          continue
        fi
      fi

      record_finding "${rule_id}" "${desc}" "${label}" "${line_no}" "${text}"
    done <<< "${matches}"
  done
}

main() {
  load_allowlist

  if [[ -z "${COMMIT_RANGE:-}" && "${MODE}" == "range" ]]; then
    COMMIT_RANGE="${RANGE}"
  fi
  if [[ -n "${COMMIT_RANGE:-}" ]]; then
    scan_commit_messages "${COMMIT_RANGE}"
  fi

  local file_count=0
  while IFS= read -r -d '' path; do
    [[ -z "${path}" ]] && continue
    file_count=$((file_count + 1))
    scan_file "${path}"
  done < <(list_scan_files)

  if [[ "${VERBOSE}" -eq 1 ]]; then
    echo "redaction-scan: mode=${MODE} range=${RANGE:-none} files=${file_count} commit-messages=${COMMIT_MESSAGES_SCANNED} allowlist=${ALLOWLIST_FILE}"
  fi

  if [[ "${FINDINGS}" -gt 0 ]]; then
    echo "redaction-scan: FAIL — ${FINDINGS} finding(s) (fail-closed)" >&2
    local line
    for line in "${FINDING_LINES[@]}"; do
      echo "  ${line}" >&2
    done
    echo "redaction-scan: fix or allowlist (path:line / PREFIX: / RULE:) then re-run." >&2
    exit 1
  fi

  echo "redaction-scan: OK — 0 findings (mode=${MODE}, files=${file_count}, commit-messages=${COMMIT_MESSAGES_SCANNED})"
  exit 0
}

main
