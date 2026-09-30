"""Regression coverage for master-ops/scripts/worker-wait.

worker-wait is self-contained (master-ops/ is template-applied into repos with
no src/ tree), so it is loaded via runpy exactly like tests/test_dispatch_gate.py
loads scripts/dispatch-gate, rather than imported as a package.
"""

from __future__ import annotations

import json
import os
import runpy
import stat
import time
from pathlib import Path

import pytest

from windows_exec_surface import skip_windows_exec_surface


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "master-ops" / "scripts" / "worker-wait"


def _load():
    return runpy.run_path(str(_script()), run_name="worker_wait_test")


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# --- _compute_verdict: pure, no subprocess ----------------------------------


def test_pid_gone_with_no_worker_done_is_dead() -> None:
    mod = _load()
    verdict = mod["_compute_verdict"](
        pid="123", pid_alive=False, age_seconds=1.0, stall_seconds=600, sweep_class="working"
    )
    assert verdict == "DEAD"
    # Failability: a verdict function that ignored pid_alive would call this working.
    assert (
        mod["_compute_verdict"](
            pid="123", pid_alive=True, age_seconds=1.0, stall_seconds=600, sweep_class="working"
        )
        != "DEAD"
    )


def test_pid_alive_output_stale_sweep_idle_is_stall() -> None:
    mod = _load()
    verdict = mod["_compute_verdict"](
        pid="123", pid_alive=True, age_seconds=9999.0, stall_seconds=600, sweep_class="idle"
    )
    assert verdict == "STALL"
    # Failability: fresh output must not be called STALL even with the same sweep class.
    assert (
        mod["_compute_verdict"](
            pid="123", pid_alive=True, age_seconds=1.0, stall_seconds=600, sweep_class="idle"
        )
        == "working"
    )


def test_pid_alive_output_fresh_is_working() -> None:
    mod = _load()
    assert (
        mod["_compute_verdict"](
            pid="123", pid_alive=True, age_seconds=5.0, stall_seconds=600, sweep_class=None
        )
        == "working"
    )


def test_no_pid_is_unknown() -> None:
    mod = _load()
    assert (
        mod["_compute_verdict"](
            pid=None, pid_alive=None, age_seconds=None, stall_seconds=600, sweep_class=None
        )
        == "UNKNOWN"
    )
    # Failability: a no-pid row must never be reported DEAD or STALL — those
    # verdicts require a measured pid per the contract.
    assert (
        mod["_compute_verdict"](
            pid=None, pid_alive=None, age_seconds=9999.0, stall_seconds=600, sweep_class="idle"
        )
        not in ("DEAD", "STALL")
    )


def test_no_pid_but_sweep_says_working_is_working() -> None:
    mod = _load()
    assert (
        mod["_compute_verdict"](
            pid=None, pid_alive=None, age_seconds=None, stall_seconds=600, sweep_class="working"
        )
        == "working"
    )


# --- ledger indexing ---------------------------------------------------------


def test_ledger_index_maps_job_id_to_pid_and_pane(tmp_path: Path) -> None:
    mod = _load()
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({"job_id": "ctx_a", "kind": "host_diversity_audit"}),
                json.dumps({"job_id": "ctx_b", "worker_pid": "42", "pane": "term_b"}),
                json.dumps({"job_id": "ctx_b", "pane": "term_b_2"}),
                "not json",
            ]
        ),
        encoding="utf-8",
    )
    index = mod["_ledger_index"](ledger)
    assert "ctx_a" not in index
    assert index["ctx_b"] == {"pid": "42", "pane": "term_b_2"}


# --- lock ---------------------------------------------------------------------


