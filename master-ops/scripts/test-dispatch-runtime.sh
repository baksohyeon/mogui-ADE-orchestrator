#!/bin/bash
# Static regression check for the minimal agy capability mapping in dispatch.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
for pattern in \
  'agy:gemini' \
  "if runtime == 'agy': runtime = 'gemini'" \
  'agy) echo "agy --model $model_arg --dangerously-skip-permissions"'; do
  grep -Fq "$pattern" "$dispatch" || { echo "FAIL: missing dispatch pattern: $pattern" >&2; exit 1; }
done
echo "dispatch agy capability regression test passed"
