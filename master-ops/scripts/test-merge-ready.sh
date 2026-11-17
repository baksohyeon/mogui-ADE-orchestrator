#!/usr/bin/env bash
# Cases for scripts/merge-ready, against a stubbed `gh` so none of this
# touches the network. Acceptance checks from contract #330:
#   (a) a failed check -> 1; (b) an open review thread -> 1;
#   (c) a stop-list path change -> 2; (d) a clean PR -> 0;
#   (e) a missing or an unparseable gh response -> 1 with a reason, never 0.
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
OTHER_SHA="fedcba9876543210fedcba9876543210fedcba98"

STUB_DIR="${WORK_DIR}/stub"
mkdir -p "${STUB_DIR}"

cat >"${STUB_DIR}/gh" <<'EOF'
#!/usr/bin/env bash
# Fixture gh: reads canned JSON (or, for the tarball endpoint, raw bytes)
# from $GH_FIXTURE_DIR, named by which endpoint this call hit. GH_STUB_CASE
# overrides one endpoint to simulate a missing, broken, or failing response.
# `pr checks` mimics real gh: its own exit code is 1 whenever any entry in
# the fixture is not bucket "pass", but the JSON itself still prints, the
# same way a pending or failing required check behaves live.
set -u
case "$1" in
  pr)
    case "${2:-}" in
      view)
        case "${GH_STUB_CASE:-}" in
          missing)
            echo "gh: pull request not found" >&2
            exit 1
            ;;
          bad-json)
            echo "this is not json"
            ;;
          *)
            cat "${GH_FIXTURE_DIR}/pr.json"
            ;;
        esac
        exit 0
        ;;
      checks)
        if [ "${GH_STUB_CASE:-}" = "checks-broken" ]; then
          echo "gh: could not reach checks endpoint" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/checks.json"
        if python3 -c "
