#!/usr/bin/env bash
# Regression checks for dispatch's agy pre-trust helper and call site.
set -u

dispatch_dir="$(cd "$(dirname "$0")" && pwd)"
dispatch="$dispatch_dir/dispatch"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fn=$(awk '$0=="ensure_agy_pretrust() {"{f=1} f{print} f&&$0=="}"{exit}' "$dispatch")
if [ -z "$fn" ]; then
  echo "FAIL: could not extract ensure_agy_pretrust" >&2
  exit 1
fi

cat >"$work/agy-worker-pretrust" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" != "$AGY_EXPECTED_PATH" ]; then
  echo "unexpected worktree path: ${1:-<none>}" >&2
  exit 1
fi
printf 'Summary: 0 added, 0 updated, 1 already trusted\n'
EOF
chmod +x "$work/agy-worker-pretrust"
write_runner() {
  local runner="$1" body="$2"
  {
    echo '#!/usr/bin/env bash'
    echo 'set -u'
    printf 'export AGY_EXPECTED_PATH=%q\n' "$work"
    printf 'AGY_PRETRUST_BIN=%q\n' "$work/agy-worker-pretrust"
    printf '%s\n' "$body"
    printf 'ensure_agy_pretrust agy path:%q && printf "TRUSTED\\n"\n' "$work"
  } >"$runner"
  chmod +x "$runner"
}

write_runner "$work/run.sh" "$fn"
out=$(bash "$work/run.sh" 2>&1)
status=$?
if [ "$status" -ne 0 ] \
  || ! printf '%s\n' "$out" | grep -q '^TRUSTED$' \
  || ! printf '%s\n' "$out" | grep -q 'pre-trust ✓ agy'; then
  echo "FAIL: ensure_agy_pretrust should accept a trusted Summary line" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : ensure_agy_pretrust accepts a trusted Summary line"

cat >"$work/agy-worker-pretrust" <<'EOF'
#!/usr/bin/env bash
printf 'helper failed\n' >&2
exit 7
EOF
chmod +x "$work/agy-worker-pretrust"
out=$(bash "$work/run.sh" 2>&1)
status=$?
if [ "$status" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'failed (exit 7)'; then
  echo "FAIL: ensure_agy_pretrust should fail closed on a nonzero helper exit" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : ensure_agy_pretrust fails closed on a nonzero helper exit"

cat >"$work/agy-worker-pretrust" <<'EOF'
#!/usr/bin/env bash
printf 'helper completed without a summary\n'
EOF
chmod +x "$work/agy-worker-pretrust"
out=$(bash "$work/run.sh" 2>&1)
status=$?
if [ "$status" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'produced no Summary line'; then
  echo "FAIL: ensure_agy_pretrust should fail closed when Summary is missing" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : ensure_agy_pretrust fails closed when Summary is missing"

mutant_fn=${fn/'    "")'/'    "never")'}
if [ "$mutant_fn" = "$fn" ]; then
  echo "FAIL: missing-summary mutant did not change the source" >&2
  exit 1
fi
write_runner "$work/run-mutant.sh" "$mutant_fn"
out=$(bash "$work/run-mutant.sh" 2>&1)
status=$?
if [ "$status" -ne 0 ] || ! printf '%s\n' "$out" | grep -q '^TRUSTED$'; then
  echo "FAIL: failability mutant did not demonstrate that dropping the missing-summary guard weakens the check" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "ok   : failability: dropping the missing-summary case makes the guard succeed"

call_line=$(grep -n '^  ensure_agy_pretrust "\$RUNTIME" "\$WORKTREE" || exit 2$' "$dispatch" | head -1 | cut -d: -f1)
terminal_line=$(grep -n 'orca terminal create --worktree "\$WORKTREE"' "$dispatch" | head -1 | cut -d: -f1)
if [ -z "$call_line" ] || [ -z "$terminal_line" ] || [ "$call_line" -ge "$terminal_line" ]; then
  echo "FAIL: dispatch must call ensure_agy_pretrust before terminal creation" >&2
  exit 1
fi
echo "ok   : dispatch calls ensure_agy_pretrust before terminal creation"

if grep -q '^if \[ "\$CHECK_ONLY" = 1 \] && \[ "\$RUNTIME" = agy \]; then$' "$dispatch"; then
  echo "FAIL: dispatch should not have an agy-only check-only pre-trust block" >&2
  exit 1
fi
echo "ok   : check-only agy dispatch has no mutating pre-trust block"
