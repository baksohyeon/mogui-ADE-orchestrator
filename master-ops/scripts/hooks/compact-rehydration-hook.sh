#!/usr/bin/env bash
# PostToolUse/UserPromptSubmit: restore the work layer after compact recall.
# Every failure is silent so a context repair hook cannot block a tool call or prompt.
set +e

VERDICT="pass"
FIRE_LOG="${MOGUI_HOOK_FIRE_LOG:-${HOME:-$(cd ~ 2>/dev/null && pwd)}/.mogui/hook-fire-log.jsonl}"
json_str() {
  local value="${1-}"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=$(printf '%s' "$value" | tr -d '\000-\037\177')
  printf '%s' "$value"
}
derive_session_kind() {
  if [ -n "${ORCA_TASK_ID:-}" ] || [ -n "${ORCA_DISPATCH_ID:-}" ] || [[ "$PWD" == *".orca/worktrees"* ]]; then
    printf 'worker'
  elif [ -f "$PWD/docs/MASTER-OPERATIONS.md" ]; then
    printf 'master'
  else
    printf 'unknown'
  fi
}
log_fire() {
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || return 0
  local session_kind
  session_kind="$(derive_session_kind)"
  printf '{"ts":%d,"hook":"compact-rehydration-hook","event":"%s","cwd":"%s","runtime_hint":"%s","session_kind":"%s","verdict":"%s"}\n' \
    "$(date +%s)" "$(json_str "${1:-UserPromptSubmit}")" "$(json_str "$PWD")" "$(json_str "${MOGUI_RUNTIME_HINT:-unknown}")" "$(json_str "$session_kind")" "$(json_str "$VERDICT")" >> "$FIRE_LOG" 2>/dev/null || true
}
trap 'log_fire "${1:-UserPromptSubmit}"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
if ! source "$SCRIPT_DIR/compact-rehydration-constants.inc" 2>/dev/null; then
  COMPACT_SESSION_ID_PATTERN='[A-Za-z0-9._:-]+'
  COMPACT_PENDING_DIR_NAME='compact-pending'
fi
OPS_REPO_DEFAULT="{{OPS_REPO}}"
OPS_REPO="${MOGUI_OPS_REPO:-$OPS_REPO_DEFAULT}"
if [[ "$OPS_REPO" == *"{{OPS_REPO}}"* ]]; then
  OPS_REPO="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd -P)"
