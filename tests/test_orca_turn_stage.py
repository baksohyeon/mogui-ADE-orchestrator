"""orca_json.turn_stage over the JSON shapes measured on orca 1.4.253 (2026-11-09).

Values are scrubbed placeholders; the keys and the stage values are verbatim.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "master-ops" / "scripts" / "lib" / "orca_json.py"
_spec = importlib.util.spec_from_file_location("orca_json_turn_stage", MODULE)
orca_json = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orca_json)


def _inject(stages: list[str], provider: str, observation: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "result": {
                "dispatch": {"id": "ctx_example", "status": "dispatched"},
                "injected": True,
                "prompt": {
                    "requestId": "req_example",
                    "stages": stages,
                    "provider": provider,
                    "observation": observation,
                    "processIncarnation": "inc_example",
                    "generation": 1,
                    "baselineWorkingSequence": 0,
                    "baselineExplicitWorkingStartedAt": None,
                    "baselinePermissionSequence": 0,
                },
                "mutation": {"requestId": "req_example", "replayed": False},
            },
        }
    )


def _worker_show(activity: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "result": {
                "dispatch": {"id": "ctx_example", "status": "dispatched"},
                "projection": {
                    "stage": {
                        "worker": "unsupervised",
                        "dispatch": "dispatched",
                        "detail": None,
                        "activity": activity,
                    }
                },
                "observation": {"status": "live", "exactWorker": True, "agentWait": None},
            },
        }
    )


TERMINAL_SEND_TURN_STARTED = json.dumps(
    {
        "ok": True,
        "result": {
            "send": {
                "handle": "term_example",
                "accepted": True,
                "bytesWritten": 57,
                "prompt": {
                    "requestId": "req_example",
                    "stages": ["input_accepted", "turn_started"],
                    "provider": "claude",
                    "observation": "supported",
                },
            },
            "mutation": {"requestId": "req_example", "replayed": False},
        },
    }
)


def stage(raw: str) -> str | None:
    _ok, result, _error = orca_json.parse_envelope(raw)
    return orca_json.turn_stage(result)


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        (_inject(["input_accepted", "turn_started"], "claude", "supported"), "turn_started"),
        (_inject(["input_accepted"], "claude", "supported"), "input_accepted"),
        (_inject(["input_accepted"], "unsupported", "unsupported"), "unsupported"),
        (TERMINAL_SEND_TURN_STARTED, "turn_started"),
        (_worker_show("working"), "turn_started"),
        (_worker_show("done"), None),
        (_worker_show("unknown"), None),
    ],
    ids=[
        "inject-turn-started",
        "inject-input-accepted-only",
        "inject-unsupported",
        "terminal-send-turn-started",
        "worker-show-working",
        "worker-show-done",
        "worker-show-unknown",
    ],
)
def test_turn_stage_reads_each_measured_shape(raw: str, want: str | None) -> None:
    assert stage(raw) == want


def test_turn_stage_tolerates_missing_keys() -> None:
    assert stage(json.dumps({"ok": True, "result": {"dispatch": {"id": "ctx_example"}}})) is None
    assert stage(json.dumps({"ok": True, "result": {"prompt": {}}})) == "unsupported"
    assert stage(json.dumps({"ok": True, "result": {"projection": {"stage": None}}})) is None
    assert stage("not json at all") is None
    assert orca_json.turn_stage(None) is None
