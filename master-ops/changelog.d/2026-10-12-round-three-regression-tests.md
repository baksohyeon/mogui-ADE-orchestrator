Lands the seven round-three rows from `docs/reports/test-gaps-2026-10-07.md`. Row 6 adds a
`tests/test_dispatch_gate.py` case pinning that `--ledger` given after the subcommand already exits 2
on argparse's own unrecognized-arguments refusal and writes no file in the cwd. Row 7 fixes a live
`IndexError` in `dispatch_gate.py`'s `_registration_candidate`: registering once without
`--contract-sha` leaves that ticket's file on disk, and registering again with its contract sha hit an
unguarded `matching_pending` lookup; the guard now matches its two sibling branches. Row 9 adds a
`tests/test_changelog_release.py` case pinning that a fragment added after a release's own fold still
carries over whole into the next fold. Row 8 adds `scripts/test-contributing-shell-loop.sh`, extracting
`CONTRIBUTING.md`'s documented shell-test loop at runtime and replaying it against a failing and a
passing fixture script. Row 10 fixes `scripts/worker-pane-sweep` to classify from the lines at and
after a pane's last prompt line, so an approval marker left in scrollback above a now-idle prompt no
longer reports a false `ACTION approval`. Row 11 hardens `scripts/test-product-path-guard.sh`'s
`sed-dash-n-print-range-passes` case against the guard's unsafe-command check reading a bare `w`, `W`,
or `e` in the scratch temp path's random name. Row 12 makes `scripts/test-bash-output-size-warn.sh`
resolve the real `python3` before swapping `$HOME`, so a mise-managed shim no longer installs a Python
mid-test and leaks its banner into the captured output.
