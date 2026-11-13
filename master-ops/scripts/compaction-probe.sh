#!/usr/bin/env bash
# SessionStart(compact) context-quality recall probe.
# This writes a per-session marker and emits recall instructions. It records no
# secret values and implements no dispatch or security enforcement.
set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

INPUT="$(cat 2>/dev/null)"
CONTEXT_LOG_PATH="${CONTEXT_QUALITY_LOG:-$HOME/.mogui/monitors/mg/context-quality.jsonl}"
DISPATCH_LEDGER_PATH="${DISPATCH_GATE_LEDGER:-${MOGUI_STATE_DIR:-$HOME/.mogui}/dispatch-ledger.jsonl}"
STATE_DIR="${MOGUI_STATE_DIR:-${HOME:-$(cd ~ 2>/dev/null && pwd)}/.mogui}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
CONTEXT_LOG_SCRIPT="$SCRIPT_DIR/context-quality-log.sh"

PROBE_INPUT="$INPUT" \
CONTEXT_LOG_PATH="$CONTEXT_LOG_PATH" \
DISPATCH_LEDGER_PATH="$DISPATCH_LEDGER_PATH" \
STATE_DIR="$STATE_DIR" \
CONTEXT_LOG_SCRIPT="$CONTEXT_LOG_SCRIPT" \
python3 <<'PY' 2>/dev/null || true
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import shlex

try:
    payload = json.loads(os.environ.get("PROBE_INPUT", "") or "{}")
except Exception:
    sys.exit(0)

if payload.get("source") != "compact":
    sys.exit(0)

session_id = payload.get("session_id") or "<unknown-session>"
context_log_path = os.environ.get(
    "CONTEXT_LOG_PATH",
    os.path.expanduser("~/.mogui/monitors/mg/context-quality.jsonl"),
)
dispatch_ledger_path = os.environ.get(
    "DISPATCH_LEDGER_PATH",
    os.path.expanduser("~/.mogui/dispatch-ledger.jsonl"),
)

safe_session = isinstance(session_id, str) and re.fullmatch(r"[A-Za-z0-9._:-]+", session_id)
if safe_session:
    state_dir = Path(os.environ.get("STATE_DIR", "") or "").expanduser()
    context_log = Path(context_log_path).expanduser().resolve()
    marker_dir = state_dir / "compact-pending"
    marker_path = marker_dir / str(session_id)
    try:
        marker_dir.mkdir(parents=True, exist_ok=True)
        log_offset = context_log.stat().st_size if context_log.is_file() else 0
        marker = {
            "compact_time": datetime.now(timezone.utc).isoformat(),
            "log_path": str(context_log),
            "log_offset": log_offset,
            "session_id": str(session_id),
            "post_tool_uses": 0,
        }
        temporary = marker_path.with_name(marker_path.name + ".tmp")
        temporary.write_text(json.dumps(marker, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(marker_path)
    except Exception:
        pass

record_template = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "workspace": "mogui-master",
    "session": session_id,
    "event": "compact",
    "model": "<actual model/tool version stamp>",
    "recall": {
        "tracks": "<remembered active tracks>",
        "cards": "<remembered card ids for tracks dispatched or landed today>",
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
R5 Dispatch cards: from memory only, the card ids of the tracks dispatched or landed today (KST). After recording, verify against the ledger's card column.

Append one JSON record before source verification. Suggested payload:
{json.dumps(record_template, ensure_ascii=False, separators=(",", ":"))}

Append the recall record with this runnable command:
{'CONTEXT_QUALITY_LOG=' + shlex.quote(str(Path(context_log_path).expanduser().resolve()))} {shlex.quote(str(Path(os.environ.get('CONTEXT_LOG_SCRIPT', '')).expanduser().resolve()))} {shlex.quote(json.dumps(record_template, ensure_ascii=False, separators=(',', ':')))}

Dispatch ledger path:
{dispatch_ledger_path}

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
