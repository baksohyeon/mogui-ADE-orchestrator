"""Read orca orchestration JSON across the old and 1.4.246+ key shapes.

From orca 1.4.246 (2026-11-02), `orchestration` commands answer with different
JSON keys (see docs/runbooks/orca-json.md for the measured table). Every
reader of that JSON in this tree routes through here instead of a one-off
key path, so a future shape change touches this module and its test,
nowhere else.

Each `*_id`/`*_handle`/`*_status` function reads the old path first, the new
path second, and returns `None` when neither exists. Importable both as
`from lib import orca_json` (with this file's parent directory on
`sys.path`, as `dispatch` and `worker-wait` already do) and from a
`python3 -c` one-liner with the same `sys.path` seam.
"""

from __future__ import annotations

import json


def task_id(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    task = result.get("task")
    if isinstance(task, dict) and task.get("id"):
        return task["id"]
    return result.get("taskId")


def run_id(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    run = result.get("run")
    if isinstance(run, dict) and run.get("id"):
        return run["id"]
    return result.get("runId")


def terminal_handle(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    terminal = result.get("terminal")
    if isinstance(terminal, dict) and terminal.get("handle"):
        return terminal["handle"]
    # 1.4.246+'s own key name is unconfirmed between these two (peer-seat
    # report, not independently re-measured for this module; see the runbook).
    return result.get("terminalHandle") or result.get("handle")


def dispatch_id(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    dispatch = result.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("id"):
        return dispatch["id"]
    return result.get("dispatchId")


def dispatch_status(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    dispatch = result.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("status"):
        return dispatch["status"]
    return result.get("status")


# `projection.stage.activity` value that means a turn is running. Measured on
# orca 1.4.253 (2026-11-09), `worker-show --full` on a claude worker: `working`
# from about one second after the inject until the turn ended. `done` is left
# out on purpose: it follows the pane, so it can be left over from an earlier
# turn, and a worker that finished fast already reads `completed` on its own
# dispatch record.
_TURN_ACTIVITIES = {"working"}


def turn_stage(result: dict | None) -> str | None:
    """Orca's own answer to "did the injected prompt start a turn", read from
    any of three shapes:

    - `dispatch --inject --json`: `result.prompt.{stages, observation}`
    - `terminal send --json`: `result.send.prompt.{stages, observation}`
    - `worker-show --json --full`: `result.projection.stage.activity`

    Returns `turn_started`, `input_accepted`, `unsupported` (Orca said it
    could not observe the prompt), or `None` when no shape is present.
    """
    if not isinstance(result, dict):
        return None
    projection = result.get("projection")
    stage = projection.get("stage") if isinstance(projection, dict) else None
    if isinstance(stage, dict) and stage.get("activity") in _TURN_ACTIVITIES:
        return "turn_started"
    send = result.get("send")
    prompt = send.get("prompt") if isinstance(send, dict) else result.get("prompt")
    if not isinstance(prompt, dict):
        return None
    if prompt.get("observation") != "supported":
        return "unsupported"
    stages = prompt.get("stages") or []
    if "turn_started" in stages:
        return "turn_started"
    if "input_accepted" in stages:
        return "input_accepted"
    return None


def delivery_id(result: dict | None) -> str | None:
    """`None` on both the old shape's unacked batch and the whole of
    1.4.246+, which dropped `deliveryId`: a consuming `check` there marks the
    batch handled server-side, and `--ack` is a no-op."""
    if not isinstance(result, dict):
        return None
    return result.get("deliveryId")


def messages(result: dict | None) -> list:
    if not isinstance(result, dict):
        return []
    return result.get("messages") or []


# A worker row's "still active" status spelled two ways: `dispatched` (old
# `dispatchStatus`) and `in_progress` (new `outcome`). Normalized rows use
# `in_progress` for both, so a caller has one value to check regardless of
# which orca answered it.
_STATUS_ALIASES = {"dispatched": "in_progress"}


def workers(result: dict | None) -> list[dict]:
    """Normalized `{dispatch_id, task_id, status, terminal}` rows from a
    `worker-list` result, old shape (`dispatchStatus`/`agentTerminalHandle`)
    or new (`outcome`/`terminal`) alike."""
    if not isinstance(result, dict):
        return []
    rows = []
    for worker in result.get("workers") or []:
        if not isinstance(worker, dict):
            continue
        raw_status = worker.get("dispatchStatus")
        if raw_status is None:
            raw_status = worker.get("outcome")
        task_id_value = worker.get("taskId") or worker.get("task_id")
        rows.append(
            {
                "dispatch_id": worker.get("dispatchId"),
                "task_id": task_id_value,
                "status": _STATUS_ALIASES.get(raw_status, raw_status),
                "terminal": worker.get("agentTerminalHandle") or worker.get("terminal"),
            }
        )
    return rows


def next_cursor(result: dict | None) -> str | None:
    """`None` at the last page for both shapes: old `page.hasMore == False`
    (whatever `page.nextCursor` says alongside it), new `nextCursor == ""`."""
    if not isinstance(result, dict):
        return None
    page = result.get("page")
    if isinstance(page, dict):
        if not page.get("hasMore"):
            return None
        return page.get("nextCursor") or None
    return result.get("nextCursor") or None


def parse_envelope(text: str) -> tuple[bool, dict | None, dict | None]:
    """Decode the last JSON document in `text` and split it into
    `(ok, result, error)`.

    orca sometimes prints a human-readable line after the JSON on failure
    (for example `error: run_required: ...`); `json.loads` on the whole
    string then raises, which is the same silent-empty-string failure this
    module exists to replace. `raw_decode` walks the string one JSON value
    at a time and keeps the last one, so trailing non-JSON text after it is
    ignored instead of failing the parse.
    """
    decoder = json.JSONDecoder()
    idx, length = 0, len(text)
    last: dict | None = None
    while idx < length:
        while idx < length and text[idx] in " \t\r\n":
            idx += 1
        if idx >= length:
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        idx = end
        if isinstance(obj, dict):
            last = obj
    if not isinstance(last, dict):
        return False, None, {"code": "no_json", "message": "no JSON object found in output"}
    return bool(last.get("ok")), last.get("result"), last.get("error")
