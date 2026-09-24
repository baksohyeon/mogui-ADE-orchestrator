#!/bin/bash
# Regression coverage for every product-path guard bypass class.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOOK="$ROOT/scripts/hooks/product-path-guard.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

product="$TMP/workspace/product"
product2="$TMP/workspace/product-two"
product_legacy="$TMP/workspace/product-legacy"
ops="$TMP/workspace/ops"
link="$TMP/workspace/product-link"
mkdir -p "$product" "$product2" "$product_legacy" "$ops" "$TMP/home" "$TMP/logs"
ln -s "$product" "$link"
product_real=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$product")
printf '{"master_host_runtime":"claude","product_repositories":["%s","%s"]}\n' "$product" "$product2" >"$TMP/runtime.json"
# Legacy one-entry string form must stay covered by a valid fixture: the
# array fixture above exercises only product_repositories, and the only
# other product_repo fixture (below) is intentionally malformed.
printf '{"master_host_runtime":"claude","product_repo":"%s"}\n' "$product_legacy" >"$TMP/runtime-legacy.json"

run_file() {
  local path="$1"
  python3 - "$path" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$TMP/runtime.json" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

run_file_config() {
  local config="$1" path="$2"
  python3 - "$path" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$config" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

run_file_override() {
  local path="$1"
  python3 - "$path" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=1 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$TMP/runtime.json" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

run_bash() {
  local command="$1"
  local working_directory="${2:-.}"
  python3 - "$command" "$working_directory" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_PRODUCT_GUARD_ALLOWLIST=/dev/null MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$TMP/runtime.json" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1], "working_directory": sys.argv[2] if len(sys.argv) > 2 else "."}}))
PY
}

run_bash_strict() {
  local command="$1"
  local working_directory="${2:-.}"
  python3 - "$command" "$working_directory" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1 MOGUI_PRODUCT_GUARD_ALLOWLIST="$TMP/allowlist.txt" MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$TMP/runtime.json" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1], "working_directory": sys.argv[2] if len(sys.argv) > 2 else "."}}))
PY
}

run_bash_event_failure() {
  local command="$1"
  local working_directory="${2:-.}"
  python3 - "$command" "$working_directory" <<'PY' | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_EVENT_LOG=/dev/null/event-log.jsonl MOGUI_INSTANCE_RUNTIME_CONFIG="$TMP/runtime.json" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1], "working_directory": sys.argv[2] if len(sys.argv) > 2 else "."}}))
PY
}

run_bash_default_config() {
  local command="$1"
  local working_directory="${2:-.}"
  python3 - "$command" "$working_directory" <<'PY' 2>/dev/null | HOME="$TMP/home" MOGUI_INSTANCE_RUNTIME_CONFIG= MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED=0 MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1], "working_directory": sys.argv[2] if len(sys.argv) > 2 else "."}}))
PY
}

run_raw_payload() {
  local payload="$1"
  local fail_closed="${2:-0}"
  local config="${3:-$TMP/runtime.json}"
  local hook="${4:-$HOOK}"
  printf '%s' "$payload" | HOME="$TMP/home" MOGUI_INLINE_EDIT_OVERRIDE=0 MOGUI_PRODUCT_GUARD_FAIL_CLOSED="$fail_closed" MOGUI_EVENT_LOG="$TMP/home/.mogui/event-log.jsonl" MOGUI_INSTANCE_RUNTIME_CONFIG="$config" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$hook" >/dev/null 2>"$TMP/stderr"
}

expect_blocked() {
  local label="$1" rc
  shift
  local before after
  before=$(fire_count)
  "$@"; rc=$?
  after=$(fire_count)
  [ "$rc" -eq 2 ] || { echo "FAIL: $label rc=$rc" >&2; cat "$TMP/stderr" >&2; exit 1; }
  [ $((after - before)) -eq 1 ] || { echo "FAIL: $label expected exactly one new fire-log record, before=$before after=$after" >&2; exit 1; }
  grep -q BLOCKED "$TMP/stderr" || { echo "FAIL: $label had no BLOCKED" >&2; exit 1; }
  echo "PASS: $label"
}

