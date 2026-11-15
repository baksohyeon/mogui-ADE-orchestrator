#!/bin/bash
# Regression checks for the codex brief's measured push and pull-request
# destination. The function is extracted from dispatch so these cases run
# without Orca, a live worker, or network access.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

egress_fn=$(awk '$0=="append_codex_authorized_egress() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
[ -n "$egress_fn" ] || { echo "FAIL: could not extract codex egress function" >&2; exit 1; }
remote_fn=$(awk '$0=="github_remote_metadata() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
[ -n "$remote_fn" ] || { echo "FAIL: could not extract GitHub remote parser" >&2; exit 1; }

call_count=$(grep -c '^append_codex_authorized_egress$' "$dispatch" || true)
[ "$call_count" = 1 ] || {
  echo "FAIL: dispatch must call the codex egress function exactly once" >&2
  exit 1
}
grep -Fq 'branch_arg=$(printf '\''%q'\'' "$branch_name")' "$dispatch" || {
  echo "FAIL: measured branch is not shell-quoted" >&2
  exit 1
}
grep -Fq 'git push origin -- $branch_arg' "$dispatch" || {
  echo "FAIL: measured push command does not use the quoted branch and --" >&2
  exit 1
}

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-brief-egress.$$"
mkdir -p "$work/repo"
trap 'rm -rf "$work"' EXIT

git -C "$work/repo" init -q
git -C "$work/repo" checkout -q -b worker-push-authorization
git -C "$work/repo" remote add origin https://token:secret@github.com/baksohyeon/mogui-ADE-orchestrator.git

run_case() {
  local runtime="$1" selector="$2" stderr_file="$work/stderr"
  local script_file="$work/run.sh"
  {
    echo 'set -u'
    printf 'RUNTIME=%q\n' "$runtime"
    printf 'WORKTREE=%q\n' "$selector"
    echo 'SPEC="base brief"'
    printf '%s\n' "$remote_fn"
    printf '%s\n' "$egress_fn"
    echo 'append_codex_authorized_egress'
    printf 'printf "SPEC=<%%s>\\n" "$SPEC"\n'
  } > "$script_file"
  bash "$script_file" 2>"$stderr_file"
}

measured=$(run_case codex "path:$work/repo")
expected="SPEC=<base brief

Authorized egress for this worker (owner's repository): The owner authorizes this worker to run \`git push origin -- worker-push-authorization\` to \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`, with configured push destination(s) \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`, which is the owner's own repository and this worktree's \`origin\`, and \`gh pr create\`, \`gh pr edit\`, \`gh pr comment\` and \`gh api graphql\` (read) on \`baksohyeon/mogui-ADE-orchestrator\`. No other network write is authorized.>"
[ "$measured" = "$expected" ] || {
  echo "FAIL: measured codex dispatch did not include the branch, origin URL, and owner/repo" >&2
  printf '  got: %s\n' "$measured" >&2
  exit 1
}
measured_warning=$(cat "$work/stderr")
[ -z "$measured_warning" ] || {
  echo "FAIL: measured origin printed an unmeasured warning" >&2
  printf '  got: %s\n' "$measured_warning" >&2
  exit 1
}
printf '%s' "$measured" | grep -Fq 'token:secret' && {
  echo "FAIL: credential-bearing origin leaked into the brief" >&2
  exit 1
}
echo "ok   : codex brief names the measured push and PR destination"

git -C "$work/repo" remote set-url --add --push origin git@github.com:baksohyeon/mogui-ADE-orchestrator.git
push_measured=$(run_case codex "path:$work/repo")
printf '%s' "$push_measured" | grep -Fq 'configured push destination(s) `git@github.com:baksohyeon/mogui-ADE-orchestrator.git`' || {
  echo "FAIL: configured push URL was not named in the brief" >&2
  printf '  got: %s\n' "$push_measured" >&2
  exit 1
}
echo "ok   : configured push URLs are named in the codex brief"

claude=$(run_case claude "path:$work/repo")
[ "$claude" = 'SPEC=<base brief>' ] || {
  echo "FAIL: non-codex brief changed: $claude" >&2
  exit 1
}
echo "ok   : non-codex brief is unchanged"

git -C "$work/repo" remote set-url origin https://gitlab.com/acme/tool.git
foreign=$(run_case codex "path:$work/repo")
expected_foreign="SPEC=<base brief

Authorized egress for this worker (owner's repository): the destination is unmeasured and no push is authorized.>"
[ "$foreign" = "$expected_foreign" ] || {
  echo "FAIL: non-GitHub origin did not remove push authorization" >&2
  printf '  got: %s\n' "$foreign" >&2
  exit 1
}
echo "ok   : non-GitHub origin is unmeasured"

git -C "$work/repo" remote remove origin
unmeasured=$(run_case codex "path:$work/repo")
expected_unmeasured="SPEC=<base brief

Authorized egress for this worker (owner's repository): the destination is unmeasured and no push is authorized.>"
[ "$unmeasured" = "$expected_unmeasured" ] || {
  echo "FAIL: unmeasured origin did not remove push authorization" >&2
  printf '  got: %s\n' "$unmeasured" >&2
  exit 1
}
warning=$(cat "$work/stderr")
[ "$warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: unmeasured origin did not print exactly one warning line" >&2
  printf '  got: %s\n' "$warning" >&2
  exit 1
}
echo "ok   : unmeasured origin denies push authorization and prints one warning"

mutant=${egress_fn/'[ "$RUNTIME" = codex ] || return 0'/'return 0'}
[ "$mutant" != "$egress_fn" ] || { echo "FAIL: codex guard mutant did not change the source" >&2; exit 1; }
mutant_script="$work/mutant.sh"
{
  echo 'set -u'
  printf 'RUNTIME=codex\nWORKTREE=%q\nSPEC="base brief"\n' "path:$work/repo"
  printf '%s\n' "$remote_fn"
  printf '%s\n' "$mutant"
  echo 'append_codex_authorized_egress'
  printf 'printf "%%s\\n" "$SPEC"\n'
} > "$mutant_script"
mutant_out=$(bash "$mutant_script")
[ "$mutant_out" = 'base brief' ] || {
  echo "FAIL: failability: codex guard mutant still changed the brief" >&2
  exit 1
}
echo "ok   : failability: restoring the non-codex guard leaves the codex brief unmodified"
