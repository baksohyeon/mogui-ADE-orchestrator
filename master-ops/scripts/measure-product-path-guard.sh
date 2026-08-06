#!/bin/bash
# Report measured Bash observations and the guard rejection rate.
set -u

LOG=${MOGUI_EVENT_LOG:-$HOME/.mogui/event-log.jsonl}
python3 - "$LOG" <<'PY'
import json
import sys

path = sys.argv[1]
observed = 0
rejected = 0
try:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") != "product_path_guard":
                continue
            if not record.get("command_class"):
                continue
            observed += 1
            if record.get("outcome") == "finding":
                rejected += 1
except OSError:
    pass

if observed:
    rate = f"{rejected / observed * 100:.2f}% ({rejected}/{observed})"
else:
    rate = "N/A (0/0; no command observations)"
print(f"bash_command_observations={observed}")
print(f"guard_rejections={rejected}")
print(f"rejection_rate={rate}")
PY
