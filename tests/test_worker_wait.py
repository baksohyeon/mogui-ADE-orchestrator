"""Regression coverage for master-ops/scripts/worker-wait.

worker-wait is self-contained (master-ops/ is template-applied into repos with
no src/ tree), so it is loaded via runpy exactly like tests/test_dispatch_gate.py
loads scripts/dispatch-gate, rather than imported as a package.
"""

from __future__ import annotations

import contextlib
import json
import os
import runpy
import signal
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


def test_pid_alive_but_age_unmeasured_is_unknown_not_stall() -> None:
    """STALL means measured-stale, not "the sweep said something other than
    working while we happened to have no age." An unreadable lastOutputAt
    (pane not found in terminal list) must not be silently read as stale."""

    mod = _load()
    verdict = mod["_compute_verdict"](
        pid="123", pid_alive=True, age_seconds=None, stall_seconds=600, sweep_class="idle"
    )
    assert verdict == "UNKNOWN"
    # Failability: the same sweep class with a measured, stale age IS STALL —
    # proving age_seconds, not just the sweep class, gates this verdict.
    assert (
        mod["_compute_verdict"](
            pid="123", pid_alive=True, age_seconds=9999.0, stall_seconds=600, sweep_class="idle"
        )
        == "STALL"
    )


def test_pid_liveness_could_not_be_measured_is_unknown_not_dead() -> None:
    """`pid_alive=None` means the measurement itself failed (bad pid data, `ps`
    missing or erroring) — not evidence the process is gone. Only a positive
    `ps` answer (`pid_alive=False`) may report DEAD, which the runbook tells
    the coordinator to act on with worker-abandon."""

    mod = _load()
    verdict = mod["_compute_verdict"](
        pid="123", pid_alive=None, age_seconds=1.0, stall_seconds=600, sweep_class="working"
    )
    assert verdict == "UNKNOWN"
    # Failability: the same inputs with liveness actually measured false IS DEAD.
    assert (
        mod["_compute_verdict"](
            pid="123", pid_alive=False, age_seconds=1.0, stall_seconds=600, sweep_class="working"
        )
        == "DEAD"
    )


def test_pid_alive_returns_none_for_unparseable_pid() -> None:
    mod = _load()
    assert mod["_pid_alive"]("not-a-number") is None
    # Failability: an empty pid must be unmeasurable just like a non-numeric one.
    assert mod["_pid_alive"]("") is None


