#!/usr/bin/env bash
# Seeded checks for scripts/merge-ready, with every GitHub response stubbed.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERGE_READY="${SCRIPT_DIR}/merge-ready"
if [ ! -x "${MERGE_READY}" ]; then
  echo "FAIL: ${MERGE_READY} is missing or not executable"
  exit 1
fi

F=0
ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

REPO="owner/repo"
HEAD_SHA="0123456789abcdef0123456789abcdef01234567"
HEAD_COMMIT_DATE="2026-01-01T00:00:00Z"
STALE_DATE="2025-01-01T00:00:00Z"
FRESH_DATE="2026-01-02T00:00:00Z"
BACKDATED_COMMENT_DATE="2025-01-02T00:00:00Z"
CHECK_RUN_DATE="2026-01-01T12:00:00Z"
BETWEEN_PUSH_DATE="2026-01-15T00:00:00Z"
LATEST_PUSH_DATE="2026-02-01T00:00:00Z"

INSTALL_DIR="${WORK_DIR}/install"
mkdir -p "${INSTALL_DIR}/scripts/lib" "${INSTALL_DIR}/config"
cp "${MERGE_READY}" "${INSTALL_DIR}/scripts/merge-ready"
cp "${SCRIPT_DIR}/lib/merge_ready.py" "${INSTALL_DIR}/scripts/lib/merge_ready.py"
chmod +x "${INSTALL_DIR}/scripts/merge-ready"
MERGE_READY="${INSTALL_DIR}/scripts/merge-ready"
cp "${SCRIPT_DIR}/../config/merge-ready-stop-paths.txt" "${INSTALL_DIR}/config/merge-ready-stop-paths.txt"
cat >"${INSTALL_DIR}/config/merge-ready-bots.txt" <<'EOF'
cubic-dev-ai | none | none
coderabbitai | <!-- This is an auto-generated comment: rate limited by coderabbit.ai --> | > ## Review limit reached
EOF

