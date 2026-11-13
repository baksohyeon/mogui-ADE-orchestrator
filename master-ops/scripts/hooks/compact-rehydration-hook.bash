#!/usr/bin/env bash
# PostToolUse/UserPromptSubmit: restore the work layer after compact recall.
# Every failure is silent so a context repair hook cannot block a tool call or prompt.
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
OPS_REPO_DEFAULT="{{OPS_REPO}}"
OPS_REPO="${MOGUI_OPS_REPO:-$OPS_REPO_DEFAULT}"
if [[ "$OPS_REPO" == *"{{OPS_REPO}}"* ]]; then
  OPS_REPO="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd -P)"
fi
STATE_DIR="${MOGUI_STATE_DIR:-${HOME:-$(cd ~ 2>/dev/null && pwd)}/.mogui}"
INSTANCE_CONFIG="${MOGUI_INSTANCE_RUNTIME_CONFIG:-${INSTANCE_RUNTIME_CONFIG:-$OPS_REPO/config/instance-runtime.json}}"
HOOK_INPUT="$(cat 2>/dev/null)"
# The hook payload is in HOOK_INPUT; close the inherited pipe before the
# embedded program starts so a host pipe cannot keep the shell alive.
exec 0<&-

OPS_REPO="$OPS_REPO" \
STATE_DIR="$STATE_DIR" \
INSTANCE_CONFIG="$INSTANCE_CONFIG" \
SCRIPT_DIR="$SCRIPT_DIR" \
HOOK_INPUT="$HOOK_INPUT" \
python3 - "$@" <<'PY' 2>/dev/null || true
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
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


