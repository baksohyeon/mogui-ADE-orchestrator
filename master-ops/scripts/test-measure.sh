#!/bin/bash
# Cases for scripts/measure. The ones that matter are 2 and 3: a command that
# fails silently, and a command that succeeds with nothing to say, must not
# render the same way. Reading those two as the same thing is what this wrapper
# exists to prevent.
set -u

cd "$(dirname "$0")/.."
MEASURE="./scripts/measure"

pass=0
fail=0

check() {
  # $1 name, $2 expected first line, $3 expected second line, $4 expected exit,
  # rest: command
  local name="$1" want_first="$2" want_second="$3" want_exit="$4"
  shift 4
  local out rc first second
  out=$("$MEASURE" "$@" 2>&1)
  rc=$?
  first=$(printf '%s\n' "$out" | sed -n 1p)
  second=$(printf '%s\n' "$out" | sed -n 2p)

  if [ "$first" = "$want_first" ] && [ "$second" = "$want_second" ] && [ "$rc" = "$want_exit" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       want: [$want_first] [$want_second] exit=$want_exit"
    echo "       got:  [$first] [$second] exit=$rc"
    fail=$((fail + 1))
  fi
}

# 1. Status comes first, before the output, so it cannot be scrolled past.
check "status precedes output" "exit=0" "hello" 0 \
  echo hello

# 2. A command that fails with nothing on stdout. This is the ls-remote case:
#    the failure was invisible and the empty output was read as a count of zero.
check "silent failure names its status and its emptiness" "exit=1" "(no output)" 1 \
  sh -c 'exit 1'

# 3. A command that succeeds with no output. Same rendering as case 2 except
#    the status, which is the whole point: the status is what separates them.
check "empty success is distinguishable only by status" "exit=0" "(no output)" 0 \
  sh -c 'exit 0'

# 4. stderr is not dropped. A command whose only message goes to stderr must
#    still show that message, not read as empty.
check "stderr is shown, not swallowed" "exit=3" "boom" 3 \
  sh -c 'echo boom >&2; exit 3'

# 5. The command's own status is the wrapper's status, so `measure` stays usable
#    inside if and &&. A missing command must report 127 and say what was
#    missing, not go quiet.
out=$("$MEASURE" no-such-command-exists-here 2>&1); rc=$?
if [ "$rc" = "127" ] \
   && printf '%s' "$out" | sed -n 1p | grep -qx "exit=127" \
   && printf '%s' "$out" | grep -qi "not found"; then
  echo "ok   — missing command is 127 and names itself"
  pass=$((pass + 1))
else
  echo "FAIL — missing command is 127 and names itself (exit=$rc)"
  echo "       got: $out"
  fail=$((fail + 1))
fi

# 6. Usage error is exit 2 and does not look like a successful measurement.
out=$("$MEASURE" 2>&1); rc=$?
if [ "$rc" = "2" ] && printf '%s' "$out" | grep -q "usage:"; then
  echo "ok   — no command is a usage error, not a measurement"
  pass=$((pass + 1))
else
  echo "FAIL — no command is a usage error, not a measurement (exit=$rc)"
  fail=$((fail + 1))
fi

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
