#!/usr/bin/env bash
# Regression checks for agy's measured trustedWorkspaces settings entry.
set -u

script_dir="$(cd "$(dirname "$0")" && pwd)"
script="$script_dir/../../scripts/agy-worker-pretrust"
if [ ! -x "$script" ]; then
  echo "SKIP agy-worker-pretrust source is supplied by the runtime checkout"
  exit 0
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fake_config_home="$work/home/.gemini"
settings_dir="$fake_config_home/antigravity-cli"
settings_path="$settings_dir/settings.json"
workspace="$work/worktree"
existing_workspace="$work/existing"
mkdir -p "$settings_dir" "$workspace" "$existing_workspace"
printf '{\n  "keep": true,\n  "trustedWorkspaces": [%s]\n}\n' \
  "$(printf '%s' "$existing_workspace" | jq -Rsa .)" >"$settings_path"

out=$(AGY_CONFIG_HOME="$fake_config_home" "$script" "$workspace" 2>&1)
status=$?
if [ "$status" -ne 0 ] \
  || ! printf '%s\n' "$out" | grep -Fq 'Summary: 1 added, 0 updated, 0 already trusted' \
  || ! jq -e --arg workspace "$workspace" \
    '.keep == true and (.trustedWorkspaces | index($workspace)) != null and (all(.trustedWorkspaces[]; type == "string"))' \
    "$settings_path" >/dev/null; then
  echo "FAIL: agy pre-trust did not add the exact worktree to trustedWorkspaces" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : agy pre-trust adds one exact trustedWorkspaces entry"

before_second="$work/settings.before-second.json"
cp "$settings_path" "$before_second"
out=$(AGY_CONFIG_HOME="$fake_config_home" "$script" "$workspace" 2>&1)
status=$?
if [ "$status" -ne 0 ] \
  || ! printf '%s\n' "$out" | grep -Fq 'Summary: 0 added, 0 updated, 1 already trusted' \
  || ! cmp -s "$before_second" "$settings_path"; then
  echo "FAIL: agy pre-trust second run changed an already trusted settings file" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : agy pre-trust is idempotent"

# Failability: removing the atomic replacement must leave the expected trust
# entry absent, so the test fails if the script reports success without writing.
mutant="$work/agy-worker-pretrust-mutant"
sed 's/^os\.replace(tmp_path, target_path)$/# mutant: skip the settings write/' "$script" >"$mutant"
chmod +x "$mutant"
mutant_config_home="$work/mutant-home/.gemini"
mutant_settings_dir="$mutant_config_home/antigravity-cli"
mutant_settings_path="$mutant_settings_dir/settings.json"
mkdir -p "$mutant_settings_dir"
printf '{"trustedWorkspaces": []}\n' >"$mutant_settings_path"
mutant_out=$(AGY_CONFIG_HOME="$mutant_config_home" "$mutant" "$workspace" 2>&1)
mutant_status=$?
if [ "$mutant_status" -ne 0 ] \
  || jq -e --arg workspace "$workspace" \
    '(.trustedWorkspaces | index($workspace)) != null' "$mutant_settings_path" >/dev/null 2>&1; then
  echo "FAIL: failability mutant that skips the write was not caught" >&2
  printf '%s\n' "$mutant_out" >&2
  exit 1
fi
echo "ok   : failability: skipping the settings write leaves the expected trust entry absent"
