#!/usr/bin/env bash
# Cases for scripts/merge-ready, against a stubbed `gh` so none of this
# touches the network. Acceptance checks from contract #330 round 2:
#   body `rate-limited:` naming a failing required check -> 1; an empty
#   required-checks list -> 1; a roster bot with no head review and no
#   recent comment -> 1, naming it; a rate-limit comment from that bot ->
#   not blocking; only a worker-pass marker -> 1; a master-pass marker for
#   an older head -> 1; a stop-list hit -> 2 with no test run.
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
HEAD_COMMIT_DATE="2026-01-01T00:00:00Z"
STALE_DATE="2025-01-01T00:00:00Z"
FRESH_DATE="2026-01-02T00:00:00Z"

# A scratch install (scripts/ next to config/), not the real checkout: the
# real config/merge-ready-stop-paths.txt and config/merge-ready-bots.txt
# are instance-owned and do not exist at all in a rendered, template-only
# checkout (issue measured in CI for the stop-paths file), and merge-ready
# itself has no override for either path, by design (a worker with shell
# access could otherwise point one at an empty file and neutralize it).
# Copying the real script next to fixture config/ files exercises the
# real, unmodified path-resolution logic. The fixture roster is a single
# made-up bot name, not the real cubic-dev-ai/coderabbitai list: this
# suite tests the mechanism, not the production roster.
INSTALL_DIR="${WORK_DIR}/install"
mkdir -p "${INSTALL_DIR}/scripts" "${INSTALL_DIR}/config"
cp "${SCRIPT_DIR}/merge-ready" "${INSTALL_DIR}/scripts/merge-ready"
chmod +x "${INSTALL_DIR}/scripts/merge-ready"
MERGE_READY="${INSTALL_DIR}/scripts/merge-ready"
printf '%s\n' "config/gitleaks.toml" >"${INSTALL_DIR}/config/merge-ready-stop-paths.txt"
printf '%s\n' "test-bot" >"${INSTALL_DIR}/config/merge-ready-bots.txt"

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
# --required` output at all. `files`/`comments` fixtures are already
# page-wrapped (`[[...]]`) the way `--paginate --slurp` itself wraps a
# single page; `--jq` on the commits endpoint is mimicked by the fixture
# file holding the already-extracted bare value, since this stub never
# runs jq itself.
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
      repos/*/commits/*)
        if [ "${GH_STUB_CASE:-}" = "commit-date-fail" ]; then
          echo "gh: commit lookup failed" >&2
          exit 1
        fi
        cat "${GH_FIXTURE_DIR}/commit-date.txt"
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
FAILING_CHECK='[{"name":"ci","bucket":"fail","state":"FAILURE"}]'
# A COMMENTED review from the one roster bot, at the exact head: satisfies
# the roster by default in every fixture that is not itself testing the
# roster or the CHANGES_REQUESTED/PENDING bot-blocking measurement.
DEFAULT_BOT_REVIEWS='[{"state":"COMMENTED","commit":{"oid":"HEAD_SHA_PLACEHOLDER"},"author":{"login":"test-bot","__typename":"Bot"}}]'
DEFAULT_BOT_REVIEWS="${DEFAULT_BOT_REVIEWS//HEAD_SHA_PLACEHOLDER/${HEAD_SHA}}"

write_fixture() {
  # $1 fixture dir; $2 PR body; $3 open-thread count; $4 changed-file JSON
  # array body; $5 master-pass marker line (or ""); $6 checks.json array
  # body (default: one passing required check; an entry may add
  # `"required": false` to simulate a check `--required` filters out);
  # $7 reviews.nodes JSON array body for bot reviews (default: the one
  # roster bot, COMMENTED, at the head); $8 PR state (default OPEN); $9
  # isDraft (default false); $10 extra issue-comment objects JSON array,
  # already shaped {body,user:{login,type},created_at} (default none)
  local dir="$1" body="$2" open_threads="$3" files_json="$4" marker="$5"
  local checks_json="${6:-${DEFAULT_CHECKS}}" bot_reviews="${7:-${DEFAULT_BOT_REVIEWS}}"
  local pr_state="${8:-OPEN}" is_draft="${9:-false}" extra_comments="${10:-[]}"
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
  # files.json is page-wrapped: one page holding the given flat array,
  # the shape `--paginate --slurp` itself produces for a single page.
  python3 - "${dir}/files.json" "${files_json}" <<'PY'
import json, sys
path, files_raw = sys.argv[1:3]
open(path, "w", encoding="utf-8").write(json.dumps([json.loads(files_raw)]))
PY
  python3 - "${dir}/comments.json" "${marker}" "${extra_comments}" <<'PY'
import json, sys
path, marker, extra_raw = sys.argv[1:4]
comments = []
if marker:
    comments.append({"body": marker, "user": {"login": "the-master", "type": "User"}, "created_at": "2026-01-01T00:00:00Z"})
comments.extend(json.loads(extra_raw))
open(path, "w", encoding="utf-8").write(json.dumps([comments]))
PY
  printf '%s' "${HEAD_COMMIT_DATE}" >"${dir}/commit-date.txt"
  cp "${TARBALL}" "${dir}/head.tar.gz"
}

MASTER_PASS_MARKER="merge-ready-master-pass sha=${HEAD_SHA} critical=0 important=0"
WORKER_PASS_MARKER="merge-ready-worker-pass sha=${HEAD_SHA} critical=0 important=0"

run_case() {
  # $1 fixture dir; $2 GH_STUB_CASE value (or ""); prints "<rc> <output>"
  local dir="$1" stub_case="${2:-}"
  GH_FIXTURE_DIR="${dir}" GH_STUB_CASE="${stub_case}" \
    "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true
}

# --- clean PR -> 0 ------------------------------------------------------
clean_dir="${WORK_DIR}/clean"
write_fixture "${clean_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
out=$(run_case "${clean_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "clean PR exits 0 (${out})"
else
  fail "clean PR exited ${rc}, want 0: ${out}"
fi

# --- a failing required check -> 1, even though gh's own exit code for
# `pr checks` is nonzero too (the stub mirrors real gh there) -------------
check_dir="${WORK_DIR}/failed-check"
write_fixture "${check_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${FAILING_CHECK}"
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
write_fixture "${non_required_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" \
  '[{"name":"ci","bucket":"pass","state":"SUCCESS"},{"name":"CodeRabbit","bucket":"fail","state":"FAILURE","required":false}]'
out=$(run_case "${non_required_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a failing check --required excludes does not block (${out})"
else
  fail "non-required failing check exited ${rc}, want 0: ${out}"
fi

# --- (round 2, critical #3) an empty-but-parseable required-checks array
# is not ready, never read as "nothing is required, so pass" -------------
empty_checks_dir="${WORK_DIR}/empty-checks"
write_fixture "${empty_checks_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "[]"
out=$(run_case "${empty_checks_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "non-empty list"; then
  ok "an empty required-checks array is not ready, never 0 (${out})"
else
  fail "empty required-checks list exited ${rc}, want 1: ${out}"
fi

# --- (round 2, critical #1) a PR body naming a failing required check as
# rate-limited no longer skips it: there is no PR-body exemption anymore -
rate_limited_body_dir="${WORK_DIR}/rate-limited-body"
write_fixture "${rate_limited_body_dir}" "rate-limited: ci" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${FAILING_CHECK}"
out=$(run_case "${rate_limited_body_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "ci=failure"; then
  ok "a PR-body rate-limited line no longer exempts a failing required check (${out})"
else
  fail "PR-body rate-limited line exited ${rc}, want 1 still naming ci=failure: ${out}"
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

# --- (round 2, important #4) the one roster bot with no head review and
# no recent comment of any kind is not ready, naming it -------------------
missing_bot_dir="${WORK_DIR}/missing-bot"
write_fixture "${missing_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "[]"
out=$(run_case "${missing_bot_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test-bot"; then
  ok "a roster bot with no head review or recent comment is not ready, naming it (${out})"
else
  fail "missing roster bot exited ${rc}, want 1 naming test-bot: ${out}"
fi

# --- (round 2, critical #1 + important #4) that same missing bot, but with
# a rate-limit comment at or after the head's own timestamp, is not
# blocking: the rate-limit exception now lives only on the bot roster -----
rate_limited_bot_dir="${WORK_DIR}/rate-limited-bot"
rate_limit_comment='[{"body":"Review limit reached for this billing cycle.","user":{"login":"test-bot[bot]","type":"Bot"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${rate_limited_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "OPEN" "false" "${rate_limit_comment}"
out=$(run_case "${rate_limited_bot_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a rate-limit comment from the missing bot is not blocking (${out})"
else
  fail "rate-limited bot comment exited ${rc}, want 0: ${out}"
fi

# --- the same rate-limit comment, but dated before the head commit, does
# not cover the bot: it is for an earlier push, not this one --------------
stale_rate_limit_dir="${WORK_DIR}/stale-rate-limit"
stale_rate_limit_comment='[{"body":"Review limit reached for this billing cycle.","user":{"login":"test-bot[bot]","type":"Bot"},"created_at":"'"${STALE_DATE}"'"}]'
write_fixture "${stale_rate_limit_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "OPEN" "false" "${stale_rate_limit_comment}"
out=$(run_case "${stale_rate_limit_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test-bot"; then
  ok "a rate-limit comment dated before the head commit does not cover the bot (${out})"
else
  fail "stale rate-limit comment exited ${rc}, want 1 naming test-bot: ${out}"
fi

# --- the rate-limit phrase from a human account does not cover the bot:
# the roster check's Bot-type guard must not be fooled by matching text
# alone --------------------------------------------------------------
human_rate_limit_dir="${WORK_DIR}/human-rate-limit-text"
human_rate_limit_comment='[{"body":"Review limit reached for this billing cycle.","user":{"login":"test-bot","type":"User"},"created_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${human_rate_limit_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "OPEN" "false" "${human_rate_limit_comment}"
out=$(run_case "${human_rate_limit_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test-bot"; then
  ok "the rate-limit phrase from a human account does not cover the bot (${out})"
else
  fail "human-account rate-limit text exited ${rc}, want 1 naming test-bot: ${out}"
fi

# --- a bot's sticky comment, created before the head commit but edited at
# or after it, still covers the bot: cubic and CodeRabbit both edit one
# comment in place on every push rather than posting a fresh one, so
# `updated_at`, not only `created_at`, has to move this measurement -------
edited_comment_dir="${WORK_DIR}/edited-comment-covers-bot"
edited_comment='[{"body":"Summary of this PR.","user":{"login":"test-bot[bot]","type":"Bot"},"created_at":"'"${STALE_DATE}"'","updated_at":"'"${FRESH_DATE}"'"}]'
write_fixture "${edited_comment_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "[]" "OPEN" "false" "${edited_comment}"
out=$(run_case "${edited_comment_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a bot's comment created before the head but edited after it still covers the bot (${out})"
else
  fail "edited-after-head comment exited ${rc}, want 0: ${out}"
fi

# --- an empty bots file fails closed, the same way an empty stop-paths
# file does, rather than reading as "no bots required" --------------------
empty_bots_install="${WORK_DIR}/install-empty-bots"
mkdir -p "${empty_bots_install}/scripts" "${empty_bots_install}/config"
cp "${SCRIPT_DIR}/merge-ready" "${empty_bots_install}/scripts/merge-ready"
chmod +x "${empty_bots_install}/scripts/merge-ready"
printf '%s\n' "config/gitleaks.toml" >"${empty_bots_install}/config/merge-ready-stop-paths.txt"
printf '# only comments\n\n' >"${empty_bots_install}/config/merge-ready-bots.txt"
empty_bots_dir="${WORK_DIR}/empty-bots-fixture"
write_fixture "${empty_bots_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${empty_bots_dir}" "${empty_bots_install}/scripts/merge-ready" --repo "${REPO}" --pr 1 --test-command true)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no entries"; then
  ok "an empty bots file fails closed (${out})"
else
  fail "empty-entries bots file exited ${rc}, want 1: ${out}"
fi

# --- an open review thread -> 1 --------------------------------------------
thread_dir="${WORK_DIR}/open-thread"
write_fixture "${thread_dir}" "" 1 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
out=$(run_case "${thread_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "open review thread"; then
  ok "an open review thread exits 1 (${out})"
else
  fail "open review thread exited ${rc}, want 1 naming the thread: ${out}"
fi

# --- (round 2, important #6) a stop-list path change -> 2, and the test
# re-run never ran at all: a sentinel the test command would have touched
# must not exist afterward -------------------------------------------------
stop_dir="${WORK_DIR}/stop-path"
write_fixture "${stop_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${MASTER_PASS_MARKER}"
sentinel="${WORK_DIR}/stop-path-sentinel"
out=$(GH_FIXTURE_DIR="${stop_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command "touch '${sentinel}'")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list" && printf '%s' "${out}" | grep -qi "tests not run" && [ ! -e "${sentinel}" ]; then
  ok "a stop-list path change exits 2 and never runs the test command (${out})"
else
  fail "stop-list path change exited ${rc} (sentinel exists: $([ -e "${sentinel}" ] && echo yes || echo no)), want 2 with no test run: ${out}"
fi

# --- a stop-paths file with no real entries (all blank/commented) fails
# closed instead of silently meaning "nothing to block" --------------------
no_entries_dir="${WORK_DIR}/no-stop-entries"
write_fixture "${no_entries_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${MASTER_PASS_MARKER}"
empty_install="${WORK_DIR}/install-empty-stoplist"
mkdir -p "${empty_install}/scripts" "${empty_install}/config"
cp "${SCRIPT_DIR}/merge-ready" "${empty_install}/scripts/merge-ready"
chmod +x "${empty_install}/scripts/merge-ready"
printf '# only comments\n\n' >"${empty_install}/config/merge-ready-stop-paths.txt"
printf '%s\n' "test-bot" >"${empty_install}/config/merge-ready-bots.txt"
out=$(GH_FIXTURE_DIR="${no_entries_dir}" "${empty_install}/scripts/merge-ready" --repo "${REPO}" --pr 1 --test-command true)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no entries"; then
  ok "a stop-paths file with no real entries fails closed (${out})"
else
  fail "empty-entries stop-paths file exited ${rc}, want 1: ${out}"
fi

# --- a path outside --contract's writes globs also asks (exit 2), decided
# early, before any test re-run --------------------------------------------
contract_dir="${WORK_DIR}/outside-writes"
write_fixture "${contract_dir}" "" 0 '[{"filename":"somewhere/else.py"}]' "${MASTER_PASS_MARKER}"
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
write_fixture "${in_scope_dir}" "" 0 '[{"filename":"somewhere/allowed.py"}]' "${MASTER_PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${in_scope_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command true --contract "${contract_file}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a path inside the contract's writes globs does not ask (${out})"
else
  fail "path inside contract writes exited ${rc}, want 0: ${out}"
fi

# --- an explicit empty writes: [] list declares an empty scope, so every
# changed path is outside it: this must ask early (before any test re-run),
# the same as a non-empty list a path falls outside, never silently pass
# through as if an empty list meant "nothing to check" --------------------
empty_writes_dir="${WORK_DIR}/empty-writes-list"
write_fixture "${empty_writes_dir}" "" 0 '[{"filename":"anything.py"}]' "${MASTER_PASS_MARKER}"
empty_writes_contract="${WORK_DIR}/empty-writes-contract.md"
printf '%s\n' "---" "writes: []" "---" >"${empty_writes_contract}"
empty_writes_sentinel="${WORK_DIR}/empty-writes-sentinel"
out=$(GH_FIXTURE_DIR="${empty_writes_dir}" "${MERGE_READY}" --repo "${REPO}" --pr 1 --test-command "touch '${empty_writes_sentinel}'" --contract "${empty_writes_contract}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "outside contract writes" && [ ! -e "${empty_writes_sentinel}" ]; then
  ok "an explicit writes: [] asks early for every changed path, no test run (${out})"
else
  fail "writes: [] exited ${rc} (sentinel exists: $([ -e "${empty_writes_sentinel}" ] && echo yes || echo no)), want 2 with no test run: ${out}"
fi

# --- a glob with its own brackets (an fnmatch character class) survives the
# writes: list parse intact, rather than being truncated at the first "]" --
bracket_glob_dir="${WORK_DIR}/bracket-glob-writes"
write_fixture "${bracket_glob_dir}" "" 0 '[{"filename":"src/a.py"}]' "${MASTER_PASS_MARKER}"
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
write_fixture "${body_example_dir}" "" 0 '[{"filename":"somewhere/else.py"}]' "${MASTER_PASS_MARKER}"
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

# --- (round 2, critical #2) only a worker-pass marker, no master-pass at
# all, is not ready: the worker's own say-so never satisfies this check ---
worker_only_dir="${WORK_DIR}/worker-only-marker"
write_fixture "${worker_only_dir}" "" 0 '[{"filename":"README.md"}]' "${WORKER_PASS_MARKER}"
out=$(run_case "${worker_only_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no master-pass marker found"; then
  ok "a worker-pass marker alone does not satisfy the master-pass check (${out})"
else
  fail "worker-only marker exited ${rc}, want 1 naming the missing master-pass marker: ${out}"
fi

# --- a missing marker of any kind is not ready, not merged -----------------
no_marker_dir="${WORK_DIR}/no-marker"
write_fixture "${no_marker_dir}" "" 0 '[{"filename":"README.md"}]' ""
out=$(run_case "${no_marker_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no master-pass marker found"; then
  ok "a missing master-pass marker exits 1 (${out})"
else
  fail "missing master-pass marker exited ${rc}, want 1: ${out}"
fi

# --- a master-pass marker recording Critical or Important findings is not
# ready ----------------------------------------------------------------
findings_dir="${WORK_DIR}/findings"
write_fixture "${findings_dir}" "" 0 '[{"filename":"README.md"}]' \
  "merge-ready-master-pass sha=${HEAD_SHA} critical=1 important=0"
out=$(run_case "${findings_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "critical=1"; then
  ok "a recorded Critical finding exits 1 (${out})"
else
  fail "recorded Critical finding exited ${rc}, want 1: ${out}"
fi

important_findings_dir="${WORK_DIR}/important-findings"
write_fixture "${important_findings_dir}" "" 0 '[{"filename":"README.md"}]' \
  "merge-ready-master-pass sha=${HEAD_SHA} critical=0 important=1"
out=$(run_case "${important_findings_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "important=1"; then
  ok "a recorded Important finding exits 1 (${out})"
else
  fail "recorded Important finding exited ${rc}, want 1: ${out}"
fi

# --- (round 2, critical #2) a master-pass marker for an older sha is not
# a pass for the current head -----------------------------------------------
stale_dir="${WORK_DIR}/stale-marker"
write_fixture "${stale_dir}" "" 0 '[{"filename":"README.md"}]' \
  "merge-ready-master-pass sha=${OTHER_SHA} critical=0 important=0"
out=$(run_case "${stale_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "not head"; then
  ok "a master-pass marker for a different sha is not a pass for this head (${out})"
else
  fail "stale master-pass marker exited ${rc}, want 1 naming the mismatch: ${out}"
fi

# --- a missing gh response is 1 with a reason, never 0 -----------------
out=$(run_case "${clean_dir}" missing)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a missing gh response exits 1 with a reason (${out})"
else
  fail "missing gh response exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- an unparseable gh response is 1 with a reason, never 0 -----------
out=$(run_case "${clean_dir}" bad-json)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "an unparseable gh response exits 1 with a reason (${out})"
else
  fail "unparseable gh response exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- a bot review left CHANGES_REQUESTED on the exact head exits 1 --------
pending_bot_dir="${WORK_DIR}/pending-bot"
bot_review_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
print(json.dumps([{"state": "CHANGES_REQUESTED", "commit": {"oid": sys.argv[1]}, "author": {"login": "test-bot", "__typename": "Bot"}}]))
PY
)
write_fixture "${pending_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${bot_review_json}"
out=$(run_case "${pending_bot_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test-bot=changes_requested"; then
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
    {"state": "CHANGES_REQUESTED", "commit": {"oid": head_sha}, "author": {"login": "test-bot", "__typename": "Bot"}},
    {"state": "APPROVED", "commit": {"oid": head_sha}, "author": {"login": "test-bot", "__typename": "Bot"}},
]))
PY
)
write_fixture "${superseded_bot_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${superseded_review_json}"
out=$(run_case "${superseded_bot_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a bot's superseded CHANGES_REQUESTED on the same head does not block once it later approves (${out})"
else
  fail "superseded bot review exited ${rc}, want 0: ${out}"
fi

# --- a bot's later COMMENTED-only review does NOT clear its own standing
# CHANGES_REQUESTED: a remark carries no decision, unlike an approval -----
commented_after_dir="${WORK_DIR}/commented-after-changes-requested"
commented_after_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
head_sha = sys.argv[1]
print(json.dumps([
    {"state": "CHANGES_REQUESTED", "commit": {"oid": head_sha}, "author": {"login": "test-bot", "__typename": "Bot"}},
    {"state": "COMMENTED", "commit": {"oid": head_sha}, "author": {"login": "test-bot", "__typename": "Bot"}},
]))
PY
)
write_fixture "${commented_after_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${commented_after_json}"
out=$(run_case "${commented_after_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "test-bot=changes_requested"; then
  ok "a bot's later COMMENTED review does not clear its own standing CHANGES_REQUESTED (${out})"
else
  fail "bot COMMENTED after CHANGES_REQUESTED exited ${rc}, want 1 still naming it: ${out}"
fi

# --- a human reviewer's own CHANGES_REQUESTED review does not count, and
# the roster bot's own separate review still covers the roster ------------
human_review_json=$(python3 - "${HEAD_SHA}" <<'PY'
import json, sys
head_sha = sys.argv[1]
print(json.dumps([
    {"state": "CHANGES_REQUESTED", "commit": {"oid": head_sha}, "author": {"login": "a-human", "__typename": "User"}},
    {"state": "COMMENTED", "commit": {"oid": head_sha}, "author": {"login": "test-bot", "__typename": "Bot"}},
]))
PY
)
human_review_dir="${WORK_DIR}/human-review"
write_fixture "${human_review_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${human_review_json}"
out=$(run_case "${human_review_dir}")
rc=$?
if [ "${rc}" -eq 0 ]; then
  ok "a human reviewer's CHANGES_REQUESTED is not a bot failure (${out})"
else
  fail "human reviewer's CHANGES_REQUESTED exited ${rc}, want 0: ${out}"
fi

# --- a rename carries its old path, so a stop-listed rename still asks,
# before any test re-run -----------------------------------------------
rename_dir="${WORK_DIR}/rename"
write_fixture "${rename_dir}" "" 0 \
  '[{"filename":"config/renamed.toml","previous_filename":"config/gitleaks.toml"}]' "${MASTER_PASS_MARKER}"
out=$(run_case "${rename_dir}")
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list"; then
  ok "renaming a stop-listed path still asks, by its old name (${out})"
else
  fail "renaming a stop-listed path exited ${rc}, want 2: ${out}"
fi

# --- a stop-list hit on an unknown repository (no known test command,
# none overridden) still asks the same way: the early check runs before
# the test command is even chosen, so a repo this script cannot test for
# still gets the stop-list verdict, not a tool-failure one -----------------
tool_failure_ask_dir="${WORK_DIR}/tool-failure-ask-wins"
write_fixture "${tool_failure_ask_dir}" "" 0 '[{"filename":"config/gitleaks.toml"}]' "${MASTER_PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${tool_failure_ask_dir}" "${MERGE_READY}" --repo "nobody/unknown-repo" --pr 1)
rc=$?
if [ "${rc}" -eq 2 ] && printf '%s' "${out}" | grep -qi "stop-list"; then
  ok "a stop-list hit on an unknown repository still asks (${out})"
else
  fail "stop-list hit on an unknown repository exited ${rc}, want 2: ${out}"
fi

# --- an unknown repository with no --test-command override is not ready,
# naming the missing test command -------------------------------------------
unknown_repo_dir="${WORK_DIR}/unknown-repo"
write_fixture "${unknown_repo_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
out=$(GH_FIXTURE_DIR="${unknown_repo_dir}" GH_STUB_CASE="" "${MERGE_READY}" --repo "nobody/unknown-repo" --pr 1)
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "no known test command"; then
  ok "an unknown repository with no --test-command is not ready (${out})"
else
  fail "unknown repository with no test command exited ${rc}, want 1: ${out}"
fi

# --- a real failing test command is not ready, naming the test re-run -----
failing_test_dir="${WORK_DIR}/failing-test-command"
write_fixture "${failing_test_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
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

# --- a head-commit-date lookup failure is 1 with a reason, never 0 --------
out=$(run_case "${clean_dir}" commit-date-fail)
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "a head commit date lookup failure exits 1 with a reason (${out})"
else
  fail "head commit date lookup failure exited ${rc} with output <${out}>, want 1 with a reason"
fi

# --- an empty head-commit-date response is 1, never read as "any comment
# timestamp is new enough" ---------------------------------------------
empty_commit_date_dir="${WORK_DIR}/empty-commit-date"
write_fixture "${empty_commit_date_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
printf '' >"${empty_commit_date_dir}/commit-date.txt"
out=$(run_case "${empty_commit_date_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && [ -n "${out}" ]; then
  ok "an empty head commit date response exits 1, not a silent pass (${out})"
else
  fail "empty head commit date response exited ${rc}, want 1: ${out}"
fi

# --- an empty-but-valid graphql response (no pullRequest) is 1 with a
# reason, never a silent "0 open threads, 0 failing bots" pass ------------
empty_gql_dir="${WORK_DIR}/empty-graphql"
write_fixture "${empty_gql_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
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
write_fixture "${malformed_connections_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
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
write_fixture "${empty_files_dir}" "" 0 '[]' "${MASTER_PASS_MARKER}"
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
write_fixture "${closed_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${DEFAULT_BOT_REVIEWS}" "CLOSED" "false"
out=$(run_case "${closed_dir}")
rc=$?
if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -qi "CLOSED"; then
  ok "a closed PR exits 1, naming its state (${out})"
else
  fail "closed PR exited ${rc}, want 1 naming CLOSED: ${out}"
fi

# --- a draft PR is not ready ------------------------------------------------
draft_dir="${WORK_DIR}/draft-pr"
write_fixture "${draft_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}" "${DEFAULT_CHECKS}" "${DEFAULT_BOT_REVIEWS}" "OPEN" "true"
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
write_fixture "${head_moved_dir}" "" 0 '[{"filename":"README.md"}]' "${MASTER_PASS_MARKER}"
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
