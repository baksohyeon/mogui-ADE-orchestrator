#!/usr/bin/env bash
set -euo pipefail

fix=false
case "${1:-}" in
  "") ;;
  --fix) fix=true ;;
  *) printf 'Usage: %s [--fix]\n' "$0" >&2; exit 2 ;;
esac

failures=0
passes=0

pass() {
  passes=$((passes + 1))
  printf 'PASS %-14s %s\n' "$1" "$2"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL %-14s %s\n' "$1" "$2"
}

strip_ansi() {
  sed $'s/\033\\[[0-9;]*[[:alpha:]]//g'
}

orca_install_hint() {
  local install_command
  local install_source
  case "$(uname -s 2>/dev/null || printf unknown)" in
    Darwin)
      install_command='brew install --cask stablyai/orca/orca'
      install_source='install Orca with Homebrew'
      ;;
    Linux|MINGW*|MSYS*|CYGWIN*)
      install_command='download Orca from https://www.onorca.dev/download'
      install_source='download Orca from the official page'
      ;;
    *)
      install_command='install Orca from https://www.onorca.dev/download'
      install_source='install Orca from the official page'
      ;;
  esac
  printf 'install guidance: %s (%s)\n' "$install_command" "$install_source"
  printf '%s' 'follow-up: enable Settings > Orca CLI > Shell command'
}

# Resolve once, before the first Orca invocation. Never fall through to another binary.
if [[ -n "${ORCA_CLI_COMMAND:-}" ]]; then
  orca_command="$ORCA_CLI_COMMAND"
elif [[ -n "${ORCA_DEV_REPO_ROOT:-}" ]]; then
  orca_command="orca-dev"
else
  orca_command="orca"
fi

printf 'INFO resolved Orca CLI: %s\n' "$orca_command"

orca_ready=false
if [[ "${orca_command##*/}" != "orca" ]]; then
  fail "orca" "$orca_command is not supported by the runtime; expose the CLI as 'orca' before onboarding"
elif command -v "$orca_command" >/dev/null 2>&1; then
  status_output=""
  if status_output=$("$orca_command" status --json 2>&1); then
    if printf '%s\n' "$status_output" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
      pass "orca" "$orca_command status --json returned ok:true"
      orca_ready=true
    else
      fail "orca" "$orca_command status --json did not return ok:true; $(orca_install_hint)"
    fi
  else
    fail "orca" "$orca_command status --json failed; $(orca_install_hint)"
  fi
else
  fail "orca" "$orca_command is not available; $(orca_install_hint)"
fi

if [[ "$orca_ready" == true ]]; then
  orchestration_output=""
  orchestration_status=0
  orchestration_output=$("$orca_command" orchestration task-list --json 2>&1) || orchestration_status=$?
  if { [[ $orchestration_status -eq 0 ]] \
    && printf '%s\n' "$orchestration_output" \
      | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; } \
    || printf '%s\n' "$orchestration_output" | grep -Eq '"code"[[:space:]]*:[[:space:]]*"run_required"'; then
    pass "orchestration" "RPC reachable (run_required is expected before a Run is bound)"
  else
    fail "orchestration" "RPC unavailable; enable Orca orchestration and retry"
  fi
else
  fail "orchestration" "not checked because Orca status failed"
fi

skills_output=""
skills_status=0
if command -v npx >/dev/null 2>&1; then
  skills_output=$(npx --no-install skills list -g 2>&1 | strip_ansi) || skills_status=$?
else
  skills_status=127
fi

if [[ $skills_status -eq 127 ]]; then
  fail "skills" "npx is unavailable; install Node.js, then run: npx skills add stablyai/orca -g --skill orca-cli --skill orchestration"
elif [[ $skills_status -eq 0 ]] \
  && printf '%s\n' "$skills_output" | grep -Eq '(^|[[:space:]])orca-cli([[:space:]]|$)' \
  && printf '%s\n' "$skills_output" | grep -Eq '(^|[[:space:]])orchestration([[:space:]]|$)'; then
  pass "skills" "global orca-cli and orchestration skills are present"
else
  if [[ "$fix" == true ]]; then
    printf 'FIX  skills         npx skills add stablyai/orca -g --skill orca-cli --skill orchestration\n'
    fix_status=0
    npx skills add stablyai/orca -g --skill orca-cli --skill orchestration || fix_status=$?
    printf 'FIX  skills         npx skills update orchestration -g\n'
    npx skills update orchestration -g || fix_status=$?
    skills_output=$(npx --no-install skills list -g 2>&1 | strip_ansi) || fix_status=$?
    if [[ $fix_status -eq 0 ]] \
      && printf '%s\n' "$skills_output" | grep -Eq '(^|[[:space:]])orca-cli([[:space:]]|$)' \
      && printf '%s\n' "$skills_output" | grep -Eq '(^|[[:space:]])orchestration([[:space:]]|$)'; then
      pass "skills" "installed global orca-cli and orchestration skills"
    else
      fail "skills" "required skills still missing after --fix"
    fi
  else
    fail "skills" "missing orca-cli or orchestration; run: npx skills add stablyai/orca -g --skill orca-cli --skill orchestration; refresh with: npx skills update orchestration -g"
  fi
fi

if command -v bd >/dev/null 2>&1; then
  bd_output=""
  if bd_output=$(bd where 2>&1); then
    bd_path=$(printf '%s\n' "$bd_output" | sed -n '1p')
    ops_root=${bd_path%/.beads}
    if [[ -f "$ops_root/docs/MASTER-OPERATIONS.md" ]]; then
      pass "bd" "bd where resolves in ops repo: $ops_root"
    else
      fail "bd" "bd where resolves outside an ops repo: $bd_path"
    fi
  else
    ops_repo_marker_found=false
    home_dir=$(cd "$HOME" && pwd -P)
    marker_dir=$(pwd -P)
    while [[ "$marker_dir" != "$home_dir" && "$marker_dir" != "/" ]]; do
      if [[ -d "$marker_dir/.beads" ]]; then
        ops_repo_marker_found=true
        break
      fi
      marker_dir=${marker_dir%/*}
      [[ -z "$marker_dir" ]] && marker_dir=/
    done
    if [[ "$ops_repo_marker_found" == true ]]; then
      fail "bd" "ops repo marker found but bd where fails — fix bd or run from the ops repo"
    else
      pass "bd" "binary present; ops repo not confirmed from this cwd; run from the approved workspace or ops repo to verify"
    fi
  fi
else
  fail "bd" "binary missing; install Beads before onboarding"
fi

test_hint='PYTHONPATH=src uv run --with pytest --no-project python3 -m pytest tests -q'
if command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  pass "python3" "present; test suite: $test_hint"
else
  fail "python3" "missing; install Python 3.10+; test suite: $test_hint"
fi

printf '\nPreflight summary\n'
printf '  PASS: %d\n' "$passes"
printf '  FAIL: %d\n' "$failures"
if [[ $failures -eq 0 ]]; then
  printf '  READY: all required checks passed\n'
else
  printf '  BLOCKED: fix every FAIL before onboarding\n'
  exit 1
fi