def parse_payload() -> dict[str, Any] | None:
    try:
        value = json.loads(os.environ.get("HOOK_INPUT", "") or "{}")
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
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
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
    return STATE_DIR / "compact-pending" / session


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
    try:
        os.link(path, claimed)
        return claimed
    except FileExistsError:
        try:
            age = dt.datetime.now(dt.timezone.utc).timestamp() - claimed.stat().st_mtime
            if age <= CLAIM_TIMEOUT_SECONDS:
                return None
            claimed.unlink()
            os.link(path, claimed)
            return claimed
        except OSError:
            return None
    except OSError:
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
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
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
    active_raw = command_json(
        ["bd", "list", "--status=in_progress", "--json", "--limit=0", "--flat"],
        OPS_REPO,
    )
    decisions_raw = command_json(
        ["bd", "list", "--status=open", "--type=decision", "--json", "--limit=0", "--flat"],
        OPS_REPO,
    )
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
    return active_lines, decision_lines, "bd list --status=in_progress --json --limit=0 --flat"


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
    payload = command_json(["orca", "terminal", "list", "--json"])
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
            ["git", "-C", str(OPS_REPO), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
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
    extras: Any = None
    for key in ("work_layer_extra_lines", "compact_rehydration_extra_lines", "rehydration_extra_lines"):
        if key in payload:
            extras = payload[key]
            break
    if extras is None and isinstance(payload.get("compact_rehydration"), dict):
        extras = payload["compact_rehydration"].get("extra_lines")
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
        label = compact_text(entry.get("label") or entry.get("name") or "extra", 120)
        if "line" in entry:
            output.append(f"{label}: {compact_text(entry['line'])}")
            continue
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
        if entry.get("command"):
            try:
                result = subprocess.run(
                    str(entry["command"]),
                    cwd=str(OPS_REPO),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return ["unavailable"]
            if result.returncode != 0:
                return ["unavailable"]
            values = [compact_text(line) for line in result.stdout.splitlines() if line.strip()]
            output.extend(f"{label}: {line}" for line in values)
            continue
        return ["unavailable"]
    return output or ["none"]


def section_total(sections: list[dict[str, Any]]) -> int:
    return len("\n".join(line for section in sections for line in [section["heading"], *section["lines"]]))


def compose_work_layer(limit: int = CAP) -> str:
    active, decisions, tracker_command = tracker_section()
    sections: list[dict[str, Any]] = [
        {"heading": "## Role State", "lines": role_state_lines(), "trim": False, "command": ""},
        {"heading": "## In-progress tracker items", "lines": active, "trim": active not in (["unavailable"], ["none"]), "command": tracker_command},
        {"heading": "## Open decisions", "lines": decisions, "trim": decisions not in (["unavailable"], ["none"]), "command": "bd list --status=open --type=decision --json --limit=0 --flat"},
        {"heading": "## Live worker panes", "lines": panes_lines(), "trim": False, "command": "orca terminal list --json"},
        {"heading": "## Uncommitted files in the ops repository", "lines": uncommitted_lines(), "trim": False, "command": "git status --porcelain"},
        {"heading": "## Seat-declared extra lines", "lines": extras_lines(), "trim": True, "command": "read the instance runtime extra-lines configuration"},
    ]
    marker = ""
    omitted = 0
    omitted_command = tracker_command
    while True:
        total = section_total(sections)
        if total <= limit and (not marker or total + len(marker) + 1 <= limit):
            break
        candidates = [section for section in sections if section["trim"] and section["lines"]]
        if not candidates:
            candidates = [section for section in sections if len(section["lines"]) > 1]
        if not candidates:
            break
        candidates[0]["lines"].pop()
        omitted += 1
        omitted_command = candidates[0]["command"]
        marker = f"{omitted} more: run {omitted_command}"
        if section_total(sections) + len(marker) + 1 <= limit:
            continue
    if marker:
        output = "\n".join(line for section in sections for line in [section["heading"], *section["lines"]])
        combined = output + "\n" + marker
        if len(combined) <= limit:
            return combined
        return output[: max(0, limit - len(marker) - 1)] + "\n" + marker
    output = "\n".join(line for section in sections for line in [section["heading"], *section["lines"]])
    if len(output) <= limit:
        return output
    return output[: max(0, limit - 1)] + "\n"


def fit_post_tool_context(context: str) -> str:
    wrapper = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}
    def serialized_size(value: str) -> int:
        wrapper["hookSpecificOutput"]["additionalContext"] = value
        return len(json.dumps(wrapper, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    if serialized_size(context) <= CAP:
        return context
    lines = context.splitlines()
    marker = lines[-1] if lines and " more: run " in lines[-1] else ""
    body = "\n".join(lines[:-1]) if marker else context
    body_bytes = body.encode("utf-8")
    low, high = 0, len(body_bytes)
    best = ""
    while low <= high:
        midpoint = (low + high) // 2
        prefix = body_bytes[:midpoint].decode("utf-8", errors="ignore").rstrip()
        candidate = prefix + (("\n" + marker) if marker else "")
        if serialized_size(candidate) <= CAP:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


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
    if compacted_at is not None and (dt.datetime.now(dt.timezone.utc) - compacted_at).total_seconds() > STALE_SECONDS:
        delete(path)
        return
    event = event_name(payload, sys.argv[1:]).lower()
    recorded = recorded_recall(marker)
    skipped = False
    if not recorded:
        if event == "userpromptsubmit":
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
        if skipped:
            append_recall_skipped(marker)
        prefix = ""
        if skipped:
            prefix = "[compact-rehydration] Recall check was not recorded; the context-quality measurement is contaminated.\n"
        if event == "posttooluse":
            wrapper_size = len(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ""}}, ensure_ascii=False, separators=(",", ":")))
            context = prefix + compose_work_layer(max(1, CAP - wrapper_size - len(prefix)))
            context = fit_post_tool_context(context)
        else:
            context = prefix + compose_work_layer(max(1, CAP - len(prefix)))
        if event == "posttooluse":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}, ensure_ascii=False, separators=(",", ":")))
        elif event == "userpromptsubmit":
            print(context)
    finally:
        delete(claimed)
        delete(path)


main()
PY
exit 0
