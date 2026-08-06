#!/bin/bash
# Static regression check for the minimal agy capability mapping in dispatch.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
grep -Fq 'agy:gemini' "$dispatch"
grep -Fq "if runtime == 'agy': runtime = 'gemini'" "$dispatch"
grep -Fq 'agy) echo "agy --model $model_arg --dangerously-skip-permissions"' "$dispatch"
echo "dispatch agy capability regression test passed"
