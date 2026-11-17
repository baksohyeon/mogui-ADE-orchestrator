#!/bin/bash
# Regression checks for scripts/issue-similar against a stubbed `gh`, so no
# test here ever makes a real network call. Each case plants its own `gh` in
# a scratch bin/ directory and prepends it to PATH (never replaces PATH, so
# python3 and the rest of the toolchain stay reachable), runs the real
# script as a subprocess, and checks stdout/stderr/exit code.
set -eu

SCRIPT="${1:-$(cd "$(dirname "$0")" && pwd)/issue-similar}"

run_with_stub() {  # gh-body work-dir -- args...
  local gh_body="$1" work="$2"
  shift 2
  mkdir -p "$work/bin"
  printf '%s\n' "$gh_body" > "$work/bin/gh"
  chmod +x "$work/bin/gh"
  # --query-delay 0 last, so it always overrides anything the caller passed
  # (argparse keeps the last value for a repeated flag) and no case here
  # pays the real default pacing delay.
  PATH="$work/bin:$PATH" python3 "$SCRIPT" "$@" --query-delay 0
}

# --- Case: a failed gh call exits 1 and names the reason. ------------------
failed_gh_call_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-failed.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "stub: network unreachable" >&2
exit 1' \
    "$work" --repo acme/widgets --title "alphaword betaword" 2>&1)
  status=$?
  [ "$status" -eq 1 ] || { echo "FAIL: a failed gh call should exit 1, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"gh search issues failed"*"network unreachable"*) ;;
    *) echo "FAIL: stderr missing the gh failure reason" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : a failed gh call exits 1 and names the reason"
)
failed_gh_call_test || exit 1

# --- Case: an empty response (gh exits 0, prints nothing) exits 1, never 0.-
empty_response_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-empty.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
exit 0' \
    "$work" --repo acme/widgets --title "alphaword betaword" 2>&1)
  status=$?
  [ "$status" -eq 1 ] || { echo "FAIL: an empty gh response should exit 1 (never 0), got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"empty response"*) ;;
    *) echo "FAIL: stderr missing the empty-response reason" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : an empty gh response exits 1 (never 0) and names the reason"
)
empty_response_test || exit 1

# --- Case: an unparseable response exits 1, never 0. ------------------------
unparseable_response_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-unparseable.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "not valid json at all"' \
    "$work" --repo acme/widgets --title "alphaword betaword" 2>&1)
  status=$?
  [ "$status" -eq 1 ] || { echo "FAIL: an unparseable gh response should exit 1 (never 0), got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"unparseable response"*) ;;
    *) echo "FAIL: stderr missing the unparseable-response reason" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : an unparseable gh response exits 1 (never 0) and names the reason"
)
unparseable_response_test || exit 1

# --- Case: one of several queries failing still aborts the whole run, -----
# --- not just drops that query's results (a merge, not best-effort).      --
partial_query_failure_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-partial.$$"
  trap 'rm -rf "${work:?}"' EXIT
  # The title yields two distinct query terms; only the one containing
  # "zzzfailterm" fails, found by inspecting the stub's own last argument
  # rather than call order, so this does not depend on query ordering.
  out=$(run_with_stub \
    '#!/bin/bash
last="${@: -1}"
case "$last" in
  *zzzfailterm*) echo "stub: simulated failure on this term" >&2; exit 7 ;;
  *) echo "[]" ;;
esac' \
    "$work" --repo acme/widgets --title "harmlessalpha zzzfailterm" 2>&1)
  status=$?
  [ "$status" -eq 1 ] || { echo "FAIL: a partial query failure should still exit 1, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"zzzfailterm"*"simulated failure"*) ;;
    *) echo "FAIL: stderr missing the failing query's reason" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : one failing query among several aborts the run instead of silently shrinking the results"
)
partial_query_failure_test || exit 1

# --- Case: a valid empty list ([]) is a legitimate zero-match result, ------
# --- distinct from the "empty response" failure above, and exits 0.       --
no_match_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-nomatch.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "[]"' \
    "$work" --repo acme/widgets --title "alphaword betaword" 2>&1)
  status=$?
  [ "$status" -eq 0 ] || { echo "FAIL: a valid empty candidate list should exit 0, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"no candidates found"*) ;;
    *) echo "FAIL: expected the no-candidates message on stdout" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : a valid empty candidate list exits 0, distinct from an empty/unparseable gh response"
)
no_match_test || exit 1

