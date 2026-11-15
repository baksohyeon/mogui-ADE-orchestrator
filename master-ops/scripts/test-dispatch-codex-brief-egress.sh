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
markdown_fn=$(awk '$0=="markdown_code_span() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
[ -n "$markdown_fn" ] || { echo "FAIL: could not extract Markdown code-span helper" >&2; exit 1; }
alignment_fn=$(awk '$0=="validate_reused_worktree_alignment() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
[ -n "$alignment_fn" ] || { echo "FAIL: could not extract reused-terminal alignment helper" >&2; exit 1; }
call_site=$(awk '$0=="validate_reused_worktree_alignment"{f=1} f{print} f&&$0=="append_codex_authorized_egress"{exit}' "$dispatch")
[ -n "$call_site" ] || { echo "FAIL: could not extract reused-terminal alignment call site" >&2; exit 1; }
case "$call_site" in
  *fail_after_tracker_claim*) echo "FAIL: reused-terminal alignment call site still blocks dispatch" >&2; exit 1;;
esac
resolve_fn=$(awk '$0=="resolve_product_repo_arg() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
[ -n "$resolve_fn" ] || { echo "FAIL: could not extract product-repository resolver" >&2; exit 1; }

work="${TMPDIR:-/tmp}/mogui-dispatch-codex-brief-egress.$$"
mkdir -p "$work/repo" "$work/other"
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
    printf '%s\n' "$markdown_fn"
    printf '%s\n' "$egress_fn"
    echo 'append_codex_authorized_egress'
    printf 'printf "SPEC=<%%s>\\n" "$SPEC"\n'
  } > "$script_file"
  bash "$script_file" 2>"$stderr_file"
}

run_call_site() {
  local runtime="$1" terminal_path="$2" terminal_identity="$3" stderr_file="$work/call-site-stderr"
  local script_file="$work/call-site.sh"
  {
    echo 'set -u'
    printf 'RUNTIME=%q\n' "$runtime"
    printf 'TERMINAL=term_x\nWORKTREE=%q\n' "path:$work/repo"
    echo 'SPEC="base brief"'
    printf 'terminal_worktree_path() { printf "%%s\\n" %q; }\n' "$terminal_path"
    printf 'terminal_worktree_identity() { printf "%%s\\n" %q; }\n' "$terminal_identity"
    printf '%s\n' "$remote_fn"
    printf '%s\n' "$markdown_fn"
    printf '%s\n' "$alignment_fn"
    printf '%s\n' "$egress_fn"
    printf '%s\n' "$call_site"
    printf 'printf "SPEC=<%%s>\\n" "$SPEC"\n'
  } > "$script_file"
  bash "$script_file" 2>"$stderr_file"
}

measured=$(run_case codex "path:$work/repo")
expected="SPEC=<base brief

