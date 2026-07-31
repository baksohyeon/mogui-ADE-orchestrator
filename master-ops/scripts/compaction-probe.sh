#!/usr/bin/env bash
# SessionStart(compact) context-quality recall probe.
# This emits instructions only. It records no secret values and implements no
# dispatch or security enforcement.
set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

INPUT="$(cat 2>/dev/null)"
LEDGER_PATH="${CONTEXT_QUALITY_LOG:-$HOME/.mogui/monitors/{{MONITOR_NS}}/context-quality.jsonl}"

PROBE_INPUT="$INPUT" \
LEDGER_PATH="$LEDGER_PATH" \
python3 <<'PY' 2>/dev/null || true
import json
import os
import sys
from datetime import datetime, timezone

try:
    payload = json.loads(os.environ.get("PROBE_INPUT", "") or "{}")
except Exception:
    sys.exit(0)

if payload.get("source") != "compact":
    sys.exit(0)

session_id = payload.get("session_id") or "<unknown-session>"
ledger_path = os.environ.get(
    "LEDGER_PATH",
    os.path.expanduser("~/.mogui/monitors/{{MONITOR_NS}}/context-quality.jsonl"),
)

record_template = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "workspace": "{{WORKSPACE_NAME}}",
    "session": session_id,
    "event": "compact",
    "model": "<actual model/tool version stamp>",
    "recall": {
        "tracks": "<remembered active tracks>",
        "decisions": "<remembered recent accepted decisions>",
        "role": "<remembered Current Role and Lock>",
        "turn": "<remembered in-progress turn and next action>",
    },
    "loss_notes": [],
    "proposed_succession": False,
}

instruction = f"""[Compaction Recall Probe]
First compare the current time with the conversation time, then continue. This probe was injected immediately after SessionStart source=compact.

The order is the test. Do not open source-of-truth files first. Write the answer from memory, append the record, and only then verify against sources of truth.

R1 Active tracks: from memory only, list active track ids and one-line status. After recording, verify against the issue tracker for {{OPS_REPO}}.
R2 Recent accepted decisions: from memory only, restate recent accepted decisions and artifacts. After recording, verify against Git history and docs.
R3 Role State: from memory only, restate Current Role and Role Lock. After recording, verify against docs/runbooks/role-state.md.
R4 In-progress turn: describe the work immediately before compaction and the next action. This item may have no independent source; mark uncertainty explicitly.

Append one JSON record before source verification. Suggested payload:
{json.dumps(record_template, ensure_ascii=False, separators=(",", ":"))}

Ledger path:
{ledger_path}

After recording, print a comparison table. If recall loss is present, write concrete loss_notes and set proposed_succession=true only when the workspace threshold says succession should be proposed. Automatic succession is not allowed."""

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": instruction,
    }
}
sys.stdout.write(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
PY

exit 0