# --- Case: a strong match (score above threshold) exits 3. -----------------
strong_match_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-strong.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "[{\"number\": 42, \"title\": \"zzzalpha zzzbeta zzzgamma reported again\", \"state\": \"open\", \"url\": \"https://example.invalid/42\", \"body\": \"\"}]"' \
    "$work" --repo acme/widgets --title "zzzalpha zzzbeta zzzgamma" 2>&1)
  status=$?
  [ "$status" -eq 3 ] || { echo "FAIL: a strong match should exit 3, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"#42"*"score=3"*) ;;
    *) echo "FAIL: stdout missing the matched candidate and its score" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : three shared distinctive words clear the threshold and exit 3"
)
strong_match_test || exit 1

# --- Case: --exclude drops the named issue number from candidates, the ----
# --- mechanism the weekly sweep needs to avoid every issue matching itself.-
# The candidate clears the threshold on its own (three shared words, like
# strong_match_test above), so --exclude has to visibly flip exit 3 -> 0,
# not just remove a candidate that was never going to change the exit code.
exclude_drops_self_match_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-exclude.$$"
  trap 'rm -rf "${work:?}"' EXIT
  local gh_stub='#!/bin/bash
echo "[{\"number\": 99, \"title\": \"alphaword betaword gammaword also appears here\", \"state\": \"open\", \"url\": \"https://example.invalid/99\", \"body\": \"\"}]"'
  out=$(run_with_stub "$gh_stub" "$work" --repo acme/widgets --title "alphaword betaword gammaword" 2>&1)
  status=$?
  [ "$status" -eq 3 ] || { echo "FAIL: three shared words should clear the threshold without --exclude, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"#99"*) ;;
    *) echo "FAIL: candidate #99 should be listed without --exclude" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  local work2
  work2="${TMPDIR:-/tmp}/mogui-issue-similar-exclude2.$$"
  trap 'rm -rf "${work:?}"; rm -rf "${work2:?}"' EXIT
  out=$(run_with_stub "$gh_stub" "$work2" --repo acme/widgets --title "alphaword betaword gammaword" --exclude 99 2>&1)
  status=$?
  [ "$status" -eq 0 ] || { echo "FAIL: excluding the only (otherwise threshold-clearing) candidate should exit 0, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"#99"*) echo "FAIL: --exclude 99 should have dropped candidate #99" >&2; printf '%s\n' "$out" >&2; return 1 ;;
    *"no candidates found"*) ;;
    *) echo "FAIL: expected the no-candidates message once #99 is excluded" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : --exclude visibly flips exit 3 -> 0 for a candidate that would otherwise clear the threshold"
)
exclude_drops_self_match_test || exit 1

# --- Case: a title's own words outrank longer, generic body filler, so a ---
# --- --body-file does not crowd the title's words out of the bounded slice.-
body_does_not_crowd_out_title_words_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-bodycrowd.$$"
  trap 'rm -rf "${work:?}"' EXIT
  mkdir -p "$work"
  printf '%s' 'stepstoreproduceissue reproduceenvironment verboselogsattached screenshotattached' > "$work/body.txt"
  out=$(run_with_stub \
    '#!/bin/bash
echo "[{\"number\": 11, \"title\": \"login fails safari\", \"state\": \"open\", \"url\": \"https://example.invalid/11\", \"body\": \"\"}]"' \
    "$work" --repo acme/widgets --title "login fails safari" --body-file "$work/body.txt" --max-words 4 2>&1)
  status=$?
  [ "$status" -eq 3 ] || { echo "FAIL: the title's own 3 words should clear the threshold despite a longer body, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *"#11"*"score=3"*) ;;
    *) echo "FAIL: stdout missing candidate #11 at score=3" >&2; printf '%s\n' "$out" >&2; return 1 ;;
  esac
  echo "ok   : title words are kept ahead of longer generic body words inside the bounded word slice"
)
body_does_not_crowd_out_title_words_test || exit 1