expect_allowed() {
  local label="$1" rc
  shift
  local before after
  before=$(fire_count)
  "$@"; rc=$?
  after=$(fire_count)
  [ "$rc" -eq 0 ] || { echo "FAIL: $label rc=$rc" >&2; cat "$TMP/stderr" >&2; exit 1; }
  [ $((after - before)) -eq 1 ] || { echo "FAIL: $label expected exactly one new fire-log record, before=$before after=$after" >&2; exit 1; }
  echo "PASS: $label"
}

fire_count() {
  if [ -f "$TMP/logs/fire.jsonl" ]; then
    wc -l < "$TMP/logs/fire.jsonl"
  else
    echo 0
  fi
}

last_verdict() {
  python3 - "$TMP/logs/fire.jsonl" <<'PY'
import json, sys
lines = [ln.strip() for ln in open(sys.argv[1], encoding="utf-8") if ln.strip()]
print(json.loads(lines[-1]).get("verdict", ""))
PY
}

expect_verdict() {
  local expected="$1" label="$2" got
  got="$(last_verdict 2>/dev/null || true)"
  [ "$got" = "$expected" ] || { echo "FAIL: $label verdict expected $expected got ${got:-<none>}" >&2; exit 1; }
  echo "PASS: $label verdict=$expected"
}

expect_invalid_input_blocked() {
  local label="$1"
  shift
  expect_blocked "$label" "$@"
  grep -q "invalid hook input" "$TMP/stderr" || { echo "FAIL: $label missing invalid hook input message" >&2; cat "$TMP/stderr" >&2; exit 1; }
  expect_verdict block "$label"
}

expect_blocked file-path run_file "$product/file.txt"
expect_verdict block file-path
expect_allowed file-path-override run_file_override "$product/file.txt"
expect_verdict override file-path-override
expect_blocked bash-redirection run_bash "echo bad > $product/file.txt"
expect_verdict block bash-redirection
expect_blocked bash-cd-and-write run_bash "cd $product && echo bad > file.txt"
expect_verdict block bash-cd-and-write
expect_blocked bash-cp run_bash "cp /dev/null $product/file.txt"
expect_verdict block bash-cp
expect_blocked bash-mv run_bash "mv $ops/file.txt $product/file.txt"
expect_verdict block bash-mv
expect_blocked bash-tee run_bash "tee $product/file.txt"
expect_verdict block bash-tee
expect_blocked bash-dd-of-equals run_bash "dd if=/dev/null of=$product/file.txt"
expect_verdict block bash-dd-of-equals
expect_blocked bash-opaque-wrapper run_bash "bash -c 'echo bad > $product/file.txt'"
expect_verdict block bash-opaque-wrapper
expect_blocked bash-hidden-relative-wrapper run_bash "sh -c 'cd $product_real && cp /dev/null file.txt'"
expect_verdict block bash-hidden-relative-wrapper
expect_blocked bash-combined-redirection run_bash "echo bad >& $product/file.txt"
expect_verdict block bash-combined-redirection
expect_blocked bash-relative-working-directory run_bash "echo bad > file.txt" "$product"
expect_verdict block bash-relative-working-directory
expect_allowed legacy-python3-c-outside-root run_bash "python3 -c 'print(1)'" "$ops"
expect_verdict pass legacy-python3-c-outside-root
expect_blocked strict-unparseable-input-block run_raw_payload "not json" 1
expect_verdict block strict-unparseable-input-block
expect_invalid_input_blocked strict-json-array-input-block run_raw_payload "[]" 1
expect_invalid_input_blocked strict-json-string-input-block run_raw_payload '"str"' 1
expect_invalid_input_blocked strict-json-null-input-block run_raw_payload "null" 1
expect_invalid_input_blocked strict-tool-input-null-block run_raw_payload '{"tool_input": null}' 1

MUTANT_HOOK="$TMP/product-path-guard-mutant.sh"
python3 - "$HOOK" "$MUTANT_HOOK" <<'PY'
import pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
needle = (
    "if ! printf '%s' \"$input\" | python3 -c 'import json,sys; "
    "payload=json.load(sys.stdin); tool=payload.get(\"tool_input\") if isinstance(payload, dict) else None; "
    "raise SystemExit(0 if isinstance(payload, dict) and isinstance(tool, dict) else 1)' >/dev/null 2>&1; then"
)
replacement = (
    "if ! printf '%s' \"$input\" | python3 -c 'import json,sys; json.load(sys.stdin); "
    "raise SystemExit(0)' >/dev/null 2>&1; then"
)
if needle not in source:
    raise SystemExit("mutant patch anchor not found")
