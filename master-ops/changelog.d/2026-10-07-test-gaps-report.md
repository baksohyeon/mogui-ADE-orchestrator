Adds `docs/reports/test-gaps-2026-10-07.md`: maps the twelve behaviours that broke in the last two weeks
to what pins each one now, classifying each row (`covered`, `pytest`, `shell-inline`, `out-of-harness`,
`fix-flaky`) and placing the gaps under `CONTRIBUTING.md`'s "Adding a test" rules for round three. Finds
two live bugs (`dispatch-gate register`'s `IndexError` on a stale ticket, `worker-pane-sweep`'s false
`approval` verdict from a resolved dialog's scrollback) and one live flake (`test-bash-output-size-warn.sh`
under a scratch `HOME`) still unguarded by any existing case.