Authorized egress for this worker (owner's repository): The owner authorizes this worker to run \`git push origin -- worker-push-authorization\` to \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`, with configured push destination(s) \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`, which is the owner's own repository and this worktree's \`origin\`, and \`gh pr create\`, \`gh pr edit\`, \`gh pr comment\` and read-only \`gh api graphql\` queries on \`baksohyeon/mogui-ADE-orchestrator\`. GraphQL mutations and other network writes are not authorized.>"
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

alignment_unmeasured="SPEC=<base brief

Authorized egress for this worker (owner's repository): the destination is unmeasured and no push is authorized.>"
claude_call_site=$(run_call_site claude "$work/other" "")
[ "$claude_call_site" = 'SPEC=<base brief>' ] || {
  echo "FAIL: unmatched Claude redispatch was blocked or changed its brief" >&2
  printf '  got: %s\n' "$claude_call_site" >&2
  exit 1
}
[ -z "$(cat "$work/call-site-stderr")" ] || {
  echo "FAIL: unmatched Claude redispatch printed a Codex egress warning" >&2
  exit 1
}
echo "ok   : unmatched Claude redispatch proceeds without egress output"

codex_unmatched_call_site=$(run_call_site codex "$work/other" "")
[ "$codex_unmatched_call_site" = "$alignment_unmeasured" ] || {
  echo "FAIL: unmatched Codex redispatch did not deny push authorization" >&2
  printf '  got: %s\n' "$codex_unmatched_call_site" >&2
  exit 1
}
[ "$(cat "$work/call-site-stderr")" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: unmatched Codex redispatch did not print exactly one warning" >&2
  exit 1
}
echo "ok   : unmatched Codex redispatch proceeds with one unmeasured warning"

codex_matched_call_site=$(run_call_site codex "$work/repo" "")
printf '%s' "$codex_matched_call_site" | grep -Fq 'Authorized egress for this worker' || {
  echo "FAIL: matched Codex redispatch did not include the measured paragraph" >&2
  printf '  got: %s\n' "$codex_matched_call_site" >&2
  exit 1
}
[ -z "$(cat "$work/call-site-stderr")" ] || {
  echo "FAIL: matched Codex redispatch printed an unmeasured warning" >&2
  exit 1
}
echo "ok   : matched Codex redispatch receives the measured egress paragraph"

run_remote_parser() {
  local remote="$1"
  local script_file="$work/remote.sh"
  {
    echo 'set -u'
    printf '%s\n' "$remote_fn"
    printf 'github_remote_metadata %q\n' "$remote"
  } > "$script_file"
  bash "$script_file"
}

ssh_metadata=$(run_remote_parser 'ssh://user@github.com:2222/owner/ssh-repo.git')
[ "$ssh_metadata" = $'ssh://github.com:2222/owner/ssh-repo.git\towner/ssh-repo\tssh://user@github.com:2222/owner/ssh-repo.git' ] || {
  echo "FAIL: SSH user and port were not preserved in validated metadata" >&2
  printf '  got: %s\n' "$ssh_metadata" >&2
  exit 1
}
echo "ok   : SSH metadata preserves the validated user and port without exposing them in display"

run_code_span() {
  local content="$1"
  local script_file="$work/code-span.sh"
  {
    echo 'set -u'
    printf '%s\n' "$markdown_fn"
    printf 'markdown_code_span %q\n' "$content"
  } > "$script_file"
  bash "$script_file"
}

make_fixture_repo() {
  local path="$1" remote="$2"
  mkdir -p "$path"
  git -C "$path" init -q
  git -C "$path" remote add origin "$remote"
}

https_repo="$work/https-repo"
ssh_repo="$work/ssh-repo"
dot_repo="$work/dot-repo"
make_fixture_repo "$https_repo" 'https://user:token@github.com/owner/https-repo.git'
make_fixture_repo "$ssh_repo" 'ssh://user@github.com:2222/owner/ssh-repo.git'
make_fixture_repo "$dot_repo" 'https://github.com/owner/.github'
runtime_config="$work/instance-runtime.json"
printf '{"product_repositories":["%s","%s","%s"]}\n' "$https_repo" "$ssh_repo" "$dot_repo" > "$runtime_config"

run_resolver() {
  local script_file="$work/resolve.sh"
  {
    echo 'set -u'
    printf 'INSTANCE_RUNTIME_CONFIG=%q\n' "$runtime_config"
    printf '%s\n' "$remote_fn"
    printf '%s\n' "$resolve_fn"
    echo 'resolve_product_repo_arg'
  } > "$script_file"
  bash "$script_file"
}

resolved=$(run_resolver)
[ "$resolved" = '["owner/https-repo", "owner/ssh-repo", "owner/.github"]' ] || {
  echo "FAIL: product-repository resolver rejected a supported URL or legal .github repository" >&2
  printf '  got: %s\n' "$resolved" >&2
  exit 1
}
case "$resolved" in
  *token*|*user@*)
    echo "FAIL: product-repository resolver leaked remote credentials" >&2
    exit 1
    ;;
esac
echo "ok   : resolver accepts credential-bearing HTTPS, user/port SSH, and .github repositories"

git -C "$work/repo" config --unset-all remote.origin.pushurl 2>/dev/null || true
git -C "$work/repo" remote set-url origin 'https://token:secret@github.com/owner/.github'
dot_brief=$(run_case codex "path:$work/repo")
printf '%s' "$dot_brief" | grep -Fq 'on `owner/.github`' || {
  echo "FAIL: .github repository was not named in the codex brief" >&2
  printf '  got: %s\n' "$dot_brief" >&2
  exit 1
}
echo "ok   : .github repository is measured in the codex brief"

git -C "$work/repo" remote set-url origin 'ssh://user@github.com:2222/owner/ssh-repo.git'
ssh_brief=$(run_case codex "path:$work/repo")
printf '%s' "$ssh_brief" | grep -Fq 'to `ssh://github.com:2222/owner/ssh-repo.git`' || {
  echo "FAIL: SSH port was not preserved in the sanitized brief destination" >&2
  printf '  got: %s\n' "$ssh_brief" >&2
  exit 1
}
case "$ssh_brief" in
  *'user@'*|*'token'*)
    echo "FAIL: SSH user or credential leaked into the brief" >&2
    exit 1
    ;;