@skip_windows_exec_surface
def test_second_waiter_refuses_while_first_holds_a_live_lock(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ps",
        "#!/usr/bin/env bash\n[ \"$2\" = 4242 ] && exit 0 || exit 1\n",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    lock_dir = tmp_path / ".mogui" / "worker-wait"
    lock_dir.mkdir(parents=True)
    (lock_dir / "run_x.lock").write_text("4242", encoding="utf-8")

    assert mod["_acquire_lock"]("run_x") is None


@skip_windows_exec_surface
def test_stale_lock_with_dead_pid_is_taken_over(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ps",
        "#!/usr/bin/env bash\nexit 1\n",  # every pid reports dead
    )
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    lock_dir = tmp_path / ".mogui" / "worker-wait"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "run_x.lock"
    lock_path.write_text("99999", encoding="utf-8")

    acquired = mod["_acquire_lock"]("run_x")
    assert acquired == lock_path
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


@skip_windows_exec_surface
def test_main_exits_2_when_lock_is_held(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ps",
        "#!/usr/bin/env bash\n[ \"$2\" = 4242 ] && exit 0 || exit 1\n",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    lock_dir = tmp_path / ".mogui" / "worker-wait"
    lock_dir.mkdir(parents=True)
    (lock_dir / "run_x.lock").write_text("4242", encoding="utf-8")

    assert mod["main"](["--run", "run_x"]) == 2


# --- messaging: heartbeat ack-chain vs a real wake --------------------------


def _write_fake_orca_for_check(tmp_path: Path) -> Path:
    """A fake `orca` whose `orchestration check` replies vary by call count.

    Call 1: a heartbeat-only batch with a keepalive doc ahead of it (proves the
    raw_decode path, not json.loads, is what parses the stream).
    Call 2 (must carry --ack from call 1's deliveryId): a worker_done batch.
    """

    counter = tmp_path / "calls"
    counter.write_text("0", encoding="utf-8")
    script = tmp_path / "orca"
    _write_executable(
        script,
        f"""#!/usr/bin/env bash
if [ "$1 $2" = "orchestration check" ]; then
  n=$(cat "{counter}")
  n=$((n + 1))
  echo "$n" > "{counter}"
  if [ "$n" = "1" ]; then
    printf '{{"_keepalive": true}}'
    printf '{{"result": {{"deliveryId": "d1", "messages": [{{"type": "heartbeat"}}]}}}}'
  else
    ack_seen=0
    for a in "$@"; do [ "$a" = "d1" ] && ack_seen=1; done
    if [ "$ack_seen" != 1 ]; then
      echo "FAIL: second check call did not chain --ack d1" >&2
      exit 3
    fi
    printf '{{"result": {{"deliveryId": "d2", "messages": [{{"type": "worker_done", "from": "term_x", "subject": "done"}}]}}}}'
  fi
else
  echo "{{}}"
fi
""",
    )
    return script


@skip_windows_exec_surface
def test_heartbeat_batch_is_acked_and_rearmed_without_waking(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    fake_orca_dir = tmp_path
    _write_fake_orca_for_check(fake_orca_dir)
    monkeypatch.setenv("PATH", f"{fake_orca_dir}:{os.environ['PATH']}")

    payload, ack = mod["_wait_for_message"]("run_x", None)

    assert ack == "d1"
    assert payload is not None
    assert payload["messages"][0]["type"] == "worker_done"
    assert payload["deliveryId"] == "d2"


@skip_windows_exec_surface
def test_worker_done_wakes_and_is_not_acked(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    script = tmp_path / "orca"
    _write_executable(
        script,
        """#!/usr/bin/env bash
if [ "$1 $2" = "orchestration check" ]; then
  for a in "$@"; do [ "$a" = "--ack" ] && { echo "FAIL: worker_done call was acked" >&2; exit 3; }; done
  printf '{"result": {"deliveryId": "d9", "messages": [{"type": "worker_done"}]}}'
else
  echo "{}"
fi
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    payload, ack = mod["_wait_for_message"]("run_x", None)

    assert payload["messages"][0]["type"] == "worker_done"
    # Not acked: no --ack flag was ever sent for this delivery, which the fake
    # orca itself would have refused with exit 3 above had it seen one.
    assert ack is None


# --- accounting end to end: DEAD, STALL, working, OPEN_PANE in one pass ----


@skip_windows_exec_surface
def test_accounting_pass_end_to_end(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.delenv("ORCA_TERMINAL_HANDLE", raising=False)

    dead_handle = "term_d0000000-0000-0000-0000-000000000001"
    stall_handle = "term_e0000000-0000-0000-0000-000000000002"
    work_handle = "term_a0000000-0000-0000-0000-000000000003"
    open_handle = "term_b0000000-0000-0000-0000-000000000004"
    fresh_unclassified_handle = "term_c0000000-0000-0000-0000-000000000005"

    now_ms = time.time() * 1000
    worker_list = {
        "result": {
            "workers": [
                {"dispatchId": "ctx_dead0001", "dispatchStatus": "dispatched", "agentTerminalHandle": dead_handle},
                {"dispatchId": "ctx_stall002", "dispatchStatus": "dispatched", "agentTerminalHandle": stall_handle},
                {"dispatchId": "ctx_work0003", "dispatchStatus": "dispatched", "agentTerminalHandle": work_handle},
                {"dispatchId": "ctx_open0004", "dispatchStatus": "completed", "agentTerminalHandle": open_handle},
                {"dispatchId": "ctx_fresh0005", "dispatchStatus": "dispatched", "agentTerminalHandle": fresh_unclassified_handle},
            ],
            "page": {"hasMore": False},
        }
    }
    terminal_list = {
        "result": {
            "terminals": [
                {"handle": dead_handle, "lastOutputAt": now_ms},
                {"handle": stall_handle, "lastOutputAt": now_ms - 9_999_000},
                {"handle": work_handle, "lastOutputAt": now_ms - 1_000},
                {"handle": open_handle, "lastOutputAt": now_ms},
                {"handle": fresh_unclassified_handle, "lastOutputAt": now_ms - 1_000},
            ]
        }
    }
    worker_list_path = tmp_path / "worker_list.json"
    terminal_list_path = tmp_path / "terminal_list.json"
    worker_list_path.write_text(json.dumps(worker_list, indent=2), encoding="utf-8")
    terminal_list_path.write_text(json.dumps(terminal_list, indent=2), encoding="utf-8")

    orca = tmp_path / "orca"
    _write_executable(
        orca,
        f"""#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") cat "{worker_list_path}" ;;
  "terminal list")
    if printf '%s\\n' "$@" | grep -q -- '--json'; then
      cat "{terminal_list_path}"
    else
      awk -F'"' '/"handle"/{{print $4, "pane"}}' "{terminal_list_path}"
    fi
    ;;
  "terminal read")
    handle="$4"
    case "${{handle: -2}}" in
      01) echo "irrelevant, pid decides DEAD" ;;
      02) echo "❯ " ;;
      03) echo "esc to interrupt" ;;
      *) echo "" ;;
    esac
    ;;
  *) echo "{{}}" ;;
