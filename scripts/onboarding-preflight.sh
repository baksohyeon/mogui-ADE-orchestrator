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
warnings=0
waived=0

# A required check that cannot be waived pushes the operator toward skipping the
# whole preflight, which loses every other check with it. PREFLIGHT_WAIVE names
# checks to downgrade from FAIL to WARN, and a waiver is always printed and
# counted: the escape exists, and it is never silent. Same shape as the gate's
# ledgered --tier-override.
waive_list=()
if [[ -n "${PREFLIGHT_WAIVE:-}" ]]; then
  IFS=',' read -r -a waive_list <<<"$PREFLIGHT_WAIVE"
fi
waived_labels=()
seen_labels=()

# Checks whose absence changes what the harness can do at all. A missing one is
# repeated at the end with its consequence, because fifteen lines of output is
# exactly the length at which the important line gets skimmed past.
ESSENTIAL_LABELS=(
  orca orchestration skills agent-cli worker-runtime bd python3
  gitleaks ctx redaction-extra skill-stack
)
essential_gaps=()

is_essential() {
  local candidate
  for candidate in "${ESSENTIAL_LABELS[@]}"; do
    [[ "${candidate}" == "$1" ]] && return 0
  done
  return 1
}

note_gap() {
  is_essential "$1" || return 0
  essential_gaps+=("$1|$2")
}

is_waived() {
  local candidate
  for candidate in ${waive_list[@]+"${waive_list[@]}"}; do
    [[ "${candidate// /}" == "$1" ]] && return 0
  done
  return 1
}

pass() {
  seen_labels+=("$1")
  passes=$((passes + 1))
  printf 'PASS %-14s %s\n' "$1" "$2"
}

fail() {
  seen_labels+=("$1")
  if is_waived "$1"; then
    # A waiver is an explicit decision the summary already names. Repeating it in
    # the essential block would make that block noise, and a block that is noise
    # stops being read, which is the only thing it had going for it.
    waived=$((waived + 1))
    waived_labels+=("$1")
    printf 'WAIVED %-12s %s (downgraded from FAIL by PREFLIGHT_WAIVE)\n' "$1" "$2"
    return
  fi
  note_gap "$1" "$2"
  failures=$((failures + 1))
  printf 'FAIL %-14s %s\n' "$1" "$2"
}

