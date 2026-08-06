#!/bin/bash
# Regression coverage for every product-path guard bypass class.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOOK="$ROOT/scripts/hooks/product-path-guard.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

product="$TMP/workspace/product"
ops="$TMP/workspace/ops"
link="$TMP/workspace/product-link"
mkdir -p "$product" "$ops" "$TMP/home" "$TMP/logs"
ln -s "$product" "$link"
printf '{"master_host_runtime":"claude","product_repo":"%s"}\n' "$product" >"$TMP/runtime.json"

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

expect_blocked() {
  local label="$1" rc
  shift
  "$@"; rc=$?
  [ "$rc" -eq 2 ] || { echo "FAIL: $label rc=$rc" >&2; cat "$TMP/stderr" >&2; exit 1; }
  grep -q BLOCKED "$TMP/stderr" || { echo "FAIL: $label had no BLOCKED" >&2; exit 1; }
  echo "PASS: $label"
}

expect_allowed() {
  local label="$1" rc
  shift
  "$@"; rc=$?
  [ "$rc" -eq 0 ] || { echo "FAIL: $label rc=$rc" >&2; cat "$TMP/stderr" >&2; exit 1; }
  echo "PASS: $label"
}

expect_blocked file-path run_file "$product/file.txt"
expect_blocked bash-redirection run_bash "echo bad > $product/file.txt"
expect_blocked bash-cd-and-write run_bash "cd $product && echo bad > file.txt"
expect_blocked bash-cp run_bash "cp /dev/null $product/file.txt"
expect_blocked bash-mv run_bash "mv $ops/file.txt $product/file.txt"
expect_blocked bash-tee run_bash "tee $product/file.txt"
expect_blocked bash-opaque-wrapper run_bash "bash -c 'echo bad > $product/file.txt'"
expect_blocked bash-hidden-relative-wrapper run_bash "sh -c 'cd $product && cp /dev/null file.txt'"
expect_blocked bash-combined-redirection run_bash "echo bad >& $product/file.txt"
expect_blocked bash-relative-working-directory run_bash "echo bad > file.txt" "$product"
expect_allowed legacy-read-only run_bash "ls" "$product"
printf 'ls\nrg\n' >"$TMP/allowlist.txt"
expect_allowed measured-read-only run_bash_strict "ls" "$product"
expect_blocked strict-unmeasured-read-only run_bash_strict "cat" "$product"
expect_blocked strict-write-capable-argument run_bash_strict "find . -exec touch file.txt \\;" "$product"
expect_allowed strict-read-search-flag run_bash_strict "rg -i needle" "$product"
expect_blocked git-remote-mutation run_bash "git -C $product remote set-url origin https://example.invalid/repo"
expect_blocked git-diff-output run_bash "git -C $product diff --output=result.txt"
expect_blocked sed-relative-product-target run_bash "sed -i $product/file.txt"
expect_allowed git-remote-show-argument run_bash "git -C $product remote show add"
expect_blocked find-exec-shell-wrapper run_bash "find . -exec sh -c 'touch $product/nested.txt' \\;" "$ops"
expect_blocked git-remote-verbose-update run_bash "git -C $product remote -v update"
expect_blocked git-diff-output-equals run_bash "git -C $ops diff --output=$product/result.txt"
expect_allowed event-log-failure-does-not-block run_bash_event_failure "ls" "$product"
expect_blocked git-add run_bash "git -C $product add file.txt"
expect_blocked git-work-tree run_bash "git --git-dir=$TMP/repo.git --work-tree=$product add file.txt"
expect_blocked symlink-path run_file "$link/file.txt"
expect_allowed outside-read run_bash "printf ok > $ops/file.txt"

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
expected = {"ts", "hook", "event", "cwd", "runtime_hint", "session_kind"}
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        record = json.loads(line)
        if set(record) != expected:
            raise SystemExit("FAIL: hook-fire-log schema changed")
PY

printf '{"product_repo":"relative/product"}\n' >"$TMP/bad-schema.json"
expect_blocked bad-schema run_file_config "$TMP/bad-schema.json" "$ops/file.txt"
expect_blocked missing-config run_file_config "$TMP/missing.json" "$ops/file.txt"

echo "product-path-guard regression tests passed"