@skip_windows_exec_surface
def test_pid_alive_returns_true_for_a_real_pid(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    ps = tmp_path / "ps"
    _write_executable(ps, "#!/usr/bin/env bash\n[ \"$2\" = 4242 ] && exit 0 || exit 1\n")
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    assert mod["_pid_alive"]("4242") is True
    # Failability: an unparseable pid must never reach `ps` and read alive.
    assert mod["_pid_alive"]("not-a-number") is None


@skip_windows_exec_surface
def test_pid_alive_returns_none_when_ps_cannot_run(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir: no `ps` on PATH at all
    assert mod["_pid_alive"]("123") is None


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
    """`_wait_for_message` makes exactly one `check` attempt per call — it never
    loops internally on a heartbeat, or `_accounting_pass` could be starved
    for as long as heartbeats keep arriving. The caller (`_run_loop`) is what
    re-arms by calling this again, once per pass, with the chained ack."""

    mod = _load()
    fake_orca_dir = tmp_path
    _write_fake_orca_for_check(fake_orca_dir)
    monkeypatch.setenv("PATH", f"{fake_orca_dir}:{os.environ['PATH']}")

    batch1, ack1 = mod["_wait_for_message"]("run_x", None)
    assert batch1 is None
    assert ack1 == "d1"

    batch2, ack2 = mod["_wait_for_message"]("run_x", ack1)
    assert batch2 is not None
    assert batch2["messages"][0]["type"] == "worker_done"
    assert batch2["deliveryId"] == "d2"
    # Failability: a version that still looped internally on the heartbeat
    # would return the worker_done batch from the FIRST call, making batch1
    # non-None above.


@skip_windows_exec_surface
def test_check_wait_ok_false_envelope_is_reported_as_failure_not_a_wake(
    tmp_path: Path, monkeypatch
) -> None:
    """A parseable `{"ok": false, ...}` response from `orca check --wait` must
    be treated as a check failure — never as a real delivery, even when the
    failed envelope happens to carry a populated `result` body (a retried or
    stale response, a proxy error page with an echoed-back payload)."""

    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        """#!/usr/bin/env bash
if [ "$1 $2" = "orchestration check" ]; then
  printf '{"ok": false, "error": "auth expired", "result": {"deliveryId": "evil", "messages": [{"type": "worker_done"}]}}'
else
  echo "{}"
fi
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    batch, ack = mod["_wait_for_message"]("run_x", None)

    assert batch is None
    assert ack is None
    # Failability: the pre-fix behavior ignored the top-level `ok` field
    # entirely and returned the embedded `result` as a real, non-None batch
    # (`deliveryId` "evil", a worker_done message) — a wake manufactured from
    # a call that never actually succeeded.


@skip_windows_exec_surface
def test_empty_result_with_no_messages_and_no_delivery_id_is_a_quiet_pass(
    tmp_path: Path, monkeypatch
) -> None:
    """A successful check call whose `result` has no messages and no
    `deliveryId` — timedOut or not — must never read as a wake."""

    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        """#!/usr/bin/env bash
if [ "$1 $2" = "orchestration check" ]; then
  printf '{"result": {}}'
else
  echo "{}"
fi
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    batch, ack = mod["_wait_for_message"]("run_x", None)

    assert batch is None
    assert ack is None
    # Failability: the pre-fix behavior returned `({}, None)` — a non-None
    # batch — for this exact envelope, since it lacks `timedOut` too.


@skip_windows_exec_surface
def test_heartbeat_without_delivery_id_is_quiet_and_keeps_the_prior_ack(
    tmp_path: Path, monkeypatch
) -> None:
    """A heartbeat batch with a missing/falsy `deliveryId` cannot be acked —
    there is nothing to send. It must not zero out an already-valid ack
    either, which would silence `--ack` on every future call and let orca
    replay the same heartbeat forever instead of blocking."""

    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        """#!/usr/bin/env bash
if [ "$1 $2" = "orchestration check" ]; then
  printf '{"result": {"messages": [{"type": "heartbeat"}]}}'
else
  echo "{}"
fi
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    batch, ack = mod["_wait_for_message"]("run_x", "already-acked")

    assert batch is None
    assert ack == "already-acked"
    # Failability: the pre-fix behavior returned `(None, None)` here (the
    # falsy `deliveryId` itself), discarding a still-valid prior ack.


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
    # Not acked *by this call*: no --ack flag was ever sent for this delivery,
    # which the fake orca itself would have refused with exit 3 above had it
    # seen one. The returned ack is this batch's own deliveryId — correct to
    # return (a caller that chains it forward acks the batch it just saw, not
    # a stale one) but this caller does not chain it forward at all; it wakes
    # instead, leaving the batch itself unacknowledged for the coordinator.
    assert ack == "d9"


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
        "ok": True,
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
        "ok": True,
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


# --- worker-list failure must never read as an empty, settled Run ----------


@skip_windows_exec_surface
def test_worker_list_failure_raises_instead_of_reporting_empty(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(orca, "#!/usr/bin/env bash\nexit 1\n")
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with pytest.raises(mod["WorkerListError"]):
        mod["_worker_list"]("run_x")


@skip_windows_exec_surface
def test_orca_json_rejects_a_well_formed_but_failed_envelope(tmp_path: Path, monkeypatch) -> None:
    """Exit 0 with parseable JSON is not success unless the envelope's own
    `"ok"` field says so — an `{"ok": false, ...}` error response must not be
    read as a valid (if empty) worker-list result."""

    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        """#!/usr/bin/env bash
echo '{"ok": false, "error": "auth expired"}'
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    assert mod["_orca_json"](["orca", "orchestration", "worker-list"]) is None
    with pytest.raises(mod["WorkerListError"]):
        mod["_worker_list"]("run_x")


@skip_windows_exec_surface
def test_once_mode_reports_failure_instead_of_false_success(tmp_path: Path, monkeypatch) -> None:
    mod = _load()
    orca = tmp_path / "orca"
    _write_executable(orca, "#!/usr/bin/env bash\nexit 1\n")
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")

    rc = mod["main"](["--once", "--run", "run_x", "--ledger", str(ledger)])
    assert rc == 2
    # Failability: the pre-fix behavior returned 0 here (empty list == success).


# --- _run_loop: return on wake, never re-enter with a stale ack -------------

LOOP_TEST_WALL_CLOCK_GUARD_SECONDS = 5


@contextlib.contextmanager
def _wall_clock_guard(seconds: float = LOOP_TEST_WALL_CLOCK_GUARD_SECONDS):
    """A regression that makes `_run_loop` re-enter `check --wait` forever
    hangs the whole suite instead of failing this one test — the fake
    `orca` above answers a second call with `exit 3`, which only fails the
    test if something actually reads that exit code; an infinite loop never
    gets that far. POSIX-only (`SIGALRM`); every caller is already marked
    `@skip_windows_exec_surface`.
    """

    def _on_alarm(signum, frame):
        raise TimeoutError(f"test exceeded its {seconds}s wall-clock guard — main() never returned")

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@skip_windows_exec_surface
def test_run_loop_returns_immediately_after_a_real_delivery(tmp_path: Path, monkeypatch) -> None:
    """The historical bug: after printing a real (non-heartbeat) delivery, the
    loop re-entered `check --wait` with the same already-seen ack, which would
    just replay the same unacknowledged batch forever instead of returning
    control to the coordinator who is supposed to act and ack it."""

    mod = _load()
    monkeypatch.delenv("ORCA_TERMINAL_HANDLE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    handle = "term_a0000000-0000-0000-0000-000000000009"
    worker_list_path = tmp_path / "worker_list.json"
    worker_list_path.write_text(
        json.dumps(
            {
                "ok": True,
                "result": {
                    "workers": [
                        {
                            "dispatchId": "ctx_x",
                            "dispatchStatus": "dispatched",
                            "agentTerminalHandle": handle,
                        }
                    ],
                    "page": {"hasMore": False},
                },
            }
        ),
        encoding="utf-8",
    )
    terminal_list_path = tmp_path / "terminal_list.json"
    terminal_list_path.write_text(
        json.dumps(
            {"ok": True, "result": {"terminals": [{"handle": handle, "lastOutputAt": time.time() * 1000}]}}
        ),
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"job_id": "ctx_x", "worker_pid": "4242", "pane": handle}),
        encoding="utf-8",
    )

    calls = tmp_path / "check_calls"
    calls.write_text("0", encoding="utf-8")
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        f"""#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") cat "{worker_list_path}" ;;
  "terminal list")
    if printf '%s\\n' "$@" | grep -q -- '--json'; then cat "{terminal_list_path}"
    else echo "{handle} pane"; fi
    ;;
  "terminal read") echo "esc to interrupt" ;;
  "orchestration check")
    n=$(cat "{calls}"); n=$((n + 1)); echo "$n" > "{calls}"
    if [ "$n" -gt 1 ]; then
      echo "FAIL: check --wait was called again after a real delivery" >&2
      exit 3
    fi
    printf '{{"result": {{"deliveryId": "d1", "messages": [{{"type": "worker_done"}}]}}}}'
    ;;
  *) echo "{{}}" ;;
esac
""",
    )
    ps = tmp_path / "ps"
    _write_executable(ps, "#!/usr/bin/env bash\n[ \"$2\" = 4242 ] && exit 0 || exit 1\n")
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with _wall_clock_guard():
        rc = mod["main"](["--run", "run_x", "--ledger", str(ledger)])

    assert rc == 0
    assert calls.read_text().strip() == "1"


