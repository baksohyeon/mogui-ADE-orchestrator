#!/usr/bin/env bash
# PostToolUse(Bash): measure what actually came back, warn once when it is large.
#
# bash-output-trim-warn.sh looks at the command string before it runs and goes quiet the moment
# any filter token appears, so it never fired while one session spent 24% of its context on Bash
# results (measured on a seat). This hook reads the tool result after the fact and speaks only about size.
# It never blocks (exit 0 always) and prints one line, because the line itself costs context.
#
#   MOGUI_BASH_OUTPUT_WARN_CHARS   threshold in characters, default 6000 (about 1.5k tokens)
#
# The result JSON is read into a variable first: a heredoc program on `python3 -` would take
# python's stdin for itself and the piped result would never reach json.load. Measured 2026-09-14
# when the first version passed its own small-result test for exactly that reason.
set -u
THRESH="${MOGUI_BASH_OUTPUT_WARN_CHARS:-6000}"
INPUT=$(cat)
printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
r = d.get("tool_response")
if isinstance(r, dict):
    text = "".join(str(r.get(k, "")) for k in ("stdout", "stderr", "output", "content")) or json.dumps(r, ensure_ascii=False)
else:
    text = "" if r is None else str(r)
n = len(text)
try:
    thresh = int(sys.argv[1])
except (TypeError, ValueError):
    sys.exit(0)
if n > thresh:
    print(f"[output-size] this Bash result was {n} chars (~{n//4} tokens), over the {thresh}-char line. Next call: ask one question, filter every sub-command, grep instead of cat.")
' "$THRESH"
exit 0
