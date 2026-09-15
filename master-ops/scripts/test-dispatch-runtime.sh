#!/bin/bash
# Static regression check for the minimal agy capability mapping in dispatch.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}
for pattern in \
  'agy:gemini' \
  "if runtime == 'agy': runtime = 'gemini'" \
  'agy) echo "agy --model $model_arg --dangerously-skip-permissions"'; do
  grep -Fq "$pattern" "$dispatch" || { echo "FAIL: missing dispatch pattern: $pattern" >&2; exit 1; }
done

probe_args_expansion_guard_test() {
  local target="$1" probe_expansion='"${MODEL_PROBE_ARGS[@]+"${MODEL_PROBE_ARGS[@]}"}"'
  if ! grep -Fq "$probe_expansion" "$target"; then
    echo "FAIL: missing guarded MODEL_PROBE_ARGS expansion in dispatch register call" >&2
    return 1
  fi

  /bin/bash -uc "set -u; MODEL_PROBE_ARGS=(); : $probe_expansion" >/dev/null 2>&1
}

probe_args_expansion_guard_test "$dispatch" || {
  echo "FAIL: MODEL_PROBE_ARGS expansion is not bash 3.2 set -u safe when empty" >&2
  exit 1
}
echo "dispatch agy capability regression test passed"