pathlib.Path(sys.argv[2]).write_text(source.replace(needle, replacement, 1), encoding="utf-8")
PY
if [ ! -f "$MUTANT_HOOK" ] || cmp -s "$HOOK" "$MUTANT_HOOK"; then
  echo "FAIL: mutant not generated" >&2
  exit 1
fi
chmod +x "$MUTANT_HOOK"

(
  expect_invalid_input_blocked failability-invalid-shape-load-order run_raw_payload "[]" 1 "$TMP/missing.json" "$MUTANT_HOOK"
)
mutant_exit=$?
(
  expect_invalid_input_blocked failability-invalid-shape-load-order run_raw_payload "[]" 1 "$TMP/missing.json" "$HOOK"
)
restored_exit=$?
[ "$mutant_exit" -eq 1 ] || { echo "FAIL: failability mutant exit expected 1 got $mutant_exit" >&2; exit 1; }
[ "$restored_exit" -eq 0 ] || { echo "FAIL: failability restored exit expected 0 got $restored_exit" >&2; exit 1; }
echo "PASS: failability mutant exit code $mutant_exit"
echo "PASS: failability restored exit code $restored_exit"

expect_allowed legacy-bash-c-outside-root run_bash "bash -c 'echo ok'" "$ops"
expect_verdict pass legacy-bash-c-outside-root
expect_blocked legacy-python3-root-token-non-c-arg run_bash "python3 $product_real/probe.py" "$ops"
expect_verdict block legacy-python3-root-token-non-c-arg
expect_blocked legacy-bash-c-relative-cd-into-root run_bash "bash -c 'cd ../product && cp /dev/null x.txt'" "$ops"
expect_verdict block legacy-bash-c-relative-cd-into-root
expect_blocked legacy-bash-c-relative-redirect-into-root run_bash "bash -c 'echo bad > ../product/x.txt'" "$ops"
expect_verdict block legacy-bash-c-relative-redirect-into-root
expect_blocked legacy-bash-c-relative-clobber-redirect-into-root run_bash "bash -c 'echo bad >| ../product/x2.txt'" "$ops"
expect_verdict block legacy-bash-c-relative-clobber-redirect-into-root
expect_blocked legacy-python3-c-inside-root run_bash "python3 -c 'print(1)'" "$product"
expect_verdict block legacy-python3-c-inside-root
expect_blocked strict-python3-c-outside-root run_bash_strict "python3 -c 'print(1)'" "$ops"
expect_verdict block strict-python3-c-outside-root
expect_allowed legacy-python3-c-redirection-outside-root run_bash "python3 -c 'print(1)' > /tmp/guard-probe.txt" "$ops"
expect_verdict pass legacy-python3-c-redirection-outside-root
expect_allowed legacy-read-only run_bash "ls" "$product"
expect_verdict pass legacy-read-only
printf 'ls\nrg\n' >"$TMP/allowlist.txt"
expect_allowed measured-read-only run_bash_strict "ls" "$product"
expect_verdict pass measured-read-only
expect_blocked strict-unmeasured-read-only run_bash_strict "cat" "$product"
expect_verdict block strict-unmeasured-read-only
expect_blocked strict-write-capable-argument run_bash_strict "find . -exec touch file.txt \\;" "$product"
expect_verdict block strict-write-capable-argument
expect_allowed strict-read-search-flag run_bash_strict "rg -i needle" "$product"
expect_verdict pass strict-read-search-flag
printf 'git apply\ngit checkout\ngit reset\ngit stash\ngit worktree\n' >>"$TMP/allowlist.txt"
expect_allowed strict-allowlisted-git-apply-check run_bash_strict "git -C $product apply --check patch.diff"
expect_verdict pass strict-allowlisted-git-apply-check
expect_blocked strict-apply-double-dash-check-bypass run_bash_strict "git -C $product apply -- --check"
expect_verdict block strict-apply-double-dash-check-bypass
expect_allowed strict-allowlisted-git-worktree-list run_bash_strict "git -C $product worktree list"
expect_verdict pass strict-allowlisted-git-worktree-list
expect_blocked strict-stash-message-list-bypass run_bash_strict "git -C $product stash --message list"
expect_verdict block strict-stash-message-list-bypass
expect_blocked strict-stash-show-output-flag run_bash_strict "git -C $product stash show --output result.patch"
expect_verdict block strict-stash-show-output-flag
expect_blocked strict-stash-show-output-equals run_bash_strict "git -C $product stash show --output=result.patch"
expect_verdict block strict-stash-show-output-equals
expect_blocked strict-git-dir-product-metadata-bypass run_bash_strict "git --git-dir=$product/.git --work-tree=$ops checkout -- ."
expect_verdict block strict-git-dir-product-metadata-bypass
expect_blocked git-remote-mutation run_bash "git -C $product remote set-url origin https://example.invalid/repo"
expect_verdict block git-remote-mutation
expect_blocked git-diff-output run_bash "git -C $product diff --output=result.txt"
expect_verdict block git-diff-output
expect_blocked strict-git-reset-hard run_bash_strict "git -C $product reset --hard"
expect_verdict block strict-git-reset-hard
expect_blocked sed-relative-product-target run_bash "sed -i $product/file.txt"
expect_verdict block sed-relative-product-target
expect_allowed git-remote-show-argument run_bash "git -C $product remote show add"
expect_verdict pass git-remote-show-argument
expect_blocked find-exec-shell-wrapper run_bash "find . -exec sh -c 'touch $product/nested.txt' \\;" "$ops"
expect_verdict block find-exec-shell-wrapper
expect_blocked git-remote-verbose-update run_bash "git -C $product remote -v update"
expect_verdict block git-remote-verbose-update
expect_blocked git-diff-output-equals run_bash "git -C $ops diff --output=$product/result.txt"
expect_verdict block git-diff-output-equals
expect_allowed event-log-failure-does-not-block run_bash_event_failure "ls" "$product"
expect_verdict pass event-log-failure-does-not-block
expect_blocked git-add run_bash "git -C $product add file.txt"
expect_verdict block git-add
expect_blocked git-work-tree run_bash "git --git-dir=$TMP/repo.git --work-tree=$product add file.txt"
expect_verdict block git-work-tree
expect_allowed cp-source-in-product-destination-outside run_bash "cp $product/source.txt $ops/out.txt" "$ops"
expect_verdict pass cp-source-in-product-destination-outside
expect_blocked install-flagged-destination-in-product run_bash "install -b $ops/source.txt $product/out.txt" "$ops"
expect_verdict block install-flagged-destination-in-product
expect_allowed install-source-in-product-destination-outside run_bash "install $product/source.txt $ops/out.txt" "$ops"
expect_verdict pass install-source-in-product-destination-outside
expect_allowed install-double-dash-literal-directory-token run_bash "install -- $product/source.txt --directory" "$ops"
expect_verdict pass install-double-dash-literal-directory-token
expect_allowed install-attached-suffix-value run_bash "install -Sd $product/source.txt $ops/out2.txt" "$ops"
expect_verdict pass install-attached-suffix-value
expect_blocked install-directory-single-target run_bash "install -d $product/newdir" "$ops"
expect_verdict block install-directory-single-target
expect_blocked install-directory-multi-target run_bash "install -d $ops/newdir $product/newdir2" "$ops"
expect_verdict block install-directory-multi-target
expect_blocked ln-source-in-product-destination-outside run_bash "ln $product/source.txt $ops/out.txt" "$ops"
expect_verdict block ln-source-in-product-destination-outside
expect_blocked ln-symbolic-source-in-product-destination-outside run_bash "ln -s $product/source.txt $ops/link.txt" "$ops"
expect_verdict block ln-symbolic-source-in-product-destination-outside
expect_blocked ln-single-source-in-product run_bash "ln $product/source.txt" "$ops"
expect_verdict block ln-single-source-in-product
expect_blocked symlink-path run_file "$link/file.txt"
expect_verdict block symlink-path
expect_allowed outside-read run_bash "printf ok > $ops/file.txt"
expect_verdict pass outside-read
expect_blocked file-path-repo-two run_file "$product2/file.txt"
expect_verdict block file-path-repo-two
expect_blocked bash-repo-two run_bash "cp /dev/null $product2/file.txt"
expect_verdict block bash-repo-two
expect_allowed outside-both-repos run_bash "printf ok > file-two.txt" "$ops"
expect_verdict pass outside-both-repos
expect_blocked legacy-string-config-file-path run_file_config "$TMP/runtime-legacy.json" "$product_legacy/file.txt"
expect_verdict block legacy-string-config-file-path
expect_allowed legacy-string-config-outside run_file_config "$TMP/runtime-legacy.json" "$ops/file.txt"
expect_verdict pass legacy-string-config-outside

