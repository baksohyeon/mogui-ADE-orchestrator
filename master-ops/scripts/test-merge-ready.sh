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

INSTALL_DIR="${WORK_DIR}/install"
mkdir -p "${INSTALL_DIR}/scripts" "${INSTALL_DIR}/config"
cp "${MERGE_READY}" "${INSTALL_DIR}/scripts/merge-ready"
chmod +x "${INSTALL_DIR}/scripts/merge-ready"
MERGE_READY="${INSTALL_DIR}/scripts/merge-ready"
printf '%s\n' "config/gitleaks.toml" >"${INSTALL_DIR}/config/merge-ready-stop-paths.txt"
printf '%s\n' "coderabbitai" >"${INSTALL_DIR}/config/merge-ready-bots.txt"

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
        else
          cat "${GH_FIXTURE_DIR}/pr.json"
        fi
        ;;
      checks)
        if [ "${GH_STUB_CASE:-}" = "checks-fail" ]; then
          echo "gh: checks unavailable" >&2
          exit 1
        fi
        required_only="$(python3 -c "import json; d=json.load(open('${GH_FIXTURE_DIR}/checks.json')); print(json.dumps([c for c in d if c.get('required', True)]))")"
        printf '%s' "${required_only}"
        python3 -c "import json, sys; sys.exit(0 if all(c.get('bucket') == 'pass' for c in json.loads('''${required_only}''')) else 1)"
        ;;
      *)
        echo "gh stub: unhandled pr command: $*" >&2
        exit 1
        ;;
    esac
    ;;
  api)
    case "${2:-}" in
      graphql)
        if [ "${GH_STUB_CASE:-}" = "graphql-fail" ]; then
          echo "gh: graphql unavailable" >&2
          exit 1
        fi
        if [ "${GH_STUB_CASE:-}" = "graphql-bad-json" ]; then
          echo "not json"
        else
          cat "${GH_FIXTURE_DIR}/graphql.json"
        fi
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
DEFAULT_REVIEWS='[{"state":"COMMENTED","commit":{"oid":"HEAD_SHA_PLACEHOLDER"},"author":{"login":"coderabbitai","__typename":"Bot"}}]'
DEFAULT_REVIEWS="${DEFAULT_REVIEWS//HEAD_SHA_PLACEHOLDER/${HEAD_SHA}}"

write_fixture() {
  local dir="$1" files_json="$2" _unused_comment="$3" checks_json="${4:-${DEFAULT_CHECKS}}"
  local reviews_json="${5:-${DEFAULT_REVIEWS}}" open_threads="${6:-0}"
  local state="${7:-OPEN}" is_draft="${8:-false}" extra_comments="${9:-[]}"
  mkdir -p "${dir}"
  python3 - "${dir}/pr.json" "${state}" "${is_draft}" <<'PY'
import json, sys
path, state, is_draft = sys.argv[1:]
json.dump({"number": 1, "url": "https://example.invalid/pr/1", "headRefOid": "0123456789abcdef0123456789abcdef01234567", "state": state, "isDraft": is_draft == "true"}, open(path, "w", encoding="utf-8"))
PY
  printf '%s' "${checks_json}" >"${dir}/checks.json"
  python3 - "${dir}/graphql.json" "${reviews_json}" "${open_threads}" <<'PY'
import json, sys
path, reviews_raw, open_threads = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = {"data": {"repository": {"pullRequest": {
    "reviewThreads": {"nodes": [{"isResolved": False} for _ in range(open_threads)], "pageInfo": {"hasNextPage": False}},
    "reviews": {"nodes": json.loads(reviews_raw), "pageInfo": {"hasNextPage": False}},
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
  printf '%s' '[{"check_runs":[{"created_at":"'"${CHECK_RUN_DATE}"'","check_suite":{"created_at":"'"${CHECK_RUN_DATE}"'"}}]}]' >"${dir}/check-runs.json"
  printf '%s' '[{"check_suites":[{"created_at":"'"${CHECK_RUN_DATE}"'"}]}]' >"${dir}/check-suites.json"
  printf '%s' '[[]]' >"${dir}/timeline.json"
}

run_case() {
  local dir="$1" stub_case="${2:-}"
  GH_FIXTURE_DIR="${dir}" GH_STUB_CASE="${stub_case}" "${MERGE_READY}" --repo "${REPO}" --pr 1
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

skip_stderr="${WORK_DIR}/skip-stderr"
GH_FIXTURE_DIR="${clean_dir}" GH_STUB_CASE="" "${MERGE_READY}" --repo "${REPO}" --pr 1 >/dev/null 2>"${skip_stderr}"; rc=$?
if [ "${rc}" -eq 0 ] && grep -Fq 'out-of-contract check skipped (no --contract)' "${skip_stderr}"; then
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
write_fixture "${rate_limit_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${rate_limit_comment}"
out=$(run_case "${rate_limit_dir}"); rc=$?
assert_rc "measured rate-limit comment covers the listed bot" 0 "${out}" "${rc}"

summary_only_dir="${WORK_DIR}/summary-only"
summary_comment='[{"body":"Review summary for this change.","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${summary_only_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${summary_comment}"
out=$(run_case "${summary_only_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a non-rate-limit comment without a head review exits 1"
else
  fail "non-rate-limit comment: got ${rc}: ${out}"
fi

stale_rate_limit_dir="${WORK_DIR}/stale-rate-limit"
stale_rate_limit_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${STALE_DATE}"'"}]'
write_fixture "${stale_rate_limit_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${stale_rate_limit_comment}"
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
write_fixture "${quoted_notice_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${quoted_notice_comment}"
out=$(run_case "${quoted_notice_dir}"); rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q 'coderabbitai'; then
  ok "a bot comment quoting the notice phrase does not count"
else
  fail "quoted rate-limit notice: got ${rc}: ${out}"
fi

backdated_dir="${WORK_DIR}/backdated-committer"
backdated_comment='[{"body":"<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n> ## Review limit reached","user":{"login":"coderabbitai[bot]","type":"Bot"},"created_at":"'"${BACKDATED_COMMENT_DATE}"'"}]'
write_fixture "${backdated_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${backdated_comment}"
printf '%s' "${STALE_DATE}" >"${backdated_dir}/commit-date.txt"
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
write_fixture "${timeline_dir}" '[{"filename":"README.md"}]' "" "${DEFAULT_CHECKS}" '[]' 0 OPEN false "${rate_limit_comment}"
printf '%s' '[{"check_runs":[]}]' >"${timeline_dir}/check-runs.json"
printf '%s' '[{"check_suites":[]}]' >"${timeline_dir}/check-suites.json"
printf '%s' '[[{"event":"head_ref_force_pushed","commit_id":"'"${HEAD_SHA}"'","created_at":"2026-01-01T00:00:00Z"}]]' >"${timeline_dir}/timeline.json"
out=$(run_case "${timeline_dir}"); rc=$?
assert_rc "PR timeline supplies the trusted head time when check runs are empty" 0 "${out}" "${rc}"

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

if grep -E 'eval|tarball|test-command|TEST_CMD' "${SCRIPT_DIR}/merge-ready" >/dev/null; then
  fail "production script still contains removed execution interface"
else
  grep_rc=$?
  if [ "${grep_rc}" -eq 1 ]; then
    ok "production script has no removed execution interface"
  else
    fail "removed execution interface check failed with grep status ${grep_rc}"
  fi
fi

if [ "${F}" -ne 0 ]; then
  echo "merge-ready seeded tests: FAIL"
  exit 1
fi
echo "merge-ready seeded tests: PASS"