# --- Case: a title that is nothing but stopwords (or non-ASCII) still ------
# --- yields real search/score terms instead of silently matching nothing. --
stopword_and_non_ascii_title_fallback_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-stopword.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "[{\"number\": 21, \"title\": \"the and is\", \"state\": \"open\", \"url\": \"https://example.invalid/21\", \"body\": \"\"}]"' \
    "$work" --repo acme/widgets --title "the and is" --json 2>&1)
  status=$?
  [ "$status" -eq 0 ] || { echo "FAIL: unexpected exit $status for a stopword-only title" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *'"words": []'*) echo "FAIL: a stopword-only title should still fall back to some query/score terms, not an empty word list" >&2; printf '%s\n' "$out" >&2; return 1 ;;
    *) ;;
  esac
  case "$out" in
    *'"score": 0'*) echo "FAIL: an exact stopword-only duplicate should score above 0" >&2; printf '%s\n' "$out" >&2; return 1 ;;
    *) ;;
  esac
  echo "ok   : a stopword-only title falls back to real terms instead of silently scoring every candidate 0"
)
stopword_and_non_ascii_title_fallback_test || exit 1

# --- Case: the gh invocation itself carries --repo, --state, and a bare ----
# --- -- separator ahead of the query, so a regression dropping one of      --
# --- these would be caught even though every other case only checks the   --
# --- final exit code and printed candidates.                              --
gh_invocation_shape_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-ghshape.$$"
  trap 'rm -rf "${work:?}"' EXIT
  mkdir -p "$work/bin"
  cat > "$work/bin/gh" <<'BIN'
#!/bin/bash
printf '%s\n' "$*" >> "$MOGUI_TEST_ARGV_LOG"
echo "[]"
BIN
  chmod +x "$work/bin/gh"
  out=$(cd "$work" && MOGUI_TEST_ARGV_LOG="$work/argv.log" PATH="$work/bin:$PATH" \
        python3 "$SCRIPT" --repo acme/widgets --title "alphaword" --query-delay 0 2>&1)
  status=$?
  [ "$status" -eq 0 ] || { echo "FAIL: unexpected exit $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  [ -f "$work/argv.log" ] || { echo "FAIL: gh was never invoked" >&2; return 1; }
  local logged
  logged=$(cat "$work/argv.log")
  case "$logged" in
    *"search issues --repo acme/widgets"*) ;;
    *) echo "FAIL: gh argv missing 'search issues --repo acme/widgets': $logged" >&2; return 1 ;;
  esac
  case "$logged" in
    *"--state open"*) ;;
    *) echo "FAIL: gh argv missing '--state open': $logged" >&2; return 1 ;;
  esac
  case "$logged" in
    *" -- alphaword"*) ;;
    *) echo "FAIL: gh argv missing a bare -- ahead of the query: $logged" >&2; return 1 ;;
  esac
  echo "ok   : the gh invocation carries --repo, --state open, and a bare -- ahead of the query"
)
gh_invocation_shape_test || exit 1

# --- Case: a short common slash-phrase or a date is not mistaken for a ----
# --- path/script-name term (that weight alone is enough to clear the      --
# --- threshold, so a false positive here is an expensive one).            --
short_slash_phrase_is_not_a_path_test() (
  set +e
  local work out status
  work="${TMPDIR:-/tmp}/mogui-issue-similar-notpath.$$"
  trap 'rm -rf "${work:?}"' EXIT
  out=$(run_with_stub \
    '#!/bin/bash
echo "[{\"number\": 55, \"title\": \"fixed on 2026/11/17, read/write and/or CI/CD either way\", \"state\": \"open\", \"url\": \"https://example.invalid/55\", \"body\": \"\"}]"' \
    "$work" --repo acme/widgets --title "a bug happened on 2026/11/17, filed under and/or CI/CD" --json 2>&1)
  status=$?
  [ "$status" -eq 0 ] || { echo "FAIL: a date and short slash-phrases alone should not clear the threshold, got $status" >&2; printf '%s\n' "$out" >&2; return 1; }
  case "$out" in
    *'"code_terms": []'*) ;;
    *) echo "FAIL: 2026/11/17, and/or, and CI/CD should all be rejected as code terms: $out" >&2; return 1 ;;
  esac
  echo "ok   : a date and a short common slash-phrase are not mistaken for a path/script-name term"
)
short_slash_phrase_is_not_a_path_test || exit 1

echo "issue-similar regression tests passed"
