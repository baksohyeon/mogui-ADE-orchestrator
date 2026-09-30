"""Fail-open JSONL event logging for mogui scripts."""

import json
import os
import re
import time


LOG_DIR = os.path.expanduser("~/.mogui")

# Two directories up from scripts/mogui_log.py: the ops/runtime repo root,
# wherever this file has been template-applied to. The descriptor lives here
# regardless of the caller's cwd (the master commonly runs from the
# workspace root, a different directory entirely).
_RUNTIME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SECRET = re.compile(
    r"(?:"
    r"sk-[A-Za-z0-9]{8,}|"
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{12,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"xox[baprs]-[0-9A-Za-z-]{10,}|"
    r"sk-ant-api03-[0-9A-Za-z_-]{20,}|"
    r"-----BEGIN [^-\r\n]+-----|"
    r"Basic\s+[A-Za-z0-9._~+/=:-]+|"
    r"Bearer\s+[A-Za-z0-9._~+/=-]+|"
    r"(?<![A-Za-z0-9_.-])/(?!/)(?:[A-Za-z0-9._-]+/)+[^\s\"'<>]*"
    r")",
    re.IGNORECASE,
)


def _scrub(value):
    """Replace secret values and home paths before they reach the log."""
    if isinstance(value, str):
        return _SECRET.sub("«redacted»", value)
    if isinstance(value, dict):
        return {_scrub(k): _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    return value


def _descriptor_workspace_root():
    """Read workspace_root from <runtime-root>/config/workspace-descriptor.json,
    if any, where runtime-root is this script's own location (_RUNTIME_ROOT),
    not the caller's cwd."""
    path = os.path.join(_RUNTIME_ROOT, "config", "workspace-descriptor.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    root = data.get("workspace_root") if isinstance(data, dict) else None
    return root.strip() if isinstance(root, str) and root.strip() else None


_SESSION_KIND_CACHE = None


def _session_kind() -> str:
    """Resolved once per process and cached: cwd, env, and the descriptor file
    are all fixed for a process's lifetime, so re-deriving this on every
    `emit()` call would pay a stat/open/json-parse per event for no reason.
    """
    global _SESSION_KIND_CACHE
    if _SESSION_KIND_CACHE is not None:
        return _SESSION_KIND_CACHE
    cwd = os.getcwd()
    seat_root = os.environ.get("MOGUI_SEAT_ROOT") or _descriptor_workspace_root()
    if seat_root and os.path.realpath(cwd) == os.path.realpath(os.path.expanduser(seat_root)):
        _SESSION_KIND_CACHE = "master"
    elif os.environ.get("ORCA_TASK_ID") or ".orca/worktrees" in cwd.replace(os.sep, "/"):
        _SESSION_KIND_CACHE = "worker"
    else:
        _SESSION_KIND_CACHE = "unknown"
    return _SESSION_KIND_CACHE


def emit(level, event, outcome, *, component="tool-impl", evidence="observed",
         reason="", session_kind=None, runtime_hint=None, msg="", **fields):
    """Append one event line and never let logging failure escape the caller."""
    try:
        scrubbed_msg = _scrub(msg)
        line = {
            "ts": int(time.time()), "level": level, "event": event,
            "component": component, "outcome": outcome, "evidence": evidence,
            "session_kind": session_kind or _session_kind(),
            "runtime_hint": runtime_hint or os.environ.get("MOGUI_RUNTIME_HINT", "unknown"),
            "reason": _scrub(reason),
            "msg": scrubbed_msg[:200] if isinstance(scrubbed_msg, str) else scrubbed_msg,
        }
        line.update({_scrub(k): _scrub(v) for k, v in fields.items()})
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "event-log.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, ensure_ascii=False) + "\n")
        return line
    except Exception:
        return locals().get("line", {
            "ts": int(time.time()), "level": level, "event": event,
            "outcome": outcome, "evidence": evidence,
        })


def human(line: dict) -> str:
    """Derive the owner-facing one-line summary from a structured event."""
    labels = {"pass": "OK", "finding": "검출", "undetermined": "결정불가"}
    tag = labels.get(line.get("outcome"), "결정불가")
    return f"[{line.get('event', '')}] {tag} — {line.get('reason', '')} ({line.get('evidence', '')})"