import json, sys
data = json.load(open('${GH_FIXTURE_DIR}/checks.json', encoding='utf-8'))
sys.exit(0 if all(c.get('bucket') == 'pass' for c in data) else 1)
"; then
          exit 0
        fi
        exit 1
        ;;
      *)
        echo "gh stub: unhandled pr subcommand: $*" >&2
        exit 1
        ;;
    esac
    ;;
  api)
    case "${2:-}" in
      graphql)
        if [ "${GH_STUB_CASE:-}" = "graphql-fail" ]; then
          echo "gh: graphql request failed" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/graphql.json"
        ;;
      repos/*/pulls/*/files)
        if [ "${GH_STUB_CASE:-}" = "files-fail" ]; then
          echo "gh: files request failed" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/files.json"
        ;;
      repos/*/issues/*/comments)
        if [ "${GH_STUB_CASE:-}" = "comments-fail" ]; then
          echo "gh: comments request failed" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/comments.json"
        ;;
      repos/*/tarball/*)
        cat "${GH_FIXTURE_DIR}/head.tar.gz"
        ;;
      *)
        echo "gh stub: unhandled api endpoint: ${2:-}" >&2
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

# A tiny tarball whose top-level entry is stripped by merge-ready's
# `--strip-components=1`, the same shape a GitHub tarball download has.
FIXTURE_SRC="${WORK_DIR}/fixture-src/stub-repo-${HEAD_SHA}"
mkdir -p "${FIXTURE_SRC}"
echo "fixture" >"${FIXTURE_SRC}/README.md"
TARBALL="${WORK_DIR}/head.tar.gz"
tar -czf "${TARBALL}" -C "${WORK_DIR}/fixture-src" "stub-repo-${HEAD_SHA}"

DEFAULT_CHECKS='[{"name":"ci","bucket":"pass","state":"SUCCESS"}]'

write_fixture() {
  # $1 fixture dir; $2 PR body; $3 open-thread count; $4 changed-file JSON
  # array body; $5 review-pass marker line (or ""); $6 checks.json array
  # body (default: one passing required check); $7 reviews.nodes JSON
  # array body for bot reviews (default none)
  local dir="$1" body="$2" open_threads="$3" files_json="$4" marker="$5"
  local checks_json="${6:-${DEFAULT_CHECKS}}" bot_reviews="${7:-[]}"
  mkdir -p "${dir}"
  python3 - "${dir}/pr.json" "${HEAD_SHA}" "${body}" <<'PY'
import json, sys
path, head_sha, body = sys.argv[1:4]
data = {"number": 1, "url": "https://example.invalid/pr/1", "headRefOid": head_sha, "body": body}
open(path, "w", encoding="utf-8").write(json.dumps(data))
PY
  printf '%s' "${checks_json}" >"${dir}/checks.json"
  python3 - "${dir}/graphql.json" "${open_threads}" "${bot_reviews}" <<'PY'
import json, sys
path, open_threads, bot_reviews_raw = sys.argv[1], int(sys.argv[2]), sys.argv[3]
nodes = [{"isResolved": False} for _ in range(open_threads)]
data = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {"nodes": nodes, "pageInfo": {"hasNextPage": False}},
                "reviews": {"nodes": json.loads(bot_reviews_raw), "pageInfo": {"hasNextPage": False}},
            }
        }
    }
}
open(path, "w", encoding="utf-8").write(json.dumps(data))
PY
  printf '%s' "${files_json}" >"${dir}/files.json"
  if [ -n "${marker}" ]; then
    python3 - "${dir}/comments.json" "${marker}" <<'PY'
import json, sys
path, marker = sys.argv[1:3]
open(path, "w", encoding="utf-8").write(json.dumps([{"body": marker}]))
PY
  else
    echo "[]" >"${dir}/comments.json"
  fi
  cp "${TARBALL}" "${dir}/head.tar.gz"
}

PASS_MARKER="merge-ready-review-pass sha=${HEAD_SHA} critical=0 important=0"
FAILING_CHECK='[{"name":"ci","bucket":"fail","state":"FAILURE"}]'

run_case() {
  # $1 fixture dir; $2 GH_STUB_CASE value (or ""); prints "<rc> <output>"
  local dir="$1" stub_case="${2:-}"
  GH_FIXTURE_DIR="${dir}" GH_STUB_CASE="${stub_case}" \
    "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true
}

# --- (d) clean PR -> 0 ------------------------------------------------------
clean_dir="${WORK_DIR}/clean"
write_fixture "${clean_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
out=$(run_case "${clean_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "clean PR exits 0 (${out})"
else
  fail "clean PR exited ${rc}, want 0: ${out}"
fi

# --- (a) a failing required check -> 1, even though gh's own exit code for
# `pr checks` is nonzero too (the stub mirrors real gh there) -------------
check_dir="${WORK_DIR}/failed-check"
write_fixture "${check_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${FAILING_CHECK}"
out=$(run_case "${check_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "ci=failure"; then
  ok "a failing required check exits 1 and names it (${out})"
else
  fail "failing required check exited ${rc}, want 1 naming it: ${out}"
fi

# --- a check this repository does not require never reaches merge-ready: it
# is simply absent from `gh pr checks --required`'s own output, so a PR
# whose only non-passing check is non-required reads as clean -------------
non_required_clean_dir="${WORK_DIR}/non-required-clean"
write_fixture "${non_required_clean_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "[]"
out=$(run_case "${non_required_clean_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a repository with no required checks at all is not blocked by this measurement (${out})"
else
  fail "empty required-checks list exited ${rc}, want 0: ${out}"
fi

# --- a check the PR body lists as rate-limited is the one exempted skip ---
rate_limited_dir="${WORK_DIR}/rate-limited"
write_fixture "${rate_limited_dir}" "rate-limited: ci" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${FAILING_CHECK}"
out=$(run_case "${rate_limited_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a check the PR body lists as rate-limited is skipped (${out})"
else
  fail "rate-limited check was not skipped, exited ${rc}: ${out}"
fi

# --- a checks response that is simply broken (no JSON at all) is 1 with a
# reason, distinct from a required check merely failing or pending --------
out=$(run_case "${clean_dir}" checks-broken)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a broken checks response exits 1 with a reason (${out})"
else
  fail "broken checks response exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- (b) open review thread -> 1 --------------------------------------------
thread_dir="${WORK_DIR}/open-thread"
write_fixture "${thread_dir}" "" 1 '[{"filename":"README.md"}]' "${PASS_MARKER}"
out=$(run_case "${thread_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "open review thread"; then
  ok "an open review thread exits 1 (${out})"
else
  fail "open review thread exited ${rc}, want 1 naming the thread: ${out}"
fi

# --- (c) stop-list path change -> 2 -----------------------------------------
stop_dir="${WORK_DIR}/stop-path"
write_fixture "${stop_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${PASS_MARKER}"
out=$(run_case "${stop_dir}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list"; then
  ok "a stop-list path change exits 2 (${out})"
else
  fail "stop-list path change exited ${rc}, want 2 naming the stop list: ${out}"
fi

# --- a path outside --contract's writes globs also asks (exit 2) -----------
contract_dir="${WORK_DIR}/outside-writes"
write_fixture "${contract_dir}" "" 0 '[{"filename":"somewhere/else.py"}]' "${PASS_MARKER}"
contract_file="${WORK_DIR}/contract.md"
printf '%s\n' "---" "writes: [somewhere/allowed.py]" "---" >"${contract_file}"
out=$(GH_FIXTURE_DIR="${contract_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true --contract "${contract_file}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "outside contract writes"; then
  ok "a path outside the contract's writes globs exits 2 (${out})"
else
  fail "path outside contract writes exited ${rc}, want 2: ${out}"
fi

# --- every changed path inside --contract's writes globs passes ------------
in_scope_dir="${WORK_DIR}/in-scope-writes"
write_fixture "${in_scope_dir}" "" 0 '[{"filename":"somewhere/allowed.py"}]' "${PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${in_scope_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true --contract "${contract_file}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a path inside the contract's writes globs does not ask (${out})"
else
  fail "path inside contract writes exited ${rc}, want 0: ${out}"
fi

# --- a missing review-pass marker is not ready, not merged -----------------
no_marker_dir="${WORK_DIR}/no-marker"
write_fixture "${no_marker_dir}" "" 0 '[{"filename":"README.md"}]' ""
out=$(run_case "${no_marker_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "review-pass marker"; then
  ok "a missing review-pass marker exits 1 (${out})"
else
  fail "missing review-pass marker exited ${rc}, want 1: ${out}"
fi

# --- a review pass recording Critical or Important findings is not ready ---
findings_dir="${WORK_DIR}/findings"
write_fixture "${findings_dir}" "" 0 '[{"filename":"README.md"}]' \
  "merge-ready-review-pass sha=${HEAD_SHA} critical=1 important=0"
out=$(run_case "${findings_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "critical=1"; then
  ok "a recorded Critical finding exits 1 (${out})"
else
  fail "recorded Critical finding exited ${rc}, want 1: ${out}"
fi

# --- (e) a missing gh response is 1 with a reason, never 0 -----------------
out=$(run_case "${clean_dir}" missing)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a missing gh response exits 1 with a reason (${out})"
else
  fail "missing gh response exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- (e) an unparseable gh response is 1 with a reason, never 0 -----------
out=$(run_case "${clean_dir}" bad-json)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "an unparseable gh response exits 1 with a reason (${out})"
else
  fail "unparseable gh response exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- a review-pass marker for a different sha is not a pass for this head --
stale_dir="${WORK_DIR}/stale-marker"
write_fixture "${stale_dir}" "" 0 '[{"filename":"README.md"}]' \
  "merge-ready-review-pass sha=${OTHER_SHA} critical=0 important=0"
out=$(run_case "${stale_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "not head"; then
  ok "a review-pass marker for a different sha is not a pass for this head (${out})"
else
  fail "stale review-pass marker exited ${rc}, want 1 naming the mismatch: ${out}"
fi

# --- a bot review left CHANGES_REQUESTED on the exact head exits 1 --------
pending_bot_dir="${WORK_DIR}/pending-bot"
bot_review_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
print(json.dumps([{"state": "CHANGES_REQUESTED", "commit": {"oid": sys.argv[1]}, "author": {"login": "some-bot", "__typename": "Bot"}}]))
PY
)
write_fixture "${pending_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${DEFAULT_CHECKS}" "${bot_review_json}"
out=$(run_case "${pending_bot_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "some-bot=changes_requested"; then
  ok "a bot review of CHANGES_REQUESTED on the exact head exits 1 (${out})"
else
  fail "bot review of CHANGES_REQUESTED exited ${rc}, want 1 naming it: ${out}"
fi

# --- a human reviewer's own CHANGES_REQUESTED review does not count -------
human_review_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
print(json.dumps([{"state": "CHANGES_REQUESTED", "commit": {"oid": sys.argv[1]}, "author": {"login": "a-human", "__typename": "User"}}]))
PY
)
human_review_dir="${WORK_DIR}/human-review"
write_fixture "${human_review_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${DEFAULT_CHECKS}" "${human_review_json}"
out=$(run_case "${human_review_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a human reviewer's CHANGES_REQUESTED is not a bot failure (${out})"
else
  fail "human reviewer's CHANGES_REQUESTED exited ${rc}, want 0: ${out}"
fi

# --- a rename carries its old path, so a stop-listed rename still asks ----
rename_dir="${WORK_DIR}/rename"
write_fixture "${rename_dir}" "" 0 \
  '[{"filename":"config/renamed.toml","previous_filename":"config/gitleaks.toml"}]' "${PASS_MARKER}"
out=$(run_case "${rename_dir}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list"; then
  ok "renaming a stop-listed path still asks, by its old name (${out})"
else
  fail "renaming a stop-listed path exited ${rc}, want 2: ${out}"
fi

# --- ask wins over not-ready when both are true ----------------------------
both_dir="${WORK_DIR}/ask-wins"
write_fixture "${both_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${PASS_MARKER}" "${FAILING_CHECK}"
out=$(run_case "${both_dir}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list" && printf '%s' "${out}" | grep -qi "ci=failure"; then
  ok "a stop-list hit plus a failed check still exits 2 and names both (${out})"
else
  fail "stop-list hit plus a failed check exited ${rc}, want 2 naming both: ${out}"
fi

# --- a graphql failure is 1 with a reason, never 0 -------------------------
out=$(run_case "${clean_dir}" graphql-fail)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a graphql failure exits 1 with a reason (${out})"
else
  fail "graphql failure exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- an empty-but-valid graphql response (no pullRequest) is 1 with a
# reason, never a silent "0 open threads, 0 failing bots" pass ------------
empty_gql_dir="${WORK_DIR}/empty-graphql"
write_fixture "${empty_gql_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
printf '%s' '{"data":{"repository":{}}}' >"${empty_gql_dir}/graphql.json"
out=$(run_case "${empty_gql_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "pullRequest"; then
  ok "a graphql response missing pullRequest exits 1, not a silent pass (${out})"
else
  fail "graphql response missing pullRequest exited ${rc}, want 1 naming the gap: ${out}"
fi

# --- a changed-files lookup failure is 1 with a reason, never 0 -----------
out=$(run_case "${clean_dir}" files-fail)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a changed-files lookup failure exits 1 with a reason (${out})"
else
  fail "changed-files lookup failure exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- an empty changed-files response is 1, never read as "nothing changed,
# so nothing to ask about" --------------------------------------------------
empty_files_dir="${WORK_DIR}/empty-files"
write_fixture "${empty_files_dir}" "" 0 '[]' "${PASS_MARKER}"
out=$(run_case "${empty_files_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "an empty changed-files response exits 1, not a silent pass (${out})"
else
  fail "empty changed-files response exited ${rc}, want 1: ${out}"
fi

# --- a comments lookup failure is 1 with a reason, never 0 -----------------
out=$(run_case "${clean_dir}" comments-fail)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a comments lookup failure exits 1 with a reason (${out})"
else
  fail "comments lookup failure exited ${rc} with output <${out}>, want 1 with a reason"
fi

echo "----"
[ "${F}" -eq 0 ] && echo "pass" || echo "fail"
exit "${F}"
