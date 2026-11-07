#!/bin/bash
# End-to-end argv coverage for dispatch's optional sender terminal.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fixture="$work/master-ops"
fake_bin="$work/bin"
tmp_home="$work/home"
state="$work/state"
policy="$work/policy.json"
contract="$work/contract.md"
rules="$fixture/rules/standing-rules.md"
gate="$work/dispatch-gate"
mkdir -p "$fixture/scripts/lib" "$fixture/rules" "$fake_bin" "$tmp_home" "$state"
cp "$dispatch" "$fixture/scripts/dispatch"
cp "$(dirname "$dispatch")/lib/orca_json.py" "$fixture/scripts/lib/orca_json.py"
cp "$(dirname "$dispatch")/mogui_log.py" "$fixture/scripts/mogui_log.py"
printf '\n' > "$rules"
printf '{"tiers":{"efficient":[],"top":[]}}\n' > "$policy"
printf '# test contract\n' > "$contract"

# Keep the real dispatch-gate out of this fixture. The test is concerned with
# the two orca argv shapes after the gate has allowed the run.
cat > "$gate" <<'EOF'
#!/bin/bash
printf '{"allow":true,"contract_sha":"abcdef0123456789","warnings":[]}\n'
EOF
chmod +x "$gate"
sed "s|^GATE=.*|GATE=$gate|" "$dispatch" > "$fixture/scripts/dispatch"
chmod +x "$fixture/scripts/dispatch"

cat > "$fake_bin/orca" <<'EOF'
#!/bin/bash
{
  printf 'argv'
  printf '\t%s' "$@"
  printf '\n'
} >> "$ORCA_LOG"
if [ "${ORCA_TERMINAL_HANDLE+x}" = x ]; then
  printf 'present\n' >> "$ORCA_ENV_LOG"
else
  printf 'absent\n' >> "$ORCA_ENV_LOG"
fi
case "$1:$2" in
  orchestration:task-create|orchestration:dispatch) ;;
  *)
    for arg in "$@"; do
      if [ "$arg" = --from ]; then
        printf '%s\n' "$*" >> "$ORCA_BAD_CALL"
        exit 1
      fi
    done
    ;;
esac
case "$1:$2" in
  orchestration:task-create) printf '{"ok":true,"result":{"taskId":"task_test"}}\n' ;;
  orchestration:dispatch) printf '{"ok":true,"result":{"dispatchId":"ctx_test"}}\n' ;;
  orchestration:dispatch-show) printf '{"ok":true,"result":{"status":"completed"}}\n' ;;
  terminal:read) printf 'unknown\n' ;;
  *) printf '{}\n' ;;
esac
EOF
chmod +x "$fake_bin/orca"
cat > "$fake_bin/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$fake_bin/sleep"

run_case() {
  local label="$1" target="$2" with_sender="$3"
  local log="$work/$label.log" env_log="$work/$label.env" bad_call="$work/$label.bad"
  local out status task_line dispatch_line prefix
  local expected_task expected_dispatch
  : > "$log"
  : > "$env_log"
  : > "$bad_call"
  local -a env_args
  env_args=(env -i PATH="$fake_bin:$PATH" HOME="$tmp_home"
    ORCA_LOG="$log" ORCA_ENV_LOG="$env_log" ORCA_BAD_CALL="$bad_call"
    MOGUI_STATE_DIR="$state"
    DISPATCH_STANDING_RULES="$rules")
  if [ "$with_sender" = 1 ]; then
    env_args+=(DISPATCH_FROM_TERMINAL=term_test)
  fi

  if out=$("${env_args[@]}" bash "$target" \
    --contract "$contract" \
    --runtime opencode --model model-test --terminal term_worker \
    --spec test-spec --tier-policy "$policy" 2>&1); then
    status=0
  else
    status=$?
  fi
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $label dispatch exited $status"
    printf '%s\n' "$out"
    return 1
  fi

  prefix=$'argv\torchestration\ttask-create\t'
  if ! task_line=$(grep -F "$prefix" "$log"); then
    echo "FAIL: $label did not reach task-create"
    return 1
  fi
  prefix=$'argv\torchestration\tdispatch\t'
  if ! dispatch_line=$(grep -F "$prefix" "$log"); then
    echo "FAIL: $label did not reach orchestration dispatch"
    return 1
  fi
  if [ "$with_sender" = 1 ]; then
    expected_task=$'argv\torchestration\ttask-create\t--from\tterm_test\t--spec\ttest-spec'
    expected_dispatch=$'argv\torchestration\tdispatch\t--from\tterm_test\t--task\ttask_test\t--to\tterm_worker\t--inject\t--json'
    if [ "$task_line" != "$expected_task" ] || [ "$dispatch_line" != "$expected_dispatch" ]; then
      echo "FAIL: $label did not pass --from term_test on both calls"
      return 1
    fi
  else
    expected_task=$'argv\torchestration\ttask-create\t--spec\ttest-spec'
    expected_dispatch=$'argv\torchestration\tdispatch\t--task\ttask_test\t--to\tterm_worker\t--inject\t--json'
    if [ "$task_line" != "$expected_task" ] || [ "$dispatch_line" != "$expected_dispatch" ]; then
      echo "FAIL: $label passed --from without DISPATCH_FROM_TERMINAL"
      return 1
    fi
  fi
  if grep -qv '^absent$' "$env_log"; then
    echo "FAIL: $label inherited ORCA_TERMINAL_HANDLE"
    return 1
  fi
  if [ -s "$bad_call" ]; then
    echo "FAIL: $label passed --from to a non-target orca call"
    return 1
  fi
  echo "PASS: $label"
}

run_case "sender-terminal" "$fixture/scripts/dispatch" 1
run_case "no-sender-terminal" "$fixture/scripts/dispatch" 0

mutant="$fixture/scripts/dispatch-mutant"
cp "$fixture/scripts/dispatch" "$mutant"
if ! grep -Fq 'task-create "${DISPATCH_FROM_ARGS[@]+"${DISPATCH_FROM_ARGS[@]}"}"' "$mutant"; then
  echo "FAIL: failability mutant anchor is missing"
  exit 1
fi
sed \
  -e 's|^TASK_RAW=.*|TASK_RAW=$(orca orchestration task-create --spec "$SPEC" --json 2>/dev/null)|' \
  -e 's|^DISP_RAW=.*|DISP_RAW=$(orca orchestration dispatch --task "$TASK" --to "$TERMINAL" --inject --json 2>/dev/null)|' \
  "$mutant" > "$mutant.next"
mv "$mutant.next" "$mutant"
if grep -Fq 'task-create "${DISPATCH_FROM_ARGS[@]+"${DISPATCH_FROM_ARGS[@]}"}"' "$mutant" \
  || grep -Fq 'orchestration dispatch "${DISPATCH_FROM_ARGS[@]+"${DISPATCH_FROM_ARGS[@]}"}"' "$mutant"; then
  echo "FAIL: failability mutant could not remove both sender expansions"
  exit 1
fi

set +e
run_case "mutant-without-sender" "$mutant" 1 > "$work/mutant.out" 2>&1
mutant_status=$?
set -e
if [ "$mutant_status" -eq 0 ]; then
  echo "FAIL: failability mutant still passed the sender-terminal case"
  cat "$work/mutant.out"
  exit 1
fi
mutant_failure=$(grep -m1 '^FAIL:' "$work/mutant.out" || printf 'missing assertion detail')
echo "PASS: failability mutant was caught ($mutant_failure)"