@skip_windows_exec_surface
def test_run_loop_exits_without_waiting_when_already_settled(tmp_path: Path, monkeypatch) -> None:
    """An already-settled Run must not incur a full `check --wait` timeout
    before the first accounting pass even runs."""

    mod = _load()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    calls = tmp_path / "check_calls"
    calls.write_text("0", encoding="utf-8")
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        f"""#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") echo '{{"ok": true, "result": {{"workers": [], "page": {{"hasMore": false}}}}}}' ;;
  "terminal list")
    if printf '%s\\n' "$@" | grep -q -- '--json'; then echo '{{"ok": true, "result": {{"terminals": []}}}}'; fi ;;
  "orchestration check")
    n=$(cat "{calls}"); n=$((n + 1)); echo "$n" > "{calls}"
    echo "FAIL: check --wait must not run when nothing is dispatched" >&2
    exit 3
    ;;
  *) echo "{{}}" ;;
esac
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with _wall_clock_guard():
        rc = mod["main"](["--run", "run_empty", "--ledger", str(tmp_path / "ledger.jsonl")])

    assert rc == 0
    assert calls.read_text().strip() == "0"


@skip_windows_exec_surface
def test_run_loop_flushes_a_heartbeats_ack_when_the_next_pass_wakes(
    tmp_path: Path, monkeypatch
) -> None:
    """The heartbeat's own ack is only ever chained forward into the *next*
    `_wait_for_message` call. When the pass right after a heartbeat is the
    one that returns control — here, the dispatch's pid dies between the
    pre-wait accounting pass and the post-heartbeat one, producing an
    actionable DEAD verdict — there is no next call left to carry that ack,
    so `_run_loop` must flush it directly instead of dropping it."""

    mod = _load()
    monkeypatch.delenv("ORCA_TERMINAL_HANDLE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    handle = "term_a0000000-0000-0000-0000-00000000000a"
    worker_list_path = tmp_path / "worker_list.json"
    worker_list_path.write_text(
        json.dumps(
            {
                "ok": True,
                "result": {
                    "workers": [
                        {
                            "dispatchId": "ctx_x",
                            "dispatchStatus": "dispatched",
                            "agentTerminalHandle": handle,
                        }
                    ],
                    "page": {"hasMore": False},
                },
            }
        ),
        encoding="utf-8",
    )
    terminal_list_path = tmp_path / "terminal_list.json"
    terminal_list_path.write_text(
        json.dumps(
            {"ok": True, "result": {"terminals": [{"handle": handle, "lastOutputAt": time.time() * 1000}]}}
        ),
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"job_id": "ctx_x", "worker_pid": "4242", "pane": handle}),
        encoding="utf-8",
    )

    ps_calls = tmp_path / "ps_calls"
    ps_calls.write_text("0", encoding="utf-8")
    ps = tmp_path / "ps"
    _write_executable(
        ps,
        f"""#!/usr/bin/env bash