STUB_DIR="${WORK_DIR}/stub"
mkdir -p "${STUB_DIR}"
cat >"${STUB_DIR}/gh" <<'EOF'
#!/usr/bin/env bash
set -u
case "$1" in
  pr)
    case "${2:-}" in
      view)
        if [ "${GH_STUB_CASE:-}" = "pr-fail" ]; then
          echo "gh: pull request unavailable" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "pr-bad-json" ]; then
          echo "not json"
        elif [ "${GH_STUB_CASE:-}" = "head-changed" ]; then
          if [ -e "${GH_FIXTURE_DIR}/pr-view-count" ]; then
            cat "${GH_FIXTURE_DIR}/pr-changed.json"
          else
            : >"${GH_FIXTURE_DIR}/pr-view-count"
            cat "${GH_FIXTURE_DIR}/pr.json"
          fi
        elif [ "${GH_STUB_CASE:-}" = "base-changed" ]; then
          if [ ! -e "${GH_FIXTURE_DIR}/pr-view-count" ]; then
            : >"${GH_FIXTURE_DIR}/pr-view-count"
            cat "${GH_FIXTURE_DIR}/pr.json"
          elif [ ! -e "${GH_FIXTURE_DIR}/pr-view-final-count" ]; then
            : >"${GH_FIXTURE_DIR}/pr-view-final-count"
            cat "${GH_FIXTURE_DIR}/pr.json"
          else
            cat "${GH_FIXTURE_DIR}/pr-base-changed.json"
          fi
        else
          cat "${GH_FIXTURE_DIR}/pr.json"
        fi
        ;;
      checks)
        if [ "${GH_STUB_CASE:-}" = "checks-fail" ]; then
          echo "gh: checks unavailable" >&2
          exit 1
        fi
        required_only="$(python3 -I -c "import json; d=json.load(open('${GH_FIXTURE_DIR}/checks.json')); print(json.dumps([c for c in d if c.get('required', True)]))")"
        printf '%s' "${required_only}"
        python3 -I -c "import json, sys; sys.exit(0 if all(c.get('bucket') == 'pass' for c in json.loads('''${required_only}''')) else 1)"
        ;;
      *)
        echo "gh stub: unhandled pr command: $*" >&2
        exit 1
        ;;
    esac
    ;;
  api)
    if [ "${GH_STUB_CASE:-}" = "encoded-base" ]; then
      printf '%s\n' "${2:-}" >>"${GH_FIXTURE_DIR}/api-paths.log"
    fi
    case "${2:-}" in
      graphql)
        if [ "${GH_STUB_CASE:-}" = "graphql-fail" ]; then
          echo "gh: graphql unavailable" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "graphql-bad-json" ]; then
          echo "not json"
        elif [ "${GH_STUB_CASE:-}" = "graphql-paginated" ] || [ "${GH_STUB_CASE:-}" = "graphql-malformed-second" ]; then
          if printf '%s' "$*" | grep -q 'reviewThreads'; then
            if [ ! -e "${GH_FIXTURE_DIR}/thread-page-count" ]; then
              : >"${GH_FIXTURE_DIR}/thread-page-count"
              cat "${GH_FIXTURE_DIR}/thread-page-1.json"
            else
              cat "${GH_FIXTURE_DIR}/thread-page-2.json"
            fi
          elif printf '%s' "$*" | grep -q 'reviews'; then
            if [ ! -e "${GH_FIXTURE_DIR}/review-page-count" ]; then
              : >"${GH_FIXTURE_DIR}/review-page-count"
              cat "${GH_FIXTURE_DIR}/review-page-1.json"
            elif [ "${GH_STUB_CASE:-}" = "graphql-malformed-second" ]; then
              cat "${GH_FIXTURE_DIR}/review-page-2-malformed.json"
            else
              cat "${GH_FIXTURE_DIR}/review-page-2.json"
            fi
          else
            echo "gh stub: graphql query did not name a connection" >&2
            exit 1
          fi
        else
          cat "${GH_FIXTURE_DIR}/graphql.json"
        fi
        ;;
      repos/*/rules/branches/*)
        if [ "${GH_STUB_CASE:-}" = "rules-fail" ]; then
          echo "gh: rules unavailable" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "rules-403-legacy" ] || [ "${GH_STUB_CASE:-}" = "rules-403-branch" ] || [ "${GH_STUB_CASE:-}" = "rules-403-no-source" ]; then
          echo "gh: Upgrade to GitHub Pro or make this repository public (HTTP 403)" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "rules-403-rate-limit" ]; then
          echo "gh: API rate limit exceeded (HTTP 403)" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "rules-paginated" ]; then
          cat "${GH_FIXTURE_DIR}/rules-pages.json"
        else
          python3 -I -c "import json; print(json.dumps([json.load(open('${GH_FIXTURE_DIR}/rules.json'))]))"
        fi
        ;;
      repos/*/branches/*/protection/required_status_checks)
        if [ "${GH_STUB_CASE:-}" = "legacy-fail" ] || [ "${GH_STUB_CASE:-}" = "legacy-permission" ] || [ "${GH_STUB_CASE:-}" = "rules-403-branch" ] || [ "${GH_STUB_CASE:-}" = "rules-403-no-source" ]; then
          echo "gh: legacy protection unavailable" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "legacy-404" ]; then
          echo "gh: Branch not protected (HTTP 404)" >&2
          printf '%s' '{"message":"Branch not protected","status":"404"}'
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/legacy.json"
        ;;
      repos/*/branches/*)
        if [ "${GH_STUB_CASE:-}" = "legacy-fail" ] || [ "${GH_STUB_CASE:-}" = "rules-403-no-source" ]; then
          echo "gh: branch details unavailable" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/branch.json"
        ;;
      repos/*/pulls/*/files)
        cat "${GH_FIXTURE_DIR}/files.json"
        ;;
      repos/*/issues/*/comments)
        cat "${GH_FIXTURE_DIR}/comments.json"
        ;;
      repos/*/issues/*/timeline)
        cat "${GH_FIXTURE_DIR}/timeline.json"
        ;;
      repos/*/commits/*/check-runs)
        if [ "${GH_STUB_CASE:-}" = "check-runs-fail" ]; then
          echo "gh: check runs unavailable" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/check-runs.json"
        ;;
      repos/*/commits/*/check-suites)
        cat "${GH_FIXTURE_DIR}/check-suites.json"
        ;;
      repos/*/commits/*)
        cat "${GH_FIXTURE_DIR}/commit-date.txt"
        ;;
      *)
        echo "gh stub: unhandled API endpoint: ${2:-}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "gh stub: unhandled command: $*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "${STUB_DIR}/gh"
export PATH="${STUB_DIR}:${PATH}"

DEFAULT_CHECKS='[{"name":"ci","bucket":"pass","state":"SUCCESS"}]'
FAILING_CHECK='[{"name":"ci","bucket":"fail","state":"FAILURE"}]'
DEFAULT_RULES='[{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"ci"}]}}]'
DEFAULT_LEGACY='{"contexts":[],"checks":[]}'
DEFAULT_REVIEWS='[{"state":"COMMENTED","body":"Automated review","comments":{"nodes":[],"pageInfo":{"hasNextPage":false}},"commit":{"oid":"HEAD_SHA_PLACEHOLDER"},"author":{"login":"coderabbitai","__typename":"Bot"}},{"state":"COMMENTED","body":"Automated review","comments":{"nodes":[],"pageInfo":{"hasNextPage":false}},"commit":{"oid":"HEAD_SHA_PLACEHOLDER"},"author":{"login":"cubic-dev-ai","__typename":"Bot"}}]'
DEFAULT_REVIEWS="${DEFAULT_REVIEWS//HEAD_SHA_PLACEHOLDER/${HEAD_SHA}}"
CUBIC_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
PAGINATED_BLOCKING_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"CHANGES_REQUESTED\",\"body\":\"\",\"comments\":{\"nodes\":[{\"databaseId\":3,\"replyTo\":null}],\"pageInfo\":{\"hasNextPage\":true}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}}]"
UNPAGED_COMMENT_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"\",\"comments\":{\"nodes\":[{\"databaseId\":4,\"replyTo\":{\"databaseId\":5}}],\"pageInfo\":{\"hasNextPage\":true}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
THREAD_REPLY_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"\",\"comments\":{\"nodes\":[{\"databaseId\":1,\"replyTo\":{\"databaseId\":2}}],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
DISMISSED_REVIEW="[{\"state\":\"DISMISSED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
MALFORMED_PAGEINFO_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"\",\"comments\":{\"nodes\":[]},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
NONBOOLEAN_PAGEINFO_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":\"false\"}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
MALFORMED_REVIEW_STATE="[{\"state\":\"UNKNOWN\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"
MISSING_REPLYTO_REVIEW="[{\"state\":\"COMMENTED\",\"body\":\"\",\"comments\":{\"nodes\":[{\"databaseId\":8}],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"coderabbitai\",\"__typename\":\"Bot\"}},{\"state\":\"COMMENTED\",\"body\":\"Automated review\",\"comments\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false}},\"commit\":{\"oid\":\"${HEAD_SHA}\"},\"author\":{\"login\":\"cubic-dev-ai\",\"__typename\":\"Bot\"}}]"

NON_HEAD_REVIEW='[{"state":"COMMENTED","commit":{"oid":"1111111111111111111111111111111111111111"},"author":{"login":"coderabbitai","__typename":"Bot"}}]'

write_fixture() {
  local dir="$1" files_json="$2" _unused_comment="$3" checks_json="${4:-${DEFAULT_CHECKS}}"
  local reviews_json="${5:-${DEFAULT_REVIEWS}}" open_threads="${6:-0}"
  local state="${7:-OPEN}" is_draft="${8:-false}" extra_comments="${9:-[]}"
  local rules_json="${10:-${DEFAULT_RULES}}" legacy_json="${11:-${DEFAULT_LEGACY}}"
  local base_branch="${12:-main}"
  mkdir -p "${dir}"
  python3 - "${dir}/pr.json" "${state}" "${is_draft}" "${base_branch}" <<'PY'
import json, sys
path, state, is_draft, base_branch = sys.argv[1:]
json.dump({"number": 1, "url": "https://example.invalid/pr/1", "headRefOid": "0123456789abcdef0123456789abcdef01234567", "baseRefName": base_branch, "state": state, "isDraft": is_draft == "true"}, open(path, "w", encoding="utf-8"))
PY
  python3 - "${dir}/pr-changed.json" <<'PY'
import json, sys
json.dump({"number": 1, "url": "https://example.invalid/pr/1", "headRefOid": "ffffffffffffffffffffffffffffffffffffffff", "baseRefName": "main", "state": "OPEN", "isDraft": False}, open(sys.argv[1], "w", encoding="utf-8"))
PY
  python3 - "${dir}/pr-base-changed.json" <<'PY'
import json, sys
json.dump({"number": 1, "url": "https://example.invalid/pr/1", "headRefOid": "0123456789abcdef0123456789abcdef01234567", "baseRefName": "release", "state": "OPEN", "isDraft": False}, open(sys.argv[1], "w", encoding="utf-8"))
PY
  printf '%s' "${checks_json}" >"${dir}/checks.json"
  printf '%s' "${rules_json}" >"${dir}/rules.json"
  printf '%s' "${legacy_json}" >"${dir}/legacy.json"
  python3 - "${dir}/branch.json" "${legacy_json}" "${base_branch}" <<'PY'
import json, sys
legacy = json.loads(sys.argv[2])
json.dump({"name": sys.argv[3], "protected": True, "protection": {"required_status_checks": legacy}}, open(sys.argv[1], "w", encoding="utf-8"))
PY
  python3 - "${dir}/graphql.json" "${reviews_json}" "${open_threads}" <<'PY'
import json, sys
path, reviews_raw, open_threads = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = {"data": {"repository": {"pullRequest": {
    "reviewThreads": {"nodes": [{"isResolved": False} for _ in range(open_threads)], "pageInfo": {"hasNextPage": False, "endCursor": None}},
    "reviews": {"nodes": json.loads(reviews_raw), "pageInfo": {"hasNextPage": False, "endCursor": None}},
}}}}
json.dump(data, open(path, "w", encoding="utf-8"))
PY
  python3 - "${dir}/files.json" "${files_json}" <<'PY'
import json, sys
json.dump([json.loads(sys.argv[2])], open(sys.argv[1], "w", encoding="utf-8"))
PY
  python3 - "${dir}/comments.json" "${extra_comments}" <<'PY'
import json, sys
path, extra = sys.argv[1:]
comments = json.loads(extra)
json.dump([comments], open(path, "w", encoding="utf-8"))
PY
  printf '%s' "${HEAD_COMMIT_DATE}" >"${dir}/commit-date.txt"
  printf '%s' '[{"check_runs":[{"name":"ci","created_at":"'"${CHECK_RUN_DATE}"'","check_suite":{"created_at":"'"${CHECK_RUN_DATE}"'"}}]}]' >"${dir}/check-runs.json"
  printf '%s' '[{"check_suites":[{"created_at":"'"${CHECK_RUN_DATE}"'"}]}]' >"${dir}/check-suites.json"
  printf '%s' '[[]]' >"${dir}/timeline.json"
}

run_case() {
  local dir="$1" stub_case="${2:-}"
  GH_FIXTURE_DIR="${dir}" GH_STUB_CASE="${stub_case}" "${MERGE_READY}" --repo "${REPO}" --pr 1
}

run_case_in_worktree() {
  local dir="$1" stub_case="${2:-}"
  (
    cd "${dir}"
    GH_FIXTURE_DIR="${dir}" GH_STUB_CASE="${stub_case}" "${MERGE_READY}" --repo "${REPO}" --pr 1
  )
}

assert_rc() {
  local label="$1" expected="$2" output="$3" actual="$4"
  if [ "${actual}" -eq "${expected}" ]; then
    ok "${label} (${output})"
  else
    fail "${label}: got ${actual}, want ${expected}: ${output}"
  fi
}

clean_dir="${WORK_DIR}/clean"
write_fixture "${clean_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${clean_dir}"); rc=$?
assert_rc "clean PR exits 0" 0 "${out}" "${rc}"

isolation_dir="${WORK_DIR}/python-isolation"
write_fixture "${isolation_dir}" '[{"filename":"README.md"}]' ""
cat >"${isolation_dir}/json.py" <<'PY'
from pathlib import Path

Path("json-imported.marker").write_text("imported", encoding="utf-8")
raise RuntimeError("pull-request json.py was imported")
PY
out=$(run_case_in_worktree "${isolation_dir}"); rc=$?
if [ -e "${isolation_dir}/json-imported.marker" ]; then
  isolation_marker="present"
else
  isolation_marker="absent"
fi
if [ "${rc}" -eq 0 ] && [ "${isolation_marker}" = "absent" ]; then
  ok "python invocations use -I and ignore a worktree json.py (marker ${isolation_marker})"
else
  fail "python isolation: got ${rc}, marker ${isolation_marker}: ${out}"
fi

legacy_checks_dir="${WORK_DIR}/legacy-checks"
write_fixture "${legacy_checks_dir}" '[{"filename":"README.md"}]' ""
printf '%s' '[]' >"${legacy_checks_dir}/check-runs.json"
printf '%s' '[]' >"${legacy_checks_dir}/check-suites.json"
printf '%s' '[[]]' >"${legacy_checks_dir}/timeline.json"
out=$(run_case "${legacy_checks_dir}"); rc=$?
assert_rc "legacy checks with completed bot reviews do not need a timestamp" 0 "${out}" "${rc}"

missing_timestamp_dir="${WORK_DIR}/missing-timestamp"
rate_limit_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${missing_timestamp_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[]' >"${missing_timestamp_dir}/check-runs.json"
printf '%s' '[]' >"${missing_timestamp_dir}/check-suites.json"
printf '%s' '[[]]' >"${missing_timestamp_dir}/timeline.json"
out=$(run_case "${missing_timestamp_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'trusted head push time' && ! printf '%s' "${out}" | grep -q 'Traceback'; then
  ok "a missing trusted timestamp blocks the rate-limit exemption with one clean message"
else
  fail "missing trusted timestamp: got ${rc}: ${out}"
fi

ordinary_push_no_timestamp_dir="${WORK_DIR}/ordinary-push-no-timestamp"
write_fixture "${ordinary_push_no_timestamp_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[[{"event":"committed","sha":"'"${HEAD_SHA}"'"}]]' >"${ordinary_push_no_timestamp_dir}/timeline.json"
out=$(run_case "${ordinary_push_no_timestamp_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'trusted head push time'; then
  ok "an ordinary push without a server timestamp leaves the rate-limit exemption unavailable"
else
  fail "ordinary push without server timestamp: got ${rc}: ${out}"
fi

paginated_blocking_review_dir="${WORK_DIR}/paginated-blocking-review"
write_fixture "${paginated_blocking_review_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${PAGINATED_BLOCKING_REVIEW}"
out=$(run_case "${paginated_blocking_review_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'review bots: coderabbitai=changes_requested'; then
  ok "a current blocking review with a top-level first-page comment remains blocking when more comments exist"
else
  fail "paginated blocking review: got ${rc}: ${out}"
fi

unpaged_comment_review_dir="${WORK_DIR}/unpaged-comment-review"
write_fixture "${unpaged_comment_review_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${UNPAGED_COMMENT_REVIEW}"
out=$(run_case "${unpaged_comment_review_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'could not determine whether a rate-limit exemption needs a timestamp'; then
  ok "a review without a first-page top-level comment does not silently pass while more pages remain"
else
  fail "unpaged review comments: got ${rc}: ${out}"
fi

thread_reply_review_dir="${WORK_DIR}/thread-reply-review"
write_fixture "${thread_reply_review_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${THREAD_REPLY_REVIEW}"
out=$(run_case "${thread_reply_review_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a head review made only of thread replies does not cover the bot"
else
  fail "thread-reply-only review: got ${rc}: ${out}"
fi

dismissed_review_dir="${WORK_DIR}/dismissed-review"
write_fixture "${dismissed_review_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DISMISSED_REVIEW}"
out=$(run_case "${dismissed_review_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a dismissed head review does not cover the bot"
else
  fail "dismissed review: got ${rc}: ${out}"
fi

updated_notice_dir="${WORK_DIR}/updated-notice"
updated_notice_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${STALE_DATE}"'","updated_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${updated_notice_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${updated_notice_comment}"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${FRESH_DATE}"'"}]]' >"${updated_notice_dir}/timeline.json"
out=$(run_case "${updated_notice_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "an edited old rate-limit notice uses created_at and does not qualify"
else
  fail "updated rate-limit notice: got ${rc}: ${out}"
fi

latest_push_dir="${WORK_DIR}/latest-push"
latest_push_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${BETWEEN_PUSH_DATE}"'"}]'
write_fixture "${latest_push_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${latest_push_comment}"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${HEAD_COMMIT_DATE}"'"}],[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${LATEST_PUSH_DATE}"'"}]]' >"${latest_push_dir}/timeline.json"
out=$(run_case "${latest_push_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "the latest qualifying head push bounds a rate-limit exemption"
else
  fail "latest qualifying head push: got ${rc}: ${out}"
fi

malformed_created_at_dir="${WORK_DIR}/malformed-created-at"
malformed_created_at_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"not-a-timestamp"}]'
write_fixture "${malformed_created_at_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${malformed_created_at_comment}"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${FRESH_DATE}"'"}]]' >"${malformed_created_at_dir}/timeline.json"
out=$(run_case "${malformed_created_at_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'created_at is malformed'; then
  ok "an unparseable rate-limit created_at blocks the exemption"
else
  fail "malformed rate-limit created_at: got ${rc}: ${out}"
fi

head_changed_dir="${WORK_DIR}/head-changed"
write_fixture "${head_changed_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${head_changed_dir}" head-changed); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'head changed during changed-file measurement'; then
  ok "a PR head change during measurement exits 1"
else
  fail "head changed during measurement: got ${rc}: ${out}"
fi

base_changed_dir="${WORK_DIR}/base-changed"
write_fixture "${base_changed_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${base_changed_dir}" base-changed); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'base branch changed during measurement'; then
  ok "a PR base change during measurement exits 1"
else
  fail "base branch changed during measurement: got ${rc}: ${out}"
fi

complete_files_dir="${WORK_DIR}/complete-files"
write_fixture "${complete_files_dir}" '[{"filename":"README.md"}]' ""
python3 - "${complete_files_dir}/files.json" <<'PY'
import json, sys
first = [{"filename": f"docs/file-{index}.md"} for index in range(300)]
second = [{"filename": "config/gitleaks.toml"}]
json.dump([first, second], open(sys.argv[1], "w", encoding="utf-8"))
PY
out=$(run_case "${complete_files_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'config/gitleaks.toml (stop-list)'; then
  ok "paginated pull-request files include a stop-list path beyond the first 300"
else
  fail "complete paginated files: got ${rc}: ${out}"
fi

complete_files_head_changed_dir="${WORK_DIR}/complete-files-head-changed"
write_fixture "${complete_files_head_changed_dir}" '[{"filename":"README.md"}]' ""
python3 - "${complete_files_head_changed_dir}/files.json" <<'PY'
import json, sys
first = [{"filename": f"docs/file-{index}.md"} for index in range(300)]
second = [{"filename": "README.md"}]
json.dump([first, second], open(sys.argv[1], "w", encoding="utf-8"))
PY
out=$(run_case "${complete_files_head_changed_dir}" head-changed); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'head changed during changed-file measurement'; then
  ok "head movement between file-list reads exits 1"
else
  fail "head movement during file-list read: got ${rc}: ${out}"
fi

malformed_pageinfo_dir="${WORK_DIR}/malformed-pageinfo"
write_fixture "${malformed_pageinfo_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${MALFORMED_PAGEINFO_REVIEW}"
out=$(run_case "${malformed_pageinfo_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'could not determine whether a rate-limit exemption needs a timestamp'; then
  ok "missing nested review-comment pageInfo exits 1"
else
  fail "missing nested review-comment pageInfo: got ${rc}: ${out}"
fi

nonboolean_pageinfo_dir="${WORK_DIR}/nonboolean-pageinfo"
write_fixture "${nonboolean_pageinfo_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${NONBOOLEAN_PAGEINFO_REVIEW}"
out=$(run_case "${nonboolean_pageinfo_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'could not determine whether a rate-limit exemption needs a timestamp'; then
  ok "non-boolean nested review-comment pageInfo exits 1"
else
  fail "non-boolean nested review-comment pageInfo: got ${rc}: ${out}"
fi

malformed_review_state_dir="${WORK_DIR}/malformed-review-state"
write_fixture "${malformed_review_state_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${MALFORMED_REVIEW_STATE}"
out=$(run_case "${malformed_review_state_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'malformed review state'; then
  ok "an unknown review state exits 1"
else
  fail "unknown review state: got ${rc}: ${out}"
fi

missing_replyto_dir="${WORK_DIR}/missing-replyto"
write_fixture "${missing_replyto_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${MISSING_REPLYTO_REVIEW}"
out=$(run_case "${missing_replyto_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'malformed review comment replyTo'; then
  ok "a missing review-comment replyTo field exits 1"
else
  fail "missing review-comment replyTo: got ${rc}: ${out}"
fi

nonboolean_thread_dir="${WORK_DIR}/nonboolean-thread"
write_fixture "${nonboolean_thread_dir}" '[{"filename":"README.md"}]' ""
python3 - "${nonboolean_thread_dir}/graphql.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [{"isResolved": "true"}]
json.dump(data, open(path, "w", encoding="utf-8"))
PY
out=$(run_case "${nonboolean_thread_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'malformed review thread isResolved'; then
  ok "a non-boolean review-thread isResolved value exits 1"
else
  fail "non-boolean review-thread isResolved: got ${rc}: ${out}"
fi

check_run_time_dir="${WORK_DIR}/check-run-time"
write_fixture "${check_run_time_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[{"check_runs":[{"name":"ci","created_at":"'"${FRESH_DATE}"'"}]}]' >"${check_run_time_dir}/check-runs.json"
printf '%s' '[[]]' >"${check_run_time_dir}/timeline.json"
out=$(run_case "${check_run_time_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'trusted head push time'; then
  ok "check-run timestamps cannot qualify a missing head push event"
else
  fail "check-run timestamp bypass: got ${rc}: ${out}"
fi

path_before_timestamp_dir="${WORK_DIR}/path-before-timestamp"
write_fixture "${path_before_timestamp_dir}" '[{"filename":"config/gitleaks.toml"}]' "" "${DEFAULT_CHECKS}" "${NON_HEAD_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[]' >"${path_before_timestamp_dir}/check-runs.json"
printf '%s' '[]' >"${path_before_timestamp_dir}/check-suites.json"
printf '%s' '[[]]' >"${path_before_timestamp_dir}/timeline.json"
out=$(run_case "${path_before_timestamp_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'stop-list'; then
  ok "a stop-list hit exits 2 before timestamp acquisition"
else
  fail "path before timestamp: got ${rc}: ${out}"
fi

rules_failure_ask_dir="${WORK_DIR}/rules-failure-ask"
write_fixture "${rules_failure_ask_dir}" '[{"filename":"config/gitleaks.toml"}]' ""
out=$(run_case "${rules_failure_ask_dir}" rules-fail); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'required check summary unavailable' && printf '%s' "${out}" | grep -q 'required-check rules'; then
  ok "a known stop-list ask survives an unreadable rules response"
else
  fail "rules failure with ask: got ${rc}: ${out}"
fi

rules_403_legacy_dir="${WORK_DIR}/rules-403-legacy"
write_fixture "${rules_403_legacy_dir}" '[{"filename":"README.md"}]' "" '[{"name":"rules-403-legacy-context","bucket":"pass","state":"SUCCESS"}]' "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" '{"contexts":["rules-403-legacy-context"],"checks":[]}'
out=$(run_case "${rules_403_legacy_dir}" rules-403-legacy); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q 'merge-ready: merge' && printf '%s' "${out}" | grep -q 'rules-403-legacy-context'; then
  ok "a plan-limit HTTP 403 with usable legacy checks measures every gate"
else
  fail "plan-limit HTTP 403 with usable legacy checks: got ${rc}: ${out}"
fi

rules_403_branch_dir="${WORK_DIR}/rules-403-branch"
write_fixture "${rules_403_branch_dir}" '[{"filename":"README.md"}]' "" '[{"name":"rules-403-branch-context","bucket":"pass","state":"SUCCESS"}]' "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" '{"contexts":["rules-403-branch-context"],"checks":[]}'
out=$(run_case "${rules_403_branch_dir}" rules-403-branch); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q 'merge-ready: merge' && printf '%s' "${out}" | grep -q 'rules-403-branch-context'; then
  ok "a plan-limit HTTP 403 with usable branch checks measures every gate"
else
  fail "plan-limit HTTP 403 with usable branch checks: got ${rc}: ${out}"
fi

rules_403_legacy_failure_dir="${WORK_DIR}/rules-403-legacy-failure"
write_fixture "${rules_403_legacy_failure_dir}" '[{"filename":"README.md"}]' "" '[{"name":"rules-403-legacy-context","bucket":"fail","state":"FAILURE"}]' "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" '{"contexts":["rules-403-legacy-context"],"checks":[]}'
out=$(run_case "${rules_403_legacy_failure_dir}" rules-403-legacy); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'rules-403-legacy-context=FAILURE'; then
  ok "a plan-limit HTTP 403 with a failing required check exits 1"
else
  fail "plan-limit HTTP 403 with a failing required check: got ${rc}: ${out}"
fi

rules_403_no_source_dir="${WORK_DIR}/rules-403-no-source"
write_fixture "${rules_403_no_source_dir}" '[{"filename":"config/gitleaks.toml"}]' ""
out=$(run_case "${rules_403_no_source_dir}" rules-403-no-source); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'HTTP 403' && printf '%s' "${out}" | grep -q 'legacy branch protection' && printf '%s' "${out}" | grep -q 'config/gitleaks.toml (stop-list)'; then
  ok "a rules HTTP 403 with no fallback source preserves the stop-list ask"
else
  fail "rules HTTP 403 without fallback: got ${rc}: ${out}"
fi

rules_403_empty_source_dir="${WORK_DIR}/rules-403-empty-source"
write_fixture "${rules_403_empty_source_dir}" '[{"filename":"config/gitleaks.toml"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" '{"contexts":[],"checks":[]}'
out=$(run_case "${rules_403_empty_source_dir}" rules-403-legacy); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'HTTP 403' && printf '%s' "${out}" | grep -q 'no required checks' && printf '%s' "${out}" | grep -q 'config/gitleaks.toml (stop-list)'; then
  ok "a rules HTTP 403 with an empty legacy source preserves the stop-list ask"
else
  fail "rules HTTP 403 empty fallback source: got ${rc}: ${out}"
fi

rules_403_rate_limit_dir="${WORK_DIR}/rules-403-rate-limit"
write_fixture "${rules_403_rate_limit_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${rules_403_rate_limit_dir}" rules-403-rate-limit); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'required check summary unavailable' && ! printf '%s' "${out}" | grep -q 'owner confirmation required'; then
  ok "a rate-limit HTTP 403 remains exit 1"
else
  fail "rate-limit HTTP 403 classification: got ${rc}: ${out}"
fi

legacy_failure_ask_dir="${WORK_DIR}/legacy-failure-ask"
write_fixture "${legacy_failure_ask_dir}" '[{"filename":"config/gitleaks.toml"}]' ""
out=$(run_case "${legacy_failure_ask_dir}" legacy-fail); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'required check summary unavailable' && printf '%s' "${out}" | grep -q 'legacy required checks'; then
  ok "a known stop-list ask survives an unreadable legacy response"
else
  fail "legacy failure with ask: got ${rc}: ${out}"
fi

encoded_base_dir="${WORK_DIR}/encoded-base"
write_fixture "${encoded_base_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" "${DEFAULT_LEGACY}" "release#1"
out=$(run_case "${encoded_base_dir}" encoded-base); rc=$?
if [ "${rc}" -eq 0 ] && grep -Fq 'repos/owner/repo/rules/branches/release%231' "${encoded_base_dir}/api-paths.log" && grep -Fq 'repos/owner/repo/branches/release%231/protection/required_status_checks' "${encoded_base_dir}/api-paths.log" && ! grep -Fq 'release#1' "${encoded_base_dir}/api-paths.log"; then
  ok "base branch names are percent-encoded in rules and legacy REST paths"
else
  fail "encoded base branch paths: got ${rc}: ${out}; paths=$(cat "${encoded_base_dir}/api-paths.log" 2>/dev/null || true)"
fi

missing_required_dir="${WORK_DIR}/missing-required"
missing_required_rules='[{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"ci"},{"context":"tests (ubuntu-latest)"}]}}]'
missing_required_legacy='{"contexts":["legacy-only"],"checks":[]}'
write_fixture "${missing_required_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${missing_required_rules}" "${missing_required_legacy}"
out=$(run_case "${missing_required_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'missing required checks: legacy-only, tests (ubuntu-latest)'; then
  ok "a required context absent from reported checks exits 1 and names rules and legacy contexts"
else
  fail "missing required context: got ${rc}: ${out}"
fi

rules_paginated_dir="${WORK_DIR}/rules-paginated"
pagination_checks='[{"name":"ci","bucket":"pass","state":"SUCCESS"},{"name":"tests (ubuntu-latest)","bucket":"pass","state":"SUCCESS"}]'
write_fixture "${rules_paginated_dir}" '[{"filename":"README.md"}]' "" "${pagination_checks}"
printf '%s' '[[{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"ci"}]}}],[{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"tests (ubuntu-latest)"}]}}]]' >"${rules_paginated_dir}/rules-pages.json"
out=$(run_case "${rules_paginated_dir}" rules-paginated); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q 'tests (ubuntu-latest)'; then
  ok "paginated required-check rules contribute every page"
else
  fail "paginated required-check rules: got ${rc}: ${out}"
fi

unknown_rule_type_dir="${WORK_DIR}/unknown-rule-type"
write_fixture "${unknown_rule_type_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" '[{"type":"workflows","parameters":{}}]'
out=$(run_case "${unknown_rule_type_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'unsupported ruleset rule type: workflows'; then
  ok "an unknown check-gating ruleset type exits 1 and names workflows"
else
  fail "unknown ruleset type: got ${rc}: ${out}"
fi

graphql_pagination_dir="${WORK_DIR}/graphql-pagination"
write_fixture "${graphql_pagination_dir}" '[{"filename":"README.md"}]' ""
python3 - "${graphql_pagination_dir}" "${HEAD_SHA}" <<'PY'
import json
import sys

root, head_sha = sys.argv[1:]
bot_review = lambda login: {
    "state": "COMMENTED",
    "body": "Automated review",
    "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}},
    "commit": {"oid": head_sha},
    "author": {"login": login, "__typename": "Bot"},
}
reviews = [bot_review("coderabbitai"), bot_review("cubic-dev-ai")]
reviews.extend(
    {
        "state": "COMMENTED",
        "body": "",
        "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        "commit": {"oid": head_sha},
        "author": {"login": f"reviewer-{index}", "__typename": "User"},
    }
    for index in range(98)
)
reviews.append(
    {
        "state": "COMMENTED",
        "body": "",
        "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        "commit": {"oid": head_sha},
        "author": {"login": "reviewer-98", "__typename": "User"},
    }
)
def page(connection, nodes, has_next, cursor):
    return {"data": {"repository": {"pullRequest": {
        connection: {"nodes": nodes, "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}},
    }}}}
json.dump(page("reviews", reviews[:100], True, "reviews-cursor"), open(f"{root}/review-page-1.json", "w", encoding="utf-8"))
json.dump(page("reviews", reviews[100:], False, None), open(f"{root}/review-page-2.json", "w", encoding="utf-8"))
json.dump(page("reviewThreads", [{"isResolved": True} for _ in range(100)], True, "threads-cursor"), open(f"{root}/thread-page-1.json", "w", encoding="utf-8"))
json.dump(page("reviewThreads", [{"isResolved": True}], False, None), open(f"{root}/thread-page-2.json", "w", encoding="utf-8"))
PY
out=$(run_case "${graphql_pagination_dir}" graphql-paginated); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q 'merge-ready: merge'; then
  ok "reviews and review threads paginate beyond 100 nodes"
else
  fail "GraphQL reviews and threads pagination: got ${rc}: ${out}"
fi

graphql_malformed_dir="${WORK_DIR}/graphql-malformed-second"
write_fixture "${graphql_malformed_dir}" '[{"filename":"README.md"}]' ""
python3 - "${graphql_malformed_dir}" "${HEAD_SHA}" <<'PY'
import json
import sys

root, head_sha = sys.argv[1:]
review = {
    "state": "COMMENTED",
    "body": "Automated review",
    "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}},
    "commit": {"oid": head_sha},
    "author": {"login": "coderabbitai", "__typename": "Bot"},
}
page = {"data": {"repository": {"pullRequest": {
    "reviews": {"nodes": [review], "pageInfo": {"hasNextPage": True, "endCursor": "reviews-cursor"}},
}}}}
json.dump(page, open(f"{root}/review-page-1.json", "w", encoding="utf-8"))
json.dump({"data": {"repository": {"pullRequest": {"reviews": {"nodes": [review]}}}}}, open(f"{root}/review-page-2-malformed.json", "w", encoding="utf-8"))
json.dump({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}, open(f"{root}/thread-page-1.json", "w", encoding="utf-8"))
PY
out=$(run_case "${graphql_malformed_dir}" graphql-malformed-second); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'could not parse reviews page 2'; then
  ok "a malformed second GraphQL page exits 1 with the connection name"
else
  fail "malformed second GraphQL page: got ${rc}: ${out}"
fi

rules_fail_dir="${WORK_DIR}/rules-fail"
write_fixture "${rules_fail_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${rules_fail_dir}" rules-fail); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'required-check rules'; then
  ok "an unreadable required-check rules response exits 1"
else
  fail "unreadable required-check rules: got ${rc}: ${out}"
fi

legacy_fail_dir="${WORK_DIR}/legacy-fail"
write_fixture "${legacy_fail_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${legacy_fail_dir}" legacy-fail); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'legacy required checks'; then
  ok "an unreadable legacy required-check response exits 1"
else
  fail "unreadable legacy required checks: got ${rc}: ${out}"
fi

legacy_permission_dir="${WORK_DIR}/legacy-permission"
legacy_permission_checks='[{"name":"ci","bucket":"pass","state":"SUCCESS"},{"name":"legacy-only","bucket":"pass","state":"SUCCESS"}]'
legacy_permission_legacy='{"contexts":["legacy-only"],"checks":[]}'
write_fixture "${legacy_permission_dir}" '[{"filename":"README.md"}]' "" "${legacy_permission_checks}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" "${legacy_permission_legacy}"
out=$(run_case "${legacy_permission_dir}" legacy-permission); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q 'legacy-only'; then
  ok "branch protection data supplies legacy contexts when the protection endpoint is unavailable"
else
  fail "legacy protection fallback: got ${rc}: ${out}"
fi

branch_missing_protection_dir="${WORK_DIR}/branch-missing-protection"
write_fixture "${branch_missing_protection_dir}" '[{"filename":"README.md"}]' "" "${legacy_permission_checks}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" "${legacy_permission_legacy}"
python3 - "${branch_missing_protection_dir}/branch.json" <<'PY'
import json, sys
path = sys.argv[1]
branch = json.load(open(path, encoding="utf-8"))
branch.pop("protection")
json.dump(branch, open(path, "w", encoding="utf-8"))
PY
out=$(run_case "${branch_missing_protection_dir}" legacy-permission); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'missing protection'; then
  ok "missing branch protection fails closed instead of meaning unprotected"
else
  fail "missing branch protection: got ${rc}: ${out}"
fi

branch_missing_status_dir="${WORK_DIR}/branch-missing-required-status"
write_fixture "${branch_missing_status_dir}" '[{"filename":"README.md"}]' "" "${legacy_permission_checks}" "${DEFAULT_REVIEWS}" 0 OPEN false "[]" "${DEFAULT_RULES}" "${legacy_permission_legacy}"
python3 - "${branch_missing_status_dir}/branch.json" <<'PY'
import json, sys
path = sys.argv[1]
branch = json.load(open(path, encoding="utf-8"))
branch["protection"].pop("required_status_checks")
json.dump(branch, open(path, "w", encoding="utf-8"))
PY
out=$(run_case "${branch_missing_status_dir}" legacy-permission); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'missing required_status_checks'; then
  ok "missing branch required status checks fail closed instead of meaning unprotected"
else
  fail "missing branch required status checks: got ${rc}: ${out}"
fi

malformed_contract_dir="${WORK_DIR}/malformed-contract"
mkdir -p "${malformed_contract_dir}"
printf '%s\n' '[{"filename":"config/gitleaks.toml"}]' >"${malformed_contract_dir}/files.json"
printf '%s\n' '---' 'title: malformed' '---' >"${malformed_contract_dir}/contract.md"
out=$(python3 -I "${SCRIPT_DIR}/lib/merge_ready.py" path-verdict \
  --files "${malformed_contract_dir}/files.json" \
  --stop-paths "${INSTALL_DIR}/config/merge-ready-stop-paths.txt" \
  --contract "${malformed_contract_dir}/contract.md" 2>&1); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'stop-list' && printf '%s' "${out}" | grep -q 'no writes'; then
  ok "a malformed contract preserves a simultaneous stop-list ask"
else
  fail "malformed contract with stop-list ask: got ${rc}: ${out}"
fi

legacy_404_dir="${WORK_DIR}/legacy-404"
write_fixture "${legacy_404_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${legacy_404_dir}" legacy-404); rc=$?
assert_rc "unprotected legacy status-check endpoint contributes no contexts" 0 "${out}" "${rc}"

stop_paths_config="${INSTALL_DIR}/config/merge-ready-stop-paths.txt"
stop_paths_backup="${WORK_DIR}/merge-ready-stop-paths.txt.valid"
mv "${stop_paths_config}" "${stop_paths_backup}"
out=$(run_case "${clean_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'config/merge-ready-stop-paths.txt is missing' && printf '%s' "${out}" | grep -q 'copy it from the template'; then
  ok "missing stop-list config asks for the copy with exit 2"
else
  fail "missing stop-list config: got ${rc}: ${out}"
fi
mv "${stop_paths_backup}" "${stop_paths_config}"

bots_config="${INSTALL_DIR}/config/merge-ready-bots.txt"
bots_backup="${WORK_DIR}/merge-ready-bots.txt.valid"
mv "${bots_config}" "${bots_backup}"
out=$(run_case "${clean_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'config/merge-ready-bots.txt is missing' && printf '%s' "${out}" | grep -q 'copy it from the template'; then
  ok "missing roster config asks for the copy with exit 2"
else
  fail "missing roster file: got ${rc}: ${out}"
fi
: >"${bots_config}"
out=$(run_case "${clean_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'bots file has no entries'; then
  ok "empty roster file exits 1 and fails closed"
else
  fail "empty roster file: got ${rc}: ${out}"
fi
mv "${bots_backup}" "${bots_config}"

run_upgrade_apply() {
  local ops="$1" json_out="$2" err_out="$3"
  python3 -I "${SCRIPT_DIR}/template-apply" \
    --ops "${ops}" --template "${SCRIPT_DIR}/.." --write --confirm-input apply --json \
    --placeholder WORKSPACE_NAME=seed-test \
    --placeholder WORKSPACE_ROOT="${WORK_DIR}/workspace" \
    --placeholder OPS_REPO="${ops}" \
    --placeholder MONITOR_NS=seed-test \
    --placeholder MODEL_ID=seed-test \
    --placeholder REPO_LIST=seed-test \
    --placeholder RUNTIME_ROOT="${WORK_DIR}/runtime" \
    >"${json_out}" 2>"${err_out}"
}

assert_upgrade_seed_case() {
  local label="$1" ops="$2" expected_stop="$3" expected_bots="$4"
  local expected_stop_action="$5" expected_bots_action="$6" json_out="${ops}.json" err_out="${ops}.err"
  mkdir -p "${ops}/config"
  if [ "${expected_stop_action}" = "skipped-as-instance-owned" ]; then
    printf '%s\n' "${expected_stop}" >"${ops}/config/merge-ready-stop-paths.txt"
  fi
  if [ "${expected_bots_action}" = "skipped-as-instance-owned" ]; then
    printf '%s\n' "${expected_bots}" >"${ops}/config/merge-ready-bots.txt"
  fi
  run_upgrade_apply "${ops}" "${json_out}" "${err_out}"
  local rc=$?
  if [ "${rc}" -eq 0 ] && [ "$(cat "${ops}/config/merge-ready-stop-paths.txt")" = "${expected_stop}" ] && [ "$(cat "${ops}/config/merge-ready-bots.txt")" = "${expected_bots}" ] && python3 - "${json_out}" "${expected_stop_action}" "${expected_bots_action}" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
actions = {item["path"]: item["action"] for item in payload["actions"]}
assert actions["config/merge-ready-stop-paths.txt"] == sys.argv[2], actions
assert actions["config/merge-ready-bots.txt"] == sys.argv[3], actions
PY
  then
    ok "${label} seeds or preserves both merge-ready configs with the expected actions"
  else
    fail "${label}: got ${rc}: $(cat "${err_out}" 2>/dev/null || true)"
  fi
}

template_stop_contents="$(cat "${SCRIPT_DIR}/../config/merge-ready-stop-paths.txt")"
template_bots_contents="$(cat "${SCRIPT_DIR}/../config/merge-ready-bots.txt")"
assert_upgrade_seed_case "upgrade with both configs absent" "${WORK_DIR}/upgrade-both-missing" "${template_stop_contents}" "${template_bots_contents}" written written
assert_upgrade_seed_case "upgrade with existing stop-list" "${WORK_DIR}/upgrade-stop-existing" "install-owned-stop-list" "${template_bots_contents}" skipped-as-instance-owned written
assert_upgrade_seed_case "upgrade with existing bot roster" "${WORK_DIR}/upgrade-bots-existing" "${template_stop_contents}" "install-owned-bots" written skipped-as-instance-owned
assert_upgrade_seed_case "upgrade with both configs existing" "${WORK_DIR}/upgrade-both-existing" "install-owned-stop-list" "install-owned-bots" skipped-as-instance-owned skipped-as-instance-owned

invalid_seed_template="${WORK_DIR}/invalid-seed-template"
cp -R "${SCRIPT_DIR}/.." "${invalid_seed_template}"
mv "${invalid_seed_template}/config/merge-ready-stop-paths.txt" "${invalid_seed_template}/config/merge-ready-stop-paths.txt.saved"
ln -s merge-ready-stop-paths.txt "${invalid_seed_template}/config/merge-ready-stop-paths.txt"
invalid_seed_ops="${WORK_DIR}/invalid-seed-ops"
mkdir -p "${invalid_seed_ops}"
invalid_seed_json="${WORK_DIR}/invalid-seed.json"
invalid_seed_err="${WORK_DIR}/invalid-seed.err"
python3 -I "${SCRIPT_DIR}/template-apply" \
  --ops "${invalid_seed_ops}" --template "${invalid_seed_template}" --write --confirm-input apply --json \
  --placeholder WORKSPACE_NAME=seed-test \
  --placeholder WORKSPACE_ROOT="${WORK_DIR}/workspace" \
  --placeholder OPS_REPO="${invalid_seed_ops}" \
  --placeholder MONITOR_NS=seed-test \
  --placeholder MODEL_ID=seed-test \
  --placeholder REPO_LIST=seed-test \
  --placeholder RUNTIME_ROOT="${WORK_DIR}/runtime" \
  >"${invalid_seed_json}" 2>"${invalid_seed_err}"
rc=$?
if [ "${rc}" -eq 1 ] && grep -q 'error-invalid-path: config/merge-ready-stop-paths.txt' "${invalid_seed_err}"; then
  ok "a merge-ready seed symlink loop is reported as error-invalid-path"
else
  fail "invalid merge-ready seed path: got ${rc}: $(cat "${invalid_seed_err}" 2>/dev/null || true)"
fi

skip_stderr="${WORK_DIR}/skip-stderr"
skip_stdout="${WORK_DIR}/skip-stdout"
GH_FIXTURE_DIR="${clean_dir}" GH_STUB_CASE="" "${MERGE_READY}" --repo "${REPO}" --pr 1 >"${skip_stdout}" 2>"${skip_stderr}"; rc=$?
if [ "${rc}" -eq 0 ] && grep -Fq 'out-of-contract check skipped (no --contract)' "${skip_stderr}" && grep -Fq 'contract scope check skipped (no --contract)' "${skip_stdout}"; then
  ok "missing --contract prints the skipped scope check"
else
  fail "missing --contract notice: got ${rc}: $(cat "${skip_stderr}")"
fi

failed_check_dir="${WORK_DIR}/failed-check"
write_fixture "${failed_check_dir}" '[{"filename":"README.md"}]' "" "${FAILING_CHECK}"
out=$(run_case "${failed_check_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'ci=FAILURE'; then
  ok "failing required check exits 1 and names ci"
else
  fail "failing required check: got ${rc}: ${out}"
fi

empty_checks_dir="${WORK_DIR}/empty-checks"
write_fixture "${empty_checks_dir}" '[{"filename":"README.md"}]' "" '[]'
out=$(run_case "${empty_checks_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'non-empty list'; then
  ok "empty required list exits 1"
else
  fail "empty required list: got ${rc}: ${out}"
fi

missing_bot_dir="${WORK_DIR}/missing-bot"
write_fixture "${missing_bot_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]'
out=$(run_case "${missing_bot_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "listed bot without head review or rate-limit comment exits 1"
else
  fail "missing roster bot: got ${rc}: ${out}"
fi

rate_limit_dir="${WORK_DIR}/rate-limit"
rate_limit_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${rate_limit_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${FRESH_DATE}"'"}]]' >"${rate_limit_dir}/timeline.json"
out=$(run_case "${rate_limit_dir}"); rc=$?
assert_rc "measured rate-limit comment covers the listed bot" 0 "${out}" "${rc}"

missing_required_line_dir="${WORK_DIR}/missing-required-line"
missing_required_line_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${missing_required_line_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${missing_required_line_comment}"
out=$(run_case "${missing_required_line_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a marker without the required notice line exits 1"
else
  fail "missing required notice line: got ${rc}: ${out}"
fi

incomplete_roster_dir="${WORK_DIR}/incomplete-roster"
write_fixture "${incomplete_roster_dir}" '[{"filename":"README.md"}]' ""
printf '%s\n' 'coderabbitai | <!-- This is an auto-generated comment: rate limited by coderabbit.ai --> | none' >"${INSTALL_DIR}/config/merge-ready-bots.txt"
out=$(run_case "${incomplete_roster_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'incomplete rate-limit form'; then
  ok "an incomplete roster form fails identically in shared review parsing"
else
  fail "incomplete roster form: got ${rc}: ${out}"
fi
cat >"${INSTALL_DIR}/config/merge-ready-bots.txt" <<'EOF'
cubic-dev-ai | none | none
coderabbitai | <!-- This is an auto-generated comment: rate limited by coderabbit.ai --> | > ## Review limit reached
EOF

missing_writes_contract="${WORK_DIR}/missing-writes-contract.md"
printf '%s\n' '---' '---' '# no writes field' >"${missing_writes_contract}"
out=$(GH_FIXTURE_DIR="${clean_dir}" GH_STUB_CASE="" "${MERGE_READY}" --repo "${REPO}" --pr 1 --contract "${missing_writes_contract}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'contract front matter has no writes'; then
  ok "a contract without writes fails closed in shared path parsing"
else
  fail "missing contract writes: got ${rc}: ${out}"
fi

cubic_rate_limit_dir="${WORK_DIR}/cubic-rate-limit"
cubic_rate_limit_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by cubic.dev -->\n\n> ## Review limit reached","user":{"login":"cubic-dev-ai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${cubic_rate_limit_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${cubic_rate_limit_comment}"
out=$(run_case "${cubic_rate_limit_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'cubic-dev-ai'; then
  ok "a Cubic rate-limit notice does not create an exemption"
else
  fail "Cubic rate-limit exemption: got ${rc}: ${out}"
fi

summary_only_dir="${WORK_DIR}/summary-only"
summary_comment='[{"body":"Review summary for this change.","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${summary_only_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${summary_comment}"
out=$(run_case "${summary_only_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a non-rate-limit comment without a head review exits 1"
else
  fail "non-rate-limit comment: got ${rc}: ${out}"
fi

stale_rate_limit_dir="${WORK_DIR}/stale-rate-limit"
stale_rate_limit_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${STALE_DATE}"'"}]'
write_fixture "${stale_rate_limit_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${stale_rate_limit_comment}"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${FRESH_DATE}"'"}]]' >"${stale_rate_limit_dir}/timeline.json"
out=$(run_case "${stale_rate_limit_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a stale rate-limit comment exits 1"
else
  fail "stale rate-limit comment: got ${rc}: ${out}"
fi

no_comment_dir="${WORK_DIR}/no-comment"
write_fixture "${no_comment_dir}" '[{"filename":"README.md"}]' ""
out=$(run_case "${no_comment_dir}"); rc=$?
assert_rc "comments are not required for the GitHub-state measurement" 0 "${out}" "${rc}"

quoted_notice_dir="${WORK_DIR}/quoted-notice"
quoted_notice_comment='[{"body":"A prior comment quoted the phrase: Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${quoted_notice_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${quoted_notice_comment}"
out=$(run_case "${quoted_notice_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a bot comment quoting the notice phrase does not count"
else
  fail "quoted rate-limit notice: got ${rc}: ${out}"
fi

backdated_dir="${WORK_DIR}/backdated-committer"
backdated_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${BACKDATED_COMMENT_DATE}"'"}]'
write_fixture "${backdated_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${backdated_comment}"
printf '%s' "${STALE_DATE}" >"${backdated_dir}/commit-date.txt"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"'"${FRESH_DATE}"'"}]]' >"${backdated_dir}/timeline.json"
out=$(run_case "${backdated_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a backdated committer date cannot qualify an older rate-limit notice"
else
  fail "backdated committer date: got ${rc}: ${out}"
fi

thread_dir="${WORK_DIR}/open-thread"
write_fixture "${thread_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 1
out=$(run_case "${thread_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'open review thread'; then
  ok "unresolved thread exits 1"
else
  fail "unresolved thread: got ${rc}: ${out}"
fi

stop_dir="${WORK_DIR}/stop-path"
write_fixture "${stop_dir}" '[{"filename":"config/gitleaks.toml"}]' ""
out=$(run_case "${stop_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'stop-list' && printf '%s' "${out}" | grep -q "head ${HEAD_SHA}"; then
  ok "stop-list path exits 2 and reports the measured head"
else
  fail "stop-list path: got ${rc}: ${out}"
fi

root_layout_stop_dir="${WORK_DIR}/root-layout-stop-path"
write_fixture "${root_layout_stop_dir}" '[{"filename":"docs/charter/01-document-map.md"}]' ""
out=$(run_case "${root_layout_stop_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'docs/charter/01-document-map.md (stop-list)'; then
  ok "a root-layout charter path matches the template stop-list and exits 2"
else
  fail "root-layout stop-list path: got ${rc}: ${out}"
fi

root_layout_dispatch_dir="${WORK_DIR}/root-layout-dispatch-path"
write_fixture "${root_layout_dispatch_dir}" '[{"filename":"scripts/dispatch"}]' ""
out=$(run_case "${root_layout_dispatch_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'scripts/dispatch (stop-list)'; then
  ok "an installed dispatch path matches the template stop-list and exits 2"
else
  fail "root-layout dispatch stop-list path: got ${rc}: ${out}"
fi

case_variant_stop_dir="${WORK_DIR}/case-variant-stop-path"
write_fixture "${case_variant_stop_dir}" '[{"filename":"Docs/Charter/01-document-map.md"}]' ""
out=$(run_case "${case_variant_stop_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q 'Docs/Charter/01-document-map.md (stop-list)'; then
  ok "a case-variant stop-list path exits 2"
else
  fail "case-variant stop-list path: got ${rc}: ${out}"
fi

template_layout_prefix='master-'"ops/"
template_layout_stop_path="${template_layout_prefix}docs/charter/01-document-map.md"
template_layout_stop_dir="${WORK_DIR}/template-layout-stop-path"
write_fixture "${template_layout_stop_dir}" "[{\"filename\":\"${template_layout_stop_path}\"}]" ""
out=$(run_case "${template_layout_stop_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q "${template_layout_stop_path} (stop-list)"; then
  ok "a template-layout charter path matches the installed stop-list and exits 2"
else
  fail "template-layout charter stop-list path: got ${rc}: ${out}"
fi

template_layout_dispatch_path="${template_layout_prefix}scripts/dispatch"
template_layout_dispatch_dir="${WORK_DIR}/template-layout-dispatch-path"
write_fixture "${template_layout_dispatch_dir}" "[{\"filename\":\"${template_layout_dispatch_path}\"}]" ""
out=$(run_case "${template_layout_dispatch_dir}"); rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -q "${template_layout_dispatch_path} (stop-list)"; then
  ok "a template-layout dispatch path matches the installed stop-list and exits 2"
else
  fail "template-layout dispatch stop-list path: got ${rc}: ${out}"
fi

manifest_dir="${WORK_DIR}/manifest"
manifest_path_prefix="master-ops"
manifest_file="${manifest_path_prefix}/MANIFEST.json"
write_fixture "${manifest_dir}" "[{\"filename\":\"${manifest_file}\"}]" ""
out=$(run_case "${manifest_dir}"); rc=$?
if [ "${rc}" -eq 0 ] && printf '%s' "${out}" | grep -q "head ${HEAD_SHA}"; then
  ok "manifest-only change reports the measured head"
else
  fail "manifest-only change: got ${rc}: ${out}"
fi

timeline_dir="${WORK_DIR}/timeline-fallback"
write_fixture "${timeline_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${CUBIC_REVIEW}" 0 OPEN false "${rate_limit_comment}"
printf '%s' '[{"check_runs":[]}]' >"${timeline_dir}/check-runs.json"
printf '%s' '[{"check_suites":[]}]' >"${timeline_dir}/check-suites.json"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"2026-01-01T00:00:00Z"}]]' >"${timeline_dir}/timeline.json"
out=$(run_case "${timeline_dir}"); rc=$?
assert_rc "PR timeline supplies the trusted head time when check runs are empty" 0 "${out}" "${rc}"

if grep -Fq 'commits/${HEAD_SHA}/check-runs' "${SCRIPT_DIR}/merge-ready"; then
  fail "check-run fetch remains despite gh pr checks being the verdict source"
else
  ok "check-run fetch is removed and gh pr checks remains the verdict source"
fi

file_cap_dir="${WORK_DIR}/file-cap"
write_fixture "${file_cap_dir}" '[{"filename":"README.md"}]' ""
python3 - "${file_cap_dir}/files.json" <<'PY'
import json
import sys
json.dump([[{"filename": f"docs/file-{index}.md"} for index in range(3000)]], open(sys.argv[1], "w", encoding="utf-8"))
PY
out=$(run_case "${file_cap_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q '3000-file cap'; then
  ok "3000 changed files exits 1 with the cap reason"
else
  fail "3000-file cap: got ${rc}: ${out}"
fi

draft_dir="${WORK_DIR}/draft"
write_fixture "${draft_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" "${DEFAULT_REVIEWS}" 0 OPEN true
out=$(run_case "${draft_dir}"); rc=$?
assert_rc "draft PR exits 1" 1 "${out}" "${rc}"

non_required_dir="${WORK_DIR}/non-required"
write_fixture "${non_required_dir}" '[{"filename":"README.md"}]' "" '[{"name":"ci","bucket":"pass","state":"SUCCESS"},{"name":"review","bucket":"fail","state":"FAILURE","required":false}]'
out=$(run_case "${non_required_dir}"); rc=$?
assert_rc "non-required failing check is excluded" 0 "${out}" "${rc}"

out=$(run_case "${clean_dir}" checks-fail); rc=$?
assert_rc "GitHub failure exits 1" 1 "${out}" "${rc}"

out=$(run_case "${clean_dir}" graphql-bad-json); rc=$?
assert_rc "unparseable GitHub reply exits 1" 1 "${out}" "${rc}"

scan_rc=0
grep -Eq 'eval|tarball|test-command|TEST_CMD' "${SCRIPT_DIR}/merge-ready" >/dev/null || scan_rc=$?
if [ "${scan_rc}" -eq 0 ]; then
  fail "production script still contains removed execution interface"
elif [ "${scan_rc}" -eq 1 ]; then
  ok "production script has no removed execution interface"
else
  fail "removed execution interface check failed with grep status ${scan_rc}"
fi

if grep -Fq 'required configuration' "${SCRIPT_DIR}/merge-ready" && grep -Fq '2  ask the owner' "${SCRIPT_DIR}/merge-ready"; then
  ok "exit-code documentation includes missing required configuration under exit 2"
else
  fail "exit-code documentation omits missing required configuration"
fi

if [ "${F}" -ne 0 ]; then
  echo "merge-ready seeded tests: FAIL"
  exit 1
fi
echo "merge-ready seeded tests: PASS"