if [ ! -s "$TMP/logs/fire.jsonl" ]; then
  echo "FAIL: MOGUI_HOOK_FIRE_LOG was ignored" >&2
  exit 1
fi
if [ ! -s "$TMP/home/.mogui/event-log.jsonl" ]; then
  echo "FAIL: event-log observation was not emitted" >&2
  exit 1
fi
python3 - "$TMP/home/.mogui/event-log.jsonl" <<'PY'
import json, sys
seen = set()
for line in open(sys.argv[1], encoding="utf-8"):
    record = json.loads(line)
    if record.get("event") == "product_path_guard":
        seen.add(record.get("tool_kind"))
        if record.get("tool_kind") not in {"bash", "file"}:
            raise SystemExit("FAIL: invalid product-path tool_kind")
if seen != {"bash", "file"}:
    raise SystemExit("FAIL: product-path tool_kind coverage incomplete")
PY
python3 - "$TMP/logs/fire.jsonl" <<'PY'
import json, sys
expected = {"ts", "hook", "event", "cwd", "runtime_hint", "session_kind", "verdict"}
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        record = json.loads(line)
        if set(record) != expected:
            raise SystemExit("FAIL: hook-fire-log schema changed")
PY

printf '{"product_repo":"relative/product"}\n' >"$TMP/bad-schema.json"
expect_blocked bad-schema run_file_config "$TMP/bad-schema.json" "$ops/file.txt"
expect_verdict block bad-schema
expect_blocked missing-config run_file_config "$TMP/missing.json" "$ops/file.txt"
expect_verdict block missing-config
printf '{"master_host_runtime":"claude","product_repositories":["%s"],"product_repo":"%s"}\n' "$product" "$product_legacy" >"$TMP/runtime-both.json"
expect_allowed both-fields-warning-outside run_file_config "$TMP/runtime-both.json" "$ops/file.txt"
expect_verdict pass both-fields-warning-outside
grep -q "configuration warning: product_repositories and product_repo are both set" "$TMP/stderr" || { echo "FAIL: both-fields-warning-outside missing configuration warning" >&2; cat "$TMP/stderr" >&2; exit 1; }
printf '{"master_host_runtime":"claude","product_repositories":["%s"],"product_repo":"relative/product"}\n' "$product" >"$TMP/runtime-both-malformed.json"
expect_blocked both-fields-malformed-legacy-blocked run_file_config "$TMP/runtime-both-malformed.json" "$ops/file.txt"
expect_verdict block both-fields-malformed-legacy-blocked
grep -q "cannot load product_repositories" "$TMP/stderr" || { echo "FAIL: both-fields-malformed-legacy-blocked missing load failure message" >&2; cat "$TMP/stderr" >&2; exit 1; }
expect_blocked unsubstituted-runtime-root-token run_bash_default_config "ls" "$ops"
expect_verdict block unsubstituted-runtime-root-token
grep -q "{{RUNTIME_ROOT}}" "$TMP/stderr" || { echo "FAIL: unsubstituted-runtime-root-token missing token name" >&2; exit 1; }
grep -q "MOGUI_INSTANCE_RUNTIME_CONFIG" "$TMP/stderr" || { echo "FAIL: unsubstituted-runtime-root-token missing override name" >&2; exit 1; }

echo "product-path-guard regression tests passed"