n=$(cat "{ps_calls}"); n=$((n + 1)); echo "$n" > "{ps_calls}"
[ "$n" = "1" ] && exit 0 || exit 1
""",
    )

    check_calls = tmp_path / "check_calls"
    check_calls.write_text("0", encoding="utf-8")
    ack_flush_seen = tmp_path / "ack_flush_seen"
    orca = tmp_path / "orca"
    _write_executable(
        orca,
        f"""#!/usr/bin/env bash
case "$1 $2" in
  "orchestration worker-list") cat "{worker_list_path}" ;;
  "terminal list")
    if printf '%s\\n' "$@" | grep -q -- '--json'; then cat "{terminal_list_path}"
    else echo "{handle} pane"; fi
    ;;
  "terminal read") echo "esc to interrupt" ;;
  "orchestration check")
    for a in "$@"; do [ "$a" = "d1" ] && echo yes > "{ack_flush_seen}"; done
    n=$(cat "{check_calls}"); n=$((n + 1)); echo "$n" > "{check_calls}"
    if [ "$n" = "1" ]; then
      printf '{{"result": {{"deliveryId": "d1", "messages": [{{"type": "heartbeat"}}]}}}}'
    else
      printf '{{"result": {{"timedOut": true}}}}'
    fi
    ;;
  *) echo "{{}}" ;;
esac
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with _wall_clock_guard():
        rc = mod["main"](["--run", "run_x", "--ledger", str(ledger)])

    assert rc == 0
    assert ack_flush_seen.exists()
    # Failability: a version that only chains a heartbeat's ack into a next
    # `_wait_for_message` call — which never happens here, since this exact
    # pass is the one that wakes on the newly-DEAD row — would leave "d1"
    # unacked and this file would never be written.
