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
  python3 - "$path" <<'PY' | HOME="$TMP/home" MOGUI_INSTANCE_RUNTIME_CONFIG="${MOGUI_INSTANCE_RUNTIME_CONFIG:-$TMP/runtime.json}" MOGUI_HOOK_FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-$TMP/logs/fire.jsonl}" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

run_file_config() {
  local config="$1" path="$2"
  python3 - "$path" <<'PY' | HOME="$TMP/home" MOGUI_INSTANCE_RUNTIME_CONFIG="$config" MOGUI_HOOK_FIRE_LOG="$TMP/logs/fire.jsonl" "$HOOK" >/dev/null 2>"$TMP/stderr"
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

run_bash() {
  local command="$1"
  python3 - "$command" <<'PY' | HOME="$TMP/home" MOGUI_INSTANCE_RUNTIME_CONFIG="${MOGUI_INSTANCE_RUNTIME_CONFIG:-$TMP/runtime.json}" MOGUI_HOOK_FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-$TMP/logs/fire.jsonl}" "$HOOK" >/dev/null 2>"$TMP/stderr"
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
expect_blocked git-add run_bash "git -C $product add file.txt"
expect_blocked git-work-tree run_bash "git --git-dir=$TMP/repo.git --work-tree=$product add file.txt"
expect_blocked symlink-path run_file "$link/file.txt"
expect_allowed outside-read run_bash "printf ok > $ops/file.txt"

if [ ! -s "$TMP/logs/fire.jsonl" ]; then
  echo "FAIL: MOGUI_HOOK_FIRE_LOG was ignored" >&2
  exit 1
fi

printf '{"product_repo":"relative/product"}\n' >"$TMP/bad-schema.json"
expect_blocked bad-schema run_file_config "$TMP/bad-schema.json" "$ops/file.txt"
expect_blocked missing-config run_file_config "$TMP/missing.json" "$ops/file.txt"

echo "product-path-guard regression tests passed"
