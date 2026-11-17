#!/usr/bin/env bash
# Cases for scripts/merge-ready, against a stubbed `gh` so none of this
# touches the network. Acceptance checks from contract #330:
#   (a) a failed check -> 1; (b) an open review thread -> 1;
#   (c) a stop-list path change -> 2; (d) a clean PR -> 0;
#   (e) a missing or an unparseable gh response -> 1 with a reason, never 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -x "${SCRIPT_DIR}/merge-ready" ]; then
  echo "FAIL: ${SCRIPT_DIR}/merge-ready is missing or not executable"
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

# A scratch install (scripts/ next to config/), not the real checkout: the
# real config/merge-ready-stop-paths.txt is instance-owned and does not
# exist at all in a rendered, template-only checkout (issue measured in
# CI), and merge-ready itself has no override for that path, by design (a
# worker with shell access could otherwise point it at an empty file and
# neutralize the stop list). Copying the real script next to a fixture
# config/ directory exercises the real, unmodified path-resolution logic.
INSTALL_DIR="${WORK_DIR}/install"
mkdir -p "${INSTALL_DIR}/scripts" "${INSTALL_DIR}/config"
cp "${SCRIPT_DIR}/merge-ready" "${INSTALL_DIR}/scripts/merge-ready"
chmod +x "${INSTALL_DIR}/scripts/merge-ready"
MERGE_READY="${INSTALL_DIR}/scripts/merge-ready"
printf '%s\n' "config/gitleaks.toml" >"${INSTALL_DIR}/config/merge-ready-stop-paths.txt"

STUB_DIR="${WORK_DIR}/stub"
mkdir -p "${STUB_DIR}"

cat >"${STUB_DIR}/gh" <<'EOF'
#!/usr/bin/env bash
# Fixture gh: reads canned JSON (or, for the tarball endpoint, raw bytes)
# from $GH_FIXTURE_DIR, named by which endpoint this call hit. GH_STUB_CASE
# overrides one endpoint to simulate a missing, broken, or failing response.
# `pr checks` mimics real gh: its own exit code is 1 whenever any entry in
# the fixture is not bucket "pass", but the JSON itself still prints, the
# same way a pending or failing required check behaves live. It also
# mimics `--required` itself: a fixture check entry with `"required":
# false` is filtered out before the JSON ever reaches the caller, the way
# a review-bot or label/assignee check never appears in real `gh pr checks
# --required` output at all.
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
          head-moved)
            # merge-ready calls `pr view` twice: once before the test
            # re-run (to pick a tarball) and once after (to re-check the
            # head). The first call here returns pr.json; every call
            # after that returns pr-moved.json, simulating a push that
            # landed while the test was running.
            counter="${GH_FIXTURE_DIR}/.pr_view_calls"
            n=$(( $(cat "${counter}" 2>/dev/null || echo 0) + 1 ))
            echo "${n}" >"${counter}"
            if [ "${n}" -le 1 ]; then
              cat "${GH_FIXTURE_DIR}/pr.json"
            else
              cat "${GH_FIXTURE_DIR}/pr-moved.json"
            fi
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
        required_only="$(python3 -c "
import json
data = json.load(open('${GH_FIXTURE_DIR}/checks.json', encoding='utf-8'))
print(json.dumps([c for c in data if c.get('required', True)]))
")"
        printf '%s' "${required_only}"
        python3 -c "
import json, sys
sys.exit(0 if all(c.get('bucket') == 'pass' for c in json.loads('''${required_only}''')) else 1)
"
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
# `--strip-components=1`, the same shape a GitHub tarball download has. A
# second one with a trivial failing test script, for the real-test-re-run
# cases below.
FIXTURE_SRC="${WORK_DIR}/fixture-src/stub-repo-${HEAD_SHA}"
mkdir -p "${FIXTURE_SRC}"
echo "fixture" >"${FIXTURE_SRC}/README.md"
TARBALL="${WORK_DIR}/head.tar.gz"
tar -czf "${TARBALL}" -C "${WORK_DIR}/fixture-src" "stub-repo-${HEAD_SHA}"

DEFAULT_CHECKS='[{"name":"ci","bucket":"pass","state":"SUCCESS"}]'