fi
STATE_DIR="${MOGUI_STATE_DIR:-${HOME:-$(cd ~ 2>/dev/null && pwd)}/.mogui}"
INSTANCE_CONFIG="${MOGUI_INSTANCE_RUNTIME_CONFIG:-${INSTANCE_RUNTIME_CONFIG:-$OPS_REPO/config/instance-runtime.json}}"
PENDING_DIR="$STATE_DIR/$COMPACT_PENDING_DIR_NAME"
shopt -s nullglob
pending_entries=("$PENDING_DIR"/* "$PENDING_DIR"/.[!.]* "$PENDING_DIR"/..?*)
if [ "${#pending_entries[@]}" -eq 0 ]; then
  exit 0
fi

OPS_REPO="$OPS_REPO" \
STATE_DIR="$STATE_DIR" \
INSTANCE_CONFIG="$INSTANCE_CONFIG" \
SCRIPT_DIR="$SCRIPT_DIR" \
PENDING_DIR="$PENDING_DIR" \
COMPACT_SESSION_ID_PATTERN="$COMPACT_SESSION_ID_PATTERN" \
COMPACT_PENDING_DIR_NAME="$COMPACT_PENDING_DIR_NAME" \
CONTEXT_LOG_WRITER="${CONTEXT_QUALITY_LOG_WRITER:-$SCRIPT_DIR/../context-quality-log.sh}" \
python3 - "$@" 3<&0 <<'PY' 2>/dev/null || true
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


# Leave room for JSON framing and UTF-8 encoding while keeping the documented
# 9,000-character ceiling on the emitted hook payload.
CAP = 8_500
STALE_SECONDS = 6 * 60 * 60
POST_TOOL_LIMIT = 2
CLAIM_TIMEOUT_SECONDS = 120
OPS_REPO = Path(os.environ.get("OPS_REPO", "")).expanduser()
STATE_DIR = Path(os.environ.get("STATE_DIR", "")).expanduser()
INSTANCE_CONFIG = Path(os.environ.get("INSTANCE_CONFIG", "")).expanduser()
SCRIPT_DIR = Path(os.environ.get("SCRIPT_DIR", "")).expanduser()
PENDING_DIR = Path(os.environ.get("PENDING_DIR", "")).expanduser()
CONTEXT_LOG_WRITER = Path(os.environ.get("CONTEXT_LOG_WRITER", "")).expanduser()
SESSION_ID_PATTERN = os.environ.get("COMPACT_SESSION_ID_PATTERN", "")
ACTIVE_TRACKER_COMMAND = ("bd", "list", "--status=in_progress", "--json", "--limit=0", "--flat")
DECISION_TRACKER_COMMAND = ("bd", "list", "--status=open", "--type=decision", "--json", "--limit=0", "--flat")
PANE_COMMAND = ("orca", "terminal", "list", "--json")
GIT_STATUS_COMMAND = ("git", "status", "--porcelain")


def display_command(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def post_tool_payload(context: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}


def parse_payload() -> dict[str, Any] | None:
    try:
        with os.fdopen(3, "rb") as handle:
            raw = handle.read()
        value = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def event_name(payload: dict[str, Any], argv: list[str]) -> str:
    value = payload.get("hook_event_name") or payload.get("event")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if argv and argv[0].strip():
        return argv[0].strip()
    return os.environ.get("CLAUDE_HOOK_EVENT", "UserPromptSubmit")


def session_name(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if not SESSION_ID_PATTERN or not re.fullmatch(SESSION_ID_PATTERN, value):
        return None
    return value


def parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def marker_path(session: str) -> Path:
    return PENDING_DIR / session


def read_marker(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    if value.get("session_id") and value.get("session_id") != path.name:
        return None
    if not isinstance(value.get("log_path"), str) or not value["log_path"]:
        return None
    try:
        value["log_offset"] = max(0, int(value.get("log_offset", 0)))
        value["post_tool_uses"] = max(0, int(value.get("post_tool_uses", 0)))
    except (TypeError, ValueError):
        return None
    return value


def write_marker(path: Path, marker: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(marker, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def recorded_recall(marker: dict[str, Any]) -> bool:
    log_path = Path(marker["log_path"]).expanduser()
    offset = marker["log_offset"]
    try:
        with log_path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except OSError:
        return False
    for raw in data.splitlines(keepends=True):
        if not raw.endswith(b"\n"):
            continue
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(row, dict)
            and row.get("session") == marker.get("session_id")
            and row.get("event") == "compact"
        ):
            return True
    return False


def claim(path: Path) -> Path | None:
    claimed = path.with_name(path.name + ".claimed")
    for _ in range(3):
        try:
            descriptor = os.open(claimed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            return claimed
        except FileExistsError:
            try:
                age = dt.datetime.now(dt.timezone.utc).timestamp() - claimed.stat().st_mtime
            except FileNotFoundError:
                continue
            except OSError:
                return None
            if age <= CLAIM_TIMEOUT_SECONDS:
                return None
            stale_name = claimed.with_name(
                f"{claimed.name}.stale-{os.getpid()}-{time.time_ns()}"
            )
            try:
                os.rename(claimed, stale_name)
            except FileNotFoundError:
                continue
            except OSError:
                return None
            try:
                descriptor = os.open(claimed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(descriptor)
            except (FileExistsError, OSError):
                try:
                    stale_name.unlink()
                except OSError:
                    pass
                return None
            try:
                stale_name.unlink()
            except OSError:
                pass
            return claimed
        except OSError:
            return None
    return None


def delete(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def append_recall_skipped(marker: dict[str, Any]) -> None:
    log_path = Path(marker["log_path"]).expanduser()
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session": marker.get("session_id", ""),
        "event": "recall_skipped",
        "model": "<hook>",
        "recall": {},
        "loss_notes": ["compact recall record was not recorded before rehydration"],
        "proposed_succession": False,
    }
    try:
        if not CONTEXT_LOG_WRITER.is_file():
            return
        environment = os.environ.copy()
        environment["CONTEXT_QUALITY_LOG"] = str(log_path)
        subprocess.run(
            ["bash", str(CONTEXT_LOG_WRITER), json.dumps(row, ensure_ascii=False, separators=(",", ":"))],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def command_json(argv: list[str], cwd: Path | None = None) -> Any | None:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return None


def rows_from(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("issues", "items", "data", "results", "terminals", "workers"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
        for key in ("result", "payload"):
            nested = rows_from(value.get(key))
            if nested is not None:
                return nested
    return None


def row_time(row: dict[str, Any]) -> dt.datetime | None:
    for key in ("updated_at", "updated", "modified_at", "modified", "created_at"):
        value = parse_time(row.get(key))
        if value is not None:
            return value
    return None


def compact_text(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_issue(row: dict[str, Any]) -> str:
    issue_id = compact_text(row.get("id"), 80)
    title = compact_text(row.get("title") or row.get("name") or row.get("summary"))
    if issue_id and title:
        return f"- {issue_id}: {title}"
    return "- " + (title or issue_id or compact_text(row))


def tracker_section() -> tuple[list[str], list[str], str]:
    active_raw = command_json(ACTIVE_TRACKER_COMMAND, OPS_REPO)
    decisions_raw = command_json(DECISION_TRACKER_COMMAND, OPS_REPO)
    active = rows_from(active_raw)
    decisions = rows_from(decisions_raw)
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=48)

    def ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: (
                row_time(row) is not None and row_time(row) >= cutoff,
                row_time(row) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            ),
            reverse=True,
        )

    active_lines = [format_issue(row) for row in ordered(active)] if active is not None else ["unavailable"]
    decision_lines = [format_issue(row) for row in ordered(decisions)] if decisions is not None else ["unavailable"]
    if not active_lines:
        active_lines = ["none"]
    if not decision_lines:
        decision_lines = ["none"]
    return active_lines, decision_lines, display_command(ACTIVE_TRACKER_COMMAND)


def role_state_lines() -> list[str]:
    path = OPS_REPO / "docs" / "runbooks" / "role-state.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["unavailable"]
    role = next((line.strip() for line in lines if line.startswith("Current Role:")), "")
    lock = next((line.strip() for line in lines if line.startswith("Role Lock:")), "")
    if not role or not lock or not role.partition(":")[2].strip() or not lock.partition(":")[2].strip():
        return ["unavailable"]
    return [f"[role-state] {role} | {lock}"]


def panes_lines() -> list[str]:
    payload = command_json(list(PANE_COMMAND))
    rows = rows_from(payload)
    if rows is None:
        return ["unavailable"]
    lines: list[str] = []
    for row in rows:
        handle = row.get("terminalHandle") or row.get("handle") or row.get("id") or row.get("name")
        label = row.get("name") or row.get("agent") or row.get("runtime") or "pane"
        state = row.get("status") or row.get("state") or "live"
        if handle:
            lines.append(f"- {compact_text(handle, 100)}: {compact_text(label, 100)} ({compact_text(state, 80)})")
        else:
            lines.append("- " + compact_text(row))
    return lines or ["none"]


def uncommitted_lines() -> list[str]:
    try:
        result = subprocess.run(
            list(GIT_STATUS_COMMAND),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=str(OPS_REPO),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["unavailable"]
    if result.returncode != 0:
        return ["unavailable"]
    count = sum(1 for line in result.stdout.splitlines() if line.strip())
    return [str(count)]


def count_json(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, (list, dict)):
        return str(len(value))
    return "1"


def extras_lines() -> list[str]:
    if not INSTANCE_CONFIG.is_file():
        return ["none"]
    try:
        payload = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["unavailable"]
    if not isinstance(payload, dict):
        return ["unavailable"]
    extras: Any = payload.get("work_layer_extra_lines")
    if extras is None:
        return ["none"]
    if isinstance(extras, dict):
        extras = [extras]
    if not isinstance(extras, list):
        return ["unavailable"]
    output: list[str] = []
    for entry in extras:
        if isinstance(entry, str):
            output.append(compact_text(entry))
            continue
        if not isinstance(entry, dict):
            return ["unavailable"]
        label = compact_text(entry.get("label") or "extra", 120)
        if "value" in entry:
            output.append(f"{label}: {compact_text(entry['value'])}")
            continue
        if entry.get("path"):
            source = Path(str(entry["path"])).expanduser()
            if not source.is_absolute():
                source = OPS_REPO / source
            try:
                output.append(f"{label}: {count_json(source)}")
            except (OSError, json.JSONDecodeError):
                return ["unavailable"]
            continue
        return ["unavailable"]
    return output or ["none"]


def render_sections(sections: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for section in sections:
        rendered.append(section["heading"])
        rendered.extend(section["lines"])
        if section["omitted"]:
            rendered.append(f"{section['omitted']} more: run {section['command']}")
    return "\n".join(rendered)


def context_fits(context: str, limit: int, post_tool: bool) -> bool:
    if post_tool:
        return len(json.dumps(post_tool_payload(context), ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= limit
    return len(context.encode("utf-8")) <= limit


def compose_work_layer(limit: int = CAP, prefix: str = "", post_tool: bool = False) -> str:
    active, decisions, tracker_command = tracker_section()
    sections: list[dict[str, Any]] = [
        {"key": "role", "heading": "## Role State", "lines": role_state_lines(), "command": "read docs/runbooks/role-state.md", "omitted": 0},
        {"key": "active", "heading": "## In-progress tracker items", "lines": active, "command": tracker_command, "omitted": 0},
        {"key": "decisions", "heading": "## Open decisions", "lines": decisions, "command": display_command(DECISION_TRACKER_COMMAND), "omitted": 0},
        {"key": "panes", "heading": "## Live worker panes", "lines": panes_lines(), "command": display_command(PANE_COMMAND), "omitted": 0},
        {"key": "uncommitted", "heading": "## Uncommitted files in the ops repository", "lines": uncommitted_lines(), "command": display_command(GIT_STATUS_COMMAND), "omitted": 0},
        {"key": "extras", "heading": "## Seat-declared extra lines", "lines": extras_lines(), "command": "read the instance runtime extra-lines configuration", "omitted": 0},
    ]
    trim_order = ("extras", "decisions", "active", "panes", "uncommitted", "role")

    def can_trim(section: dict[str, Any]) -> bool:
        lines = section["lines"]
        return bool(lines) and not (len(lines) == 1 and lines[0] in ("unavailable", "none"))

    def next_trimmed() -> bool:
        for key in trim_order:
            section = next(item for item in sections if item["key"] == key)
            if can_trim(section):
                section["lines"].pop()
                section["omitted"] += 1
                return True
        return False

    while not context_fits(prefix + render_sections(sections), limit, post_tool):
        if not next_trimmed():
            break
    return prefix + render_sections(sections)


def main() -> None:
    payload = parse_payload()
    if payload is None:
        return
    session = session_name(payload)
    if session is None:
        return
    path = marker_path(session)
    # Keep the no-marker path to one existence check and no output.
    if not path.is_file():
        return
    marker = read_marker(path)
    if marker is None:
        return
    compacted_at = parse_time(marker.get("compact_time"))
    if compacted_at is None or (dt.datetime.now(dt.timezone.utc) - compacted_at).total_seconds() > STALE_SECONDS:
        delete(path)
        return
    event = event_name(payload, sys.argv[1:]).lower()
    recorded = recorded_recall(marker)
    skipped = False
    if not recorded:
        if event == "userpromptsubmit":
            if marker["post_tool_uses"] == 0:
                print("[compact-rehydration] Recall check is owed; the work layer follows the recorded recall.")
                return
            skipped = True
        elif event == "posttooluse":
            if marker["post_tool_uses"] < POST_TOOL_LIMIT:
                marker["post_tool_uses"] += 1
                try:
                    write_marker(path, marker)
                except OSError:
                    pass
                return
            skipped = True
        else:
            return
    claimed = claim(path)
    if claimed is None:
        return
    try:
        if not path.is_file():
            return
        if skipped:
            append_recall_skipped(marker)
        prefix = ""
        if skipped:
            prefix = "[compact-rehydration] Recall check was not recorded; the context-quality measurement is contaminated.\n"
        if event == "posttooluse":
            context = compose_work_layer(CAP, prefix=prefix, post_tool=True)
        else:
            context = compose_work_layer(CAP, prefix=prefix)
        if event == "posttooluse":
            print(json.dumps(post_tool_payload(context), ensure_ascii=False, separators=(",", ":")))
        elif event == "userpromptsubmit":
            print(context)
    finally:
        delete(path)
        delete(claimed)


main()
PY
exit 0