esac
""",
    )
    ps = tmp_path / "ps"
    _write_executable(
        ps,
        "#!/usr/bin/env bash\n[ \"$2\" = 4242 ] && exit 0 || exit 1\n",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({"job_id": "ctx_dead0001", "worker_pid": "9999", "pane": dead_handle}),
                json.dumps({"job_id": "ctx_stall002", "worker_pid": "4242", "pane": stall_handle}),
                json.dumps({"job_id": "ctx_work0003", "worker_pid": "4242", "pane": work_handle}),
                json.dumps({"job_id": "ctx_fresh0005", "worker_pid": "4242", "pane": fresh_unclassified_handle}),
            ]
        ),
        encoding="utf-8",
    )

    rows, dispatched_count = mod["_accounting_pass"]("run_x", ledger, stall_seconds=60)

    assert dispatched_count == 4
    by_dispatch = {r["dispatch_id"]: r for r in rows if r["dispatch_id"]}
    assert by_dispatch["ctx_dead0001"]["verdict"] == "DEAD"
    assert by_dispatch["ctx_stall002"]["verdict"] == "STALL"
    assert by_dispatch["ctx_work0003"]["verdict"] == "working"
    assert by_dispatch["ctx_fresh0005"]["verdict"] == "working"

    open_rows = [r for r in rows if r["verdict"] == "OPEN_PANE"]
    assert len(open_rows) == 1
    assert open_rows[0]["pane"] == open_handle

    # Failability: shrinking the stall window to 0 turns the fresh-but-
    # unclassifiable pane's verdict from working to UNKNOWN, which would not
    # happen if age_seconds were computed wrong (e.g. never set, or ignored).
    # ctx_work0003 stays "working" regardless because its sweep class is
    # independently "working" — proving the two code paths are distinct.
    tight_rows, _ = mod["_accounting_pass"]("run_x", ledger, stall_seconds=0)
    by_dispatch_tight = {r["dispatch_id"]: r for r in tight_rows if r["dispatch_id"]}
    assert by_dispatch_tight["ctx_fresh0005"]["verdict"] == "UNKNOWN"
    assert by_dispatch_tight["ctx_work0003"]["verdict"] == "working"