warn() {
  seen_labels+=("$1")
  note_gap "$1" "$2"
  warnings=$((warnings + 1))
  printf 'WARN %-14s %s\n' "$1" "$2"
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
orca_basename="${orca_command##*/}"
if ! command -v "$orca_command" >/dev/null 2>&1; then
  fail "orca" "$orca_command is not available; $(orca_install_hint)"
elif [[ "$orca_basename" != "orca" \
    && "$orca_basename" != "orca-dev" \
    && "$orca_basename" != "orca-ide" ]]; then
  fail "orca" "$orca_command is not a supported Orca CLI; expose the CLI as 'orca', 'orca-dev', or 'orca-ide' before onboarding"
else
  status_output=""
  if status_output=$("$orca_command" status --json 2>&1); then
    if grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' <<<"$status_output"; then
      pass "orca" "$orca_command status --json returned ok:true"
      orca_ready=true
    else
      fail "orca" "$orca_command status --json did not return ok:true; $(orca_install_hint)"
    fi
  else
    fail "orca" "$orca_command status --json failed; $(orca_install_hint)"
  fi
fi

# A reachable RPC does not mean a dispatch will land. Measure the capability
# the master actually depends on: a non-legacy Run bound to this terminal.
# Observed failure this check exists for: a retained legacy coordinator answers
# reads normally and drops writes with effectsApplied:false, so the dispatch
# record survives while the worker receives nothing.
if [[ "$orca_ready" == true ]]; then
  orchestration_output=""
  orchestration_status=0
  orchestration_output=$("$orca_command" orchestration run-current --json 2>&1) || orchestration_status=$?
  if grep -Eq '"code"[[:space:]]*:[[:space:]]*"legacy_read_only"' <<<"$orchestration_output"; then
    fail "orchestration" "retained legacy coordinator: calls answer and writes are dropped (effectsApplied:false); bind a fresh Run with '$orca_command orchestration run-create', then re-run this preflight; restarting the app does not clear it"
  elif [[ $orchestration_status -ne 0 ]] \
    || ! grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' <<<"$orchestration_output"; then
    fail "orchestration" "RPC unavailable; enable Orca orchestration and retry"
  elif grep -Eq '"run"[[:space:]]*:[[:space:]]*null' <<<"$orchestration_output"; then
    fail "orchestration" "RPC reachable but no Run is bound to this terminal: the task family fails with run_required until one is, and a binding that drops later does so without a signal, after which check returns count:0 and an empty mailbox looks the same as a missing binding; run: $orca_command orchestration run-create"
  elif grep -Eq '"legacy"[[:space:]]*:[[:space:]]*1' <<<"$orchestration_output"; then
    fail "orchestration" "the bound Run is legacy and inspect-only; create a fresh one: $orca_command orchestration run-create"
  else
    pass "orchestration" "RPC reachable and a non-legacy Run is bound to this terminal"
  fi
else
  fail "orchestration" "not checked because Orca status failed"
fi

skills_output=""
skills_status=0
runtime_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

# Measure the artifact before the installer. The required skills can be present
# without the `skills` package manager being installed at all, and an installer
# listing that cannot run is not evidence that the skills are missing.
# ORCA_SKILLS_DIRS overrides the search for agent layouts not listed here.
skills_artifact_ok=false
skills_roots=()
if [[ -n "${ORCA_SKILLS_DIRS:-}" ]]; then
  IFS=':' read -r -a skills_roots <<<"$ORCA_SKILLS_DIRS"
else
  skills_roots=(
    "$HOME/.claude/skills"
    "$HOME/.agents/skills"
    "$HOME/.codex/skills"
    "$HOME/.config/skills"
    "$HOME/.local/share/skills"
  )
fi
skills_found_root=""
for skills_root in "${skills_roots[@]}"; do
  [[ -d "$skills_root" ]] || continue
  if [[ -e "$skills_root/orca-cli" && -e "$skills_root/orchestration" ]]; then
    skills_artifact_ok=true
    skills_found_root="$skills_root"
    break
  fi
done
if [[ "$skills_artifact_ok" == true ]]; then
  pass "skills" "orca-cli and orchestration resolve under $skills_found_root"
fi

skills_command=()
skills_display=""
skills_candidate=$(command -v skills 2>/dev/null || true)
if [[ -n "$skills_candidate" && "$skills_candidate" = /* && -x "$skills_candidate" ]]; then
  skills_realpath=$(realpath "$skills_candidate" 2>/dev/null || printf '%s' "$skills_candidate")
  case "$skills_realpath" in
    "$runtime_root"/*)
      ;;
    *)
      skills_command=("$skills_realpath")
      skills_display="$skills_realpath"
      ;;
  esac
fi

if [[ ${#skills_command[@]} -eq 0 ]] && command -v npx >/dev/null 2>&1; then
  # --no-install may use only a locally available package; never auto-fetch.
  skills_command=(npx --no-install skills)
  skills_display="npx --no-install skills"
fi

if [[ "$skills_artifact_ok" == true ]]; then
  skills_status=0
elif [[ ${#skills_command[@]} -eq 0 ]]; then
  skills_status=127
else
  skills_output=$("${skills_command[@]}" list -g 2>&1 | strip_ansi) || skills_status=$?
  if [[ $skills_status -eq 0 ]] \
    && grep -Eq '(^|[[:space:]])orca-cli([[:space:]]|$)' <<<"$skills_output" \
    && grep -Eq '(^|[[:space:]])orchestration([[:space:]]|$)' <<<"$skills_output"; then
    pass "skills" "global orca-cli and orchestration skills are present"
  else
    skills_status=1
  fi
fi

if [[ $skills_status -eq 0 ]]; then
  :
elif [[ "$fix" == true && ${#skills_command[@]} -gt 0 ]]; then
    printf 'FIX  skills         %s add stablyai/orca -g --skill orca-cli --skill orchestration\n' "$skills_display"
    fix_status=0
    "${skills_command[@]}" add stablyai/orca -g --skill orca-cli --skill orchestration || fix_status=$?
    printf 'FIX  skills         %s update orchestration -g\n' "$skills_display"
    "${skills_command[@]}" update orchestration -g || fix_status=$?
    skills_output=$("${skills_command[@]}" list -g 2>&1 | strip_ansi) || fix_status=$?
    if [[ $fix_status -eq 0 ]] \
      && grep -Eq '(^|[[:space:]])orca-cli([[:space:]]|$)' <<<"$skills_output" \
      && grep -Eq '(^|[[:space:]])orchestration([[:space:]]|$)' <<<"$skills_output"; then
      pass "skills" "installed global orca-cli and orchestration skills"
    else
      fail "skills" "required skills still missing after --fix"
    fi
  else
    if [[ ${#skills_command[@]} -eq 0 ]]; then
      fail "skills" "skills executable unavailable; install a local skills executable or package, then run: skills add stablyai/orca -g --skill orca-cli --skill orchestration"
    else
      fail "skills" "missing orca-cli or orchestration; run: $skills_display add stablyai/orca -g --skill orca-cli --skill orchestration; refresh with: $skills_display update orchestration -g"
    fi
  fi

if [[ "${ORCA_AGENT_CLI:-}" == "claude" || "${ORCA_AGENT_CLI:-}" == "claude-code" ]]; then
  claude_plugins_file="${HOME}/.claude/plugins/installed_plugins.json"
  if [[ -f "$claude_plugins_file" ]] \
    && grep -Fq 'codex@openai-codex' "$claude_plugins_file"; then
    pass "codex-plugin" "official Codex plugin is installed for Claude Code"
  else
    # A routing policy that sends heavy work to Codex is one workspace's choice,
    # not a property of every Claude Code master. Wiring stays, enforcement does
    # not: the install path is stated, and a host that never dispatches Codex
    # workers onboards without it.
    warn "codex-plugin" "official Codex plugin missing from $claude_plugins_file; hosts that dispatch Codex workers need it. In Claude Code: /plugin marketplace add openai/codex-plugin-cc; /plugin install codex@openai-codex; /reload-plugins; verify /codex:setup"
  fi
elif command -v claude >/dev/null 2>&1; then
  printf 'INFO %-14s %s\n' "codex-plugin" "skipped because Claude Code is installed but ORCA_AGENT_CLI does not select it"
else
  printf 'INFO %-14s %s\n' "codex-plugin" "skipped because Claude Code is not the selected agent"
fi

# The behaviour-shaping layer: methodology and restraint. Both are distributed as
# skill packs and are not tied to one agent, so the check is agent-neutral and only
# the install hint differs. Detection accepts either packaging: a skill directory
# under any known root, or an agent's plugin manifest, which is the same content
# wrapped differently.
#
# They warn rather than fail. A master runs without them; it runs differently, and
# the warning carries that cost so the operator learns it here instead of later.
behaviour_packs=(
  "superpowers|methodology|without it the master reads the charter as advice rather than procedure"
  "ponytail|restraint|without it expect larger diffs and more speculative structure; it pairs with the methodology layer rather than competing"
)
claude_plugins_file="${HOME}/.claude/plugins/installed_plugins.json"
for pack_entry in "${behaviour_packs[@]}"; do
  IFS='|' read -r pack_id pack_name pack_cost <<<"${pack_entry}"
  pack_found=""
  for skills_root in ${skills_roots[@]+"${skills_roots[@]}"}; do
    if [[ -e "${skills_root}/${pack_id}" ]]; then
      pack_found="${skills_root}/${pack_id}"
      break
    fi
  done
  if [[ -z "${pack_found}" && -f "${claude_plugins_file}" ]] \
    && grep -Fq "\"${pack_id}@" "${claude_plugins_file}"; then
    pack_found="agent plugin manifest"
  fi
  if [[ -n "${pack_found}" ]]; then
    pass "skill-stack" "${pack_id} (${pack_name}) resolves via ${pack_found}"
  else
    case "${ORCA_AGENT_CLI:-}" in
      claude|claude-code)
        pack_install="/plugin install ${pack_id}@<marketplace>, after /plugin marketplace add"
        ;;
      *)
        pack_install="install the ${pack_id} skill pack for ${ORCA_AGENT_CLI:-your agent}, or place it under one of: ${skills_roots[*]}"
        ;;
    esac
    warn "skill-stack" "${pack_id} (${pack_name}) missing: ${pack_cost}. Install with: ${pack_install}"
  fi
done

# Required, not optional: REDACTION_REQUIRE_EXTRA=1 scanning exits 2 with no
# rules loaded, and redaction-inventory exits 2 when this file is unset or
# yields no readable rule. A missing file is a blocked publish path.
# Honor the variable both consumers read before falling back to the default path.
redaction_extra="${REDACTION_EXTRA_PATTERNS:-${HOME}/.config/redaction-extra.txt}"
redaction_format='format: one rule per line as "id|description|regex"; blank lines and lines beginning with # are skipped; only the first two pipes separate fields, so the regex may contain "|"; the regex must compile, because redaction-inventory drops uncompilable rules without reporting them; keep the file out of version control'
if [[ ! -f "$redaction_extra" ]]; then
  fail "redaction-extra" "organization rules file missing: $redaction_extra; two of the three publish gates refuse to run without it; $redaction_format"
else
  # Counts only. This file's contents are what the scanner protects, so the
  # check must never print a rule, an identifier, or a match.
  redaction_counts=""
  redaction_counts=$(python3 - "$redaction_extra" <<'PY' 2>/dev/null || true
import re
import sys

total = valid = malformed = 0
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        total += 1
        parts = line.split("|", 2)
        if len(parts) != 3:
            malformed += 1
            continue
        try:
            re.compile(parts[2])
        except re.error:
            malformed += 1
            continue
        valid += 1
print(total, valid, malformed)
PY
  )
  if [[ -z "$redaction_counts" ]]; then
    fail "redaction-extra" "could not read $redaction_extra; $redaction_format"
  else
    read -r rx_total rx_valid rx_malformed <<<"$redaction_counts"
    if [[ "$rx_valid" -eq 0 ]]; then
      fail "redaction-extra" "$redaction_extra yields no usable rule out of $rx_total non-comment lines; $redaction_format"
    elif [[ "$rx_malformed" -gt 0 ]]; then
      fail "redaction-extra" "$rx_malformed of $rx_total rules in $redaction_extra are malformed or do not compile, so coverage is narrower than the file looks; $redaction_format"
    else
      pass "redaction-extra" "$rx_valid rules load from $redaction_extra"
    fi
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
# No version floor is enforced here. The core runs on the interpreter the host
# already has (measured down to the CLT 3.9.6 a bare Mac ends up with). A tool
# that needs a newer one states its own requirement at runtime and exits with
# its own error, which keeps interpreter floors where they belong: per tool,
# not as an onboarding blocker for hosts that never run that tool.
if command -v python3 >/dev/null 2>&1; then
  python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null)
  pass "python3" "Python ${python_version:-unknown} present; no version floor is enforced here, a tool that needs a newer interpreter states that itself at runtime (today: codex-worker-pretrust, 3.11+ for tomllib)"
else
  fail "python3" "missing; the runtime's entry points are python3 scripts, so nothing here runs without it"
fi

# --- harness and worker tool surface --------------------------------------
# Every entry below is a tool the master or a dispatched worker invokes during
# normal operation. The template ships prose and scripts; the parts that make a
# master work live in host configuration, so onboarding measures them instead of
# assuming them. Trim the lists if your routing policy uses different executors.

agent_cli="${ORCA_AGENT_CLI:-}"
if [[ -z "$agent_cli" ]]; then
  fail "agent-cli" "ORCA_AGENT_CLI is unset; name the agent CLI this master runs so agent-specific checks are measured instead of skipped"
elif ! command -v "$agent_cli" >/dev/null 2>&1; then
  fail "agent-cli" "ORCA_AGENT_CLI=$agent_cli is not on PATH; install it or correct the value"
else
  pass "agent-cli" "$agent_cli resolves on PATH"
fi

# One reachable executor is enough to delegate. Requiring every listed runtime
# blocks a host that routes all work through one of them, which is a normal
# setup, so a missing runtime is a WARN and no runtime at all is the failure.
worker_runtimes=(codex cursor-agent)
worker_runtime_found=false
for worker_runtime in "${worker_runtimes[@]}"; do
  if command -v "$worker_runtime" >/dev/null 2>&1; then
    worker_runtime_found=true
  fi
done
for worker_runtime in "${worker_runtimes[@]}"; do
  if command -v "$worker_runtime" >/dev/null 2>&1; then
    pass "worker-runtime" "$worker_runtime present"
  elif [[ "$worker_runtime_found" == true ]]; then
    warn "worker-runtime" "$worker_runtime is not on PATH; another listed runtime is, so dispatch is still possible on this host"
  else
    fail "worker-runtime" "$worker_runtime is not on PATH; a master that cannot reach its executors cannot delegate"
  fi
done

# gitleaks is the redaction gate's matching engine, so publishing needs it: the
# gate exits 2 rather than guessing when it is absent. Running a master does not,
# which is why this warns instead of blocking. It stays in ESSENTIAL_LABELS so the
# summary repeats the consequence instead of letting a warning scroll past.
if command -v gitleaks >/dev/null 2>&1; then
  pass "gitleaks" "$(gitleaks version 2>&1 | head -1)"
else
  warn "gitleaks" "gitleaks is not on PATH; the redaction gate cannot decide without it and exits 2, so install it before publishing anything (brew install gitleaks, or see https://gitleaks.io)"
fi

# ctx indexes agent history from every provider on the host into one queryable
# store. The records practice depends on it; a master runs without it, so a host
# that does no history work loses nothing. Warn, and let the summary carry it.
if command -v ctx >/dev/null 2>&1; then
  ctx_status=""
  if ctx_status=$(ctx status 2>&1); then
    pass "ctx" "$(ctx --version 2>&1 | head -1); index reachable"
  else
    warn "ctx" "ctx is installed but 'ctx status' failed; run 'ctx setup' to create the local index, or the records practice cannot query history"
  fi
else
  warn "ctx" "ctx is not on PATH; the records practice queries agent history across providers and cannot without it (see https://ctx.rs); ignore this on a host that does no history work"
fi

for repo_tool in git gh; do
  if command -v "$repo_tool" >/dev/null 2>&1; then
    pass "$repo_tool" "present"
  else
    fail "$repo_tool" "$repo_tool is required; this repository is managed through pull requests"
  fi
done

if command -v gh >/dev/null 2>&1; then
  gh_status=$(gh auth status 2>&1) || true
  if printf '%s\n' "$gh_status" | grep -q 'Logged in'; then
    if printf '%s\n' "$gh_status" | grep -q 'workflow'; then
      pass "gh-auth" "authenticated with workflow scope"
    else
      # Not fatal for ordinary PR work; fatal the moment a workflow file moves.
      warn "gh-auth" "authenticated without the workflow scope; pushing or editing GitHub Actions workflows will fail; run: gh auth refresh -h github.com -s workflow"
    fi
  else
    # Local-only work needs no forge credentials; the block belongs at push time,
    # not at onboarding. Waive-able as gh-auth if the host never pushes.
    warn "gh-auth" "gh is not authenticated, so pushing branches and opening pull requests will fail; run: gh auth login"
  fi
fi

# Tests are the agent's job, so how they would run is reported rather than
# enforced. Note the wrinkle: suite collection imports tomllib, so an interpreter
# under 3.11 reaches the suite through uv, not through python3 -m pytest.
if python3 -c 'import sys, pytest; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  pass "pytest" "python3 -m pytest is runnable on this interpreter"
elif command -v uv >/dev/null 2>&1; then
  pass "pytest" "uv present; the suite runs through: $test_hint"
else
  warn "pytest" "neither pytest on a 3.11+ interpreter nor uv is present; the agent that runs the test gate will need one of them, and this host currently offers neither"
fi

# The gate writes its ledger outside the repository. Check writability without
# creating anything: this script must not change state before --fix.
gate_ledger="${DISPATCH_GATE_LEDGER:-.mogui/dispatch-ledger.jsonl}"
gate_ledger_dir=$(dirname "$gate_ledger")
if [[ -d "$gate_ledger_dir" ]]; then
  if [[ -w "$gate_ledger_dir" ]]; then
    pass "gate-ledger" "dispatch ledger directory is writable: $gate_ledger_dir"
  else
    fail "gate-ledger" "dispatch ledger directory is not writable: $gate_ledger_dir; set DISPATCH_GATE_LEDGER to a writable path"
  fi
else
  gate_ledger_parent=$(dirname "$gate_ledger_dir")
  if [[ -d "$gate_ledger_parent" && -w "$gate_ledger_parent" ]]; then
    pass "gate-ledger" "dispatch ledger directory will be created under $(cd "$gate_ledger_parent" && pwd -P)"
  else
    fail "gate-ledger" "cannot create the dispatch ledger directory under $gate_ledger_parent; set DISPATCH_GATE_LEDGER to a writable path"
  fi
fi

# A waiver that matched nothing is a typo, and a typo'd waiver leaves the check
# enforced while the operator believes otherwise. Name the ones that never fired.
unmatched_waivers=()
for waive_label in ${waive_list[@]+"${waive_list[@]}"}; do
  waive_label="${waive_label// /}"
  [[ -z "$waive_label" ]] && continue
  waive_matched=false
  for seen_label in ${seen_labels[@]+"${seen_labels[@]}"}; do
    [[ "$seen_label" == "$waive_label" ]] && waive_matched=true && break
  done
  [[ "$waive_matched" == false ]] && unmatched_waivers+=("$waive_label")
done

printf '\nPreflight summary\n'
printf '  PASS: %d\n' "$passes"
printf '  WARN: %d\n' "$warnings"
printf '  FAIL: %d\n' "$failures"
printf '  WAIVED: %d' "$waived"
if [[ ${#waived_labels[@]} -gt 0 ]]; then
  printf ' (%s)' "$(IFS=,; printf '%s' "${waived_labels[*]}")"
fi
printf '\n'
if [[ ${#unmatched_waivers[@]} -gt 0 ]]; then
  printf '  NOTE: PREFLIGHT_WAIVE named checks that did not run: %s; those checks are still enforced\n' \
    "$(IFS=,; printf '%s' "${unmatched_waivers[*]}")"
fi
if [[ ${#essential_gaps[@]} -gt 0 ]]; then
  printf '\n'
  printf '  !! ESSENTIAL COMPONENTS MISSING (%d) — the harness will not behave as documented\n' "${#essential_gaps[@]}"
  for gap_entry in "${essential_gaps[@]}"; do
    printf '  !!   %-14s %s\n' "${gap_entry%%|*}" "${gap_entry#*|}"
  done
  printf '  !! These are not preferences. Install them, or record the decline and the\n'
  printf '  !! behaviour you are accepting, before spawning a master.\n'
fi

if [[ $failures -eq 0 ]]; then
  if [[ $waived -gt 0 ]]; then
    printf '  READY WITH WAIVERS: %d required check(s) were downgraded, not satisfied\n' "$waived"
  else
    printf '  READY: all required checks passed\n'
  fi
else
  printf '  BLOCKED: fix every FAIL before onboarding\n'
  exit 1
fi