esac
echo "ok   : SSH port is named without userinfo in the codex brief"

git -C "$work/repo" remote set-url origin 'https://token:secret@github.com/baksohyeon/mogui-ADE-orchestrator.git'
git -C "$work/repo" -c user.name=fixture -c user.email=fixture@example.invalid commit --allow-empty -qm fixture
leading_span=$(run_code_span '`leading')
[[ "$leading_span" == '`` '* ]] || {
  echo "FAIL: leading backtick did not receive Markdown code-span padding" >&2
  printf '  got: %s\n' "$leading_span" >&2
  exit 1
}
trailing_span=$(run_code_span 'trailing`')
[[ "$trailing_span" == *'trailing` '* ]] || {
  echo "FAIL: trailing backtick did not receive Markdown code-span padding" >&2
  printf '  got: %s\n' "$trailing_span" >&2
  exit 1
}
ending_branch=$'worker-ending-`'
git -C "$work/repo" branch -m "$ending_branch"
ending_branch_arg=$(printf '%q' "$ending_branch")
ending_code=$(run_code_span "git push origin -- $ending_branch_arg")
ending=$(run_case codex "path:$work/repo")
[[ "$ending" == *"run $ending_code to \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`"* ]] || {
  echo "FAIL: ending backtick branch broke the Markdown code span or hid the URL" >&2
  printf '  got: %s\n' "$ending" >&2
  exit 1
}
starting_branch=$'`worker-starting'
git -C "$work/repo" branch -m "$starting_branch"
starting_branch_arg=$(printf '%q' "$starting_branch")
starting_code=$(run_code_span "git push origin -- $starting_branch_arg")
starting=$(run_case codex "path:$work/repo")
[[ "$starting" == *"run $starting_code to \`https://github.com/baksohyeon/mogui-ADE-orchestrator.git\`"* ]] || {
  echo "FAIL: starting backtick branch broke the Markdown code span or hid the URL" >&2
  printf '  got: %s\n' "$starting" >&2
  exit 1
}
echo "ok   : leading and trailing backticks use safe Markdown code spans"

expected_foreign="SPEC=<base brief

