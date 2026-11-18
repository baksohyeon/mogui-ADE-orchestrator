- `scripts/harness-selfcheck.sh` grades its own warning lines (#336 item 2: a
  boot card that only checks for non-zero used to read a warning as a pass).
  The three `Infra:` lines (`ctx`, `ctx-upgrade`, `code-review-graph`) and the
  `Seat: NOTICE` line are the only lines in this script that could already
  print without changing the exit code; each is now tagged `BLOCK:` or
  `INFO:`. `BLOCK:` covers every `ctx`/`code-review-graph` gap (an
  unmeasurable probe, an empty result such as no repository registered, a
  registration gap, or a stale graph) and every `ctx-upgrade` gap except one:
  the installed version being numerically behind the latest one `ctx`'s own
  checker last recorded is `INFO:`, since `ctx` still runs correctly on it.
  The `Seat: NOTICE` line (workspace id rotated across a succession, same
  seat) is `INFO:` too -- the seat already proved sole and correct, only the
  role-state record is stale.

  The `INFO:` grade for `ctx-upgrade` additionally requires the probe to have
  actually returned 0: a failed, non-timeout probe's own raw output could in
  principle contain the substring "is behind" for an unrelated reason, and
  text content alone must never grant a pass to a probe that never measured
  anything.

  A new exit code, 3, fires when no hard gap occurred but at least one line
  was tagged `BLOCK:`; it is distinct from 1 (a hard gap: Orca, skill, hook,
  tracker, seat, card/twins, template) and from the existing 0 and 2. A new
  summary line, `Self-check summary: N blocking warning(s), M informational
  warning(s)`, prints just before the exit. `docs/runbooks/succession-boot-
  card.md` gains the self-check step this repository's boot sequence never
  previously named, with a table of what to do for each exit code.

  The #336 report names a breakdown (33 skill-selection, 4 settings-drift, 28
  missing-instruction-path, 1 root-`AGENTS.md`-drift warning lines) and
  states a total of 41, which the four component counts do not sum to (they
  add to 66); neither figure maps onto this script or this template either
  way: it has no "settings drift" or "missing instruction path" checks at
  all, and only 8 skill directories exist here, so 33 skill warnings cannot
  come from this codebase. That breakdown is from the reporting peer's own,
  more heavily customized installation, outside this contract's `writes`
  scope; items 1, 3, and 4 of #336 stay open and untouched.

  New test: `scripts/test-harness-selfcheck-grading.sh`, which (unlike
  `test-harness-selfcheck-infra.sh`'s isolated-block extraction) renders the
  real script into a minimal fixture `OPS_DIR`/`WORKSPACE_ROOT` and runs it
  end to end, because the grading's effect on the exit code is computed
  after every other check has already run; covers a blocking `code-review-
  graph` and a blocking `ctx` case, an informational `ctx-upgrade` case, an
  empty-probe-result case, the failed-probe-text-collision case above, and
  the informational seat notice staying at exit 0. `test-seat-check.sh`
  gains one assertion that the rotated-id notice carries `INFO:`.
