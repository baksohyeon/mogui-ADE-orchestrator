- Fixed: five `pytest` cases that only failed inside an Orca worktree. `bootstrap()`'s dual-instance
  check seats on `os.getcwd()` when no `seat_root` is given, so a real `claude` process parked at the
  same cwd — routine when a worktree holds more than one agent — reported a false `SEAT_PEER`. The
  `master-bootstrap`/`master-recover` CLIs have no way to pass `seat_root`, so an optional
  `MOGUI_SEAT_ROOT` env var override (same name `mogui_log.py` already reads for the same question)
  lets a caller opt the live cwd out without changing the unset-var default. A `MOGUI_SEAT_ROOT` that
  does not resolve to an existing directory raises `BootstrapError`.