Authorized egress for this worker (owner's repository): the destination is unmeasured and no push is authorized.>"
git -C "$work/repo" checkout -q --detach
detached=$(run_case codex "path:$work/repo")
[ "$detached" = "$expected_foreign" ] 2>/dev/null || {
  echo "FAIL: detached HEAD did not remove push authorization" >&2
  printf '  got: %s\n' "$detached" >&2
  exit 1
}
detached_warning=$(cat "$work/stderr")
[ "$detached_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: detached HEAD did not print exactly one warning" >&2
  printf '  got: %s\n' "$detached_warning" >&2
  exit 1
}
git -C "$work/repo" checkout -q "$starting_branch"
reused=$(run_case codex "")
[ "$reused" = "$expected_foreign" ] || {
  echo "FAIL: reused pane without a worktree path did not remove push authorization" >&2
  printf '  got: %s\n' "$reused" >&2
  exit 1
}
reused_warning=$(cat "$work/stderr")
[ "$reused_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: reused pane did not print exactly one warning" >&2
  printf '  got: %s\n' "$reused_warning" >&2
  exit 1
}
echo "ok   : detached and reused panes deny unmeasured push authorization"

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

git -C "$work/repo" config --unset-all remote.origin.pushurl 2>/dev/null || true
git -C "$work/repo" remote set-url origin 'https://token:secret@github.com/Owner/Repo.git'
git -C "$work/repo" remote set-url --add --push origin git@github.com:owner/repo.git
casefold_measured=$(run_case codex "path:$work/repo")
printf '%s' "$casefold_measured" | grep -Fq 'configured push destination(s) `git@github.com:owner/repo.git`' || {
  echo "FAIL: case-insensitive GitHub identities were rejected" >&2
  printf '  got: %s\n' "$casefold_measured" >&2
  exit 1
}
[ -z "$(cat "$work/stderr")" ] || {
  echo "FAIL: case-insensitive GitHub identities printed an unmeasured warning" >&2
  exit 1
}
echo "ok   : GitHub owner and repository identities compare case-insensitively"

git -C "$work/repo" config --unset-all remote.origin.pushurl 2>/dev/null || true
git -C "$work/repo" remote set-url origin 'https://token:secret@github.com/owner/repo.git'
git -C "$work/repo" remote set-url --add --push origin git@github.com:owner/other.git
mismatched_push=$(run_case codex "path:$work/repo")
[ "$mismatched_push" = "$expected_foreign" ] || {
  echo "FAIL: a push URL for another repository retained push authorization" >&2
  printf '  got: %s\n' "$mismatched_push" >&2
  exit 1
}
mismatched_push_warning=$(cat "$work/stderr")
[ "$mismatched_push_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: a mismatched push URL did not print exactly one warning" >&2
  printf '  got: %s\n' "$mismatched_push_warning" >&2
  exit 1
}
echo "ok   : a push URL for another repository is unmeasured"

git -C "$work/repo" config --unset-all remote.origin.pushurl 2>/dev/null || true
git -C "$work/repo" remote set-url origin https://gitlab.com/acme/tool.git
foreign=$(run_case codex "path:$work/repo")
[ "$foreign" = "$expected_foreign" ] || {
  echo "FAIL: non-GitHub origin did not remove push authorization" >&2
  printf '  got: %s\n' "$foreign" >&2
  exit 1
}
echo "ok   : non-GitHub origin is unmeasured"

git -C "$work/repo" remote set-url origin https://github.com/owner/repo%20name.git
invalid_slug=$(run_case codex "path:$work/repo")
invalid_slug_warning=$(cat "$work/stderr")
[ "$invalid_slug" = "$expected_foreign" ] || {
  echo "FAIL: unsafe GitHub slug did not remove push authorization" >&2
  printf '  got: %s\n' "$invalid_slug" >&2
  exit 1
}
[ "$invalid_slug_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: unsafe GitHub slug did not print the unmeasured warning" >&2
  printf '  got: %s\n' "$invalid_slug_warning" >&2
  exit 1
}
echo "ok   : unsafe GitHub slug is unmeasured"

git -C "$work/repo" remote set-url origin 'https://github.com@evil.com/owner/repo.git'
invalid_host=$(run_case codex "path:$work/repo")
invalid_host_warning=$(cat "$work/stderr")
[ "$invalid_host" = "$expected_foreign" ] || {
  echo "FAIL: a GitHub-looking userinfo host retained push authorization" >&2
  printf '  got: %s\n' "$invalid_host" >&2
  exit 1
}
[ "$invalid_host_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
  echo "FAIL: invalid host did not print exactly one warning" >&2
  printf '  got: %s\n' "$invalid_host_warning" >&2
  exit 1
}
echo "ok   : invalid GitHub host is unmeasured"

for repository_component in . ..; do
  git -C "$work/repo" remote set-url origin "https://github.com/owner/$repository_component"
  dot_repository=$(run_case codex "path:$work/repo")
  dot_repository_warning=$(cat "$work/stderr")
  [ "$dot_repository" = "$expected_foreign" ] || {
    echo "FAIL: repository component '$repository_component' retained push authorization" >&2
    printf '  got: %s\n' "$dot_repository" >&2
    exit 1
  }
  [ "$dot_repository_warning" = 'WARNING: codex authorized egress destination is unmeasured; no push is authorized.' ] || {
    echo "FAIL: repository component '$repository_component' did not print exactly one warning" >&2
    printf '  got: %s\n' "$dot_repository_warning" >&2
    exit 1
  }
done
echo "ok   : dot and dot-dot repository components are unmeasured"

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