write_fixture() {
  # $1 fixture dir; $2 PR body; $3 open-thread count; $4 changed-file JSON
  # array body; $5 review-pass marker line (or ""); $6 checks.json array
  # body (default: one passing required check; an entry may add
  # `"required": false` to simulate a check `--required` filters out);
  # $7 reviews.nodes JSON array body for bot reviews (default none);
  # $8 PR state (default OPEN); $9 isDraft (default false)
  local dir="$1" body="$2" open_threads="$3" files_json="$4" marker="$5"
  local checks_json="${6:-${DEFAULT_CHECKS}}" bot_reviews="${7:-[]}"
  local pr_state="${8:-OPEN}" is_draft="${9:-false}"
  mkdir -p "${dir}"
  python3 - "${dir}/pr.json" "${HEAD_SHA}" "${body}" "${pr_state}" "${is_draft}" <<'PY'
import json, sys
path, head_sha, body, pr_state, is_draft = sys.argv[1:6]
data = {
    "number": 1,
    "url": "https://example.invalid/pr/1",
    "headRefOid": head_sha,
    "body": body,
    "state": pr_state,
    "isDraft": is_draft == "true",
}
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

# --- a failing check that --required would exclude (not required) never
# reaches this script at all, so the PR still reads clean -----------------
non_required_dir="${WORK_DIR}/non-required-excluded"
write_fixture "${non_required_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" \
  '[{"name":"ci","bucket":"pass","state":"SUCCESS"},{"name":"CodeRabbit","bucket":"fail","state":"FAILURE","required":false}]'
out=$(run_case "${non_required_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a failing check --required excludes does not block (${out})"
else
  fail "non-required failing check exited ${rc}, want 0: ${out}"
fi

# --- a repository with no required checks at all is not blocked ------------
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

# --- a stop-paths file with no real entries (all blank/commented) fails
# closed instead of silently meaning "nothing to block" --------------------
no_entries_dir="${WORK_DIR}/no-stop-entries"
write_fixture "${no_entries_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${PASS_MARKER}"
empty_install="${WORK_DIR}/install-empty-stoplist"
mkdir -p "${empty_install}/scripts" "${empty_install}/config"
cp "${SCRIPT_DIR}/merge-ready" "${empty_install}/scripts/merge-ready"
chmod +x "${empty_install}/scripts/merge-ready"
printf '# only comments\n\n' >"${empty_install}/config/merge-ready-stop-paths.txt"
out=$(GH_FIXTURE_DIR="${no_entries_dir}" "${empty_install}/scripts/merge-ready" --repo "${REPO}" --pr 1 --test-command true)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no entries"; then
  ok "a stop-paths file with no real entries fails closed (${out})"
else
  fail "empty-entries stop-paths file exited ${rc}, want 1: ${out}"
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

# --- a glob with its own brackets (an fnmatch character class) survives the
# writes: list parse intact, rather than being truncated at the first "]" --
bracket_glob_dir="${WORK_DIR}/bracket-glob-writes"
write_fixture "${bracket_glob_dir}" "" 0 '[{"filename":"src/a.py"}]' "${PASS_MARKER}"
bracket_contract="${WORK_DIR}/bracket-contract.md"
printf '%s\n' "---" "writes: [src/[ab].py]" "---" >"${bracket_contract}"
out=$(GH_FIXTURE_DIR="${bracket_glob_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true --contract "${bracket_contract}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a writes: glob with inner brackets is parsed intact (${out})"
else
  fail "writes: glob with inner brackets exited ${rc}, want 0: ${out}"
fi

# --- a contract missing a real writes: front-matter field is not ready, not
# an ask, and a `writes: [...]` example in the contract's body text (after
# the closing `---`) is never mistaken for the declared scope --------------
body_example_dir="${WORK_DIR}/body-example-writes"
write_fixture "${body_example_dir}" "" 0 '[{"filename":"somewhere/else.py"}]' "${PASS_MARKER}"
no_writes_contract="${WORK_DIR}/no-writes-contract.md"
printf '%s\n' "---" "tier: efficient" "---" "" "Example: \`writes: [**]\` is how a contract scopes a worker." \
  >"${no_writes_contract}"
out=$(GH_FIXTURE_DIR="${body_example_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true --contract "${no_writes_contract}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "writes"; then
  ok "a writes: example in the contract body is not read as the declared scope (${out})"
else
  fail "contract with no front-matter writes: list exited ${rc}, want 1: ${out}"
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

# --- a bot's later, passing review on the same head commit supersedes its
# own earlier CHANGES_REQUESTED; only the latest counts -------------------
superseded_bot_dir="${WORK_DIR}/superseded-bot"
superseded_review_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
head_sha = sys.argv[1]
print(json.dumps([
    {"state": "CHANGES_REQUESTED", "commit": {"oid": head_sha}, "author": {"login": "some-bot", "__typename": "Bot"}},
    {"state": "APPROVED", "commit": {"oid": head_sha}, "author": {"login": "some-bot", "__typename": "Bot"}},
]))
PY
)
write_fixture "${superseded_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${DEFAULT_CHECKS}" "${superseded_review_json}"
out=$(run_case "${superseded_bot_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a bot's superseded CHANGES_REQUESTED on the same head does not block once it later approves (${out})"
else
  fail "superseded bot review exited ${rc}, want 0: ${out}"
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

# --- ask still wins over not-ready even when the test step itself could
# not run at all (no known command for this repo, and no override), since
# the stop-list check happens after the test step regardless of whether
# the test step itself could run -------------------------------------------
tool_failure_ask_dir="${WORK_DIR}/tool-failure-ask-wins"
write_fixture "${tool_failure_ask_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${tool_failure_ask_dir}" "${MERGE_READY}" --repo "nobody/unknown-repo" --pr 1)
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list"; then
  ok "a stop-list hit still asks even when the test step itself could not run (${out})"
else
  fail "stop-list hit plus a tool failure exited ${rc}, want 2: ${out}"
fi

# --- an unknown repository with no --test-command override is not ready,
# naming the missing test command -------------------------------------------
unknown_repo_dir="${WORK_DIR}/unknown-repo"
write_fixture "${unknown_repo_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${unknown_repo_dir}" GH_STUB_CASE="" "${MERGE_READY}" --repo "nobody/unknown-repo" --pr 1)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no known test command"; then
  ok "an unknown repository with no --test-command is not ready (${out})"
else
  fail "unknown repository with no test command exited ${rc}, want 1: ${out}"
fi

# --- a real failing test command is not ready, naming the test re-run -----
failing_test_dir="${WORK_DIR}/failing-test-command"
write_fixture "${failing_test_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${failing_test_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command false)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test re-run failed"; then
  ok "a failing test command exits 1 naming the test re-run (${out})"
else
  fail "failing test command exited ${rc}, want 1 naming the test re-run: ${out}"
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

# --- a pullRequest with reviews/reviewThreads present but malformed (no
# nodes/pageInfo) is 1, not a silent "zero reviews, zero threads" pass ----
malformed_connections_dir="${WORK_DIR}/malformed-connections"
write_fixture "${malformed_connections_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
printf '%s' '{"data":{"repository":{"pullRequest":{"reviews":{},"reviewThreads":{}}}}}' \
  >"${malformed_connections_dir}/graphql.json"
out=$(run_case "${malformed_connections_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "reviews"; then
  ok "a pullRequest with malformed reviews/reviewThreads exits 1, not a silent pass (${out})"
else
  fail "malformed reviews/reviewThreads exited ${rc}, want 1: ${out}"
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

# --- a closed PR is not ready, never read as mergeable ---------------------
closed_dir="${WORK_DIR}/closed-pr"
write_fixture "${closed_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "CLOSED" "false"
out=$(run_case "${closed_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "CLOSED"; then
  ok "a closed PR exits 1, naming its state (${out})"
else
  fail "closed PR exited ${rc}, want 1 naming CLOSED: ${out}"
fi

# --- a draft PR is not ready ------------------------------------------------
draft_dir="${WORK_DIR}/draft-pr"
write_fixture "${draft_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "OPEN" "true"
out=$(run_case "${draft_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "draft"; then
  ok "a draft PR exits 1, naming it as a draft (${out})"
else
  fail "draft PR exited ${rc}, want 1 naming draft: ${out}"
fi

# --- a head that moves during the test re-run is not ready, never a stale
# pass on a commit the measurement no longer reflects ----------------------
head_moved_dir="${WORK_DIR}/head-moved"
write_fixture "${head_moved_dir}" "" 0 '[{"filename":"README.md"}]' "${PASS_MARKER}"
python3 - "${head_moved_dir}/pr.json" "${head_moved_dir}/pr-moved.json" "${OTHER_SHA}" <<'PY'
import json, sys
src, dst, other_sha = sys.argv[1:4]
data = json.load(open(src, encoding="utf-8"))
data["headRefOid"] = other_sha
open(dst, "w", encoding="utf-8").write(json.dumps(data))
PY
out=$(run_case "${head_moved_dir}" head-moved)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "head changed"; then
  ok "a head that moves during the test re-run exits 1, not a stale pass (${out})"
else
  fail "head-moved-during-run exited ${rc}, want 1 naming the change: ${out}"
fi

echo "----"
[ "${F}" -eq 0 ] && echo "pass" || echo "fail"
exit "${F}"
