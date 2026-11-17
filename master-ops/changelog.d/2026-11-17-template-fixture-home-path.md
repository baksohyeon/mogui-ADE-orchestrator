- Neutral home paths in two template fixtures and a root-cause fix for the codex
  git-index test on other hosts (#333). `test-tracker-check-banner.sh` no longer
  bakes the `OPS_REPO` template value into its mock `bd` fixtures; it reads the
  same basename `tracker-check.sh` itself computes, so neither the unrendered
  `{{OPS_REPO}}` token nor, once a peer's install renders it, their real
  home-containing path ends up committed inside the fixture's own source.
  `test-dispatch-codex-git-index.sh`'s `check_git_escalation_cli` assumed the
  sibling `dispatch` script still carried its raw `OPS_REPO`/`RUNTIME_ROOT`
  template tokens so its own sandbox substitution to a temp dir would apply;
  on an installed host where `dispatch` is already rendered with real absolute
  paths, that substitution was a silent no-op, `dispatch-gate`'s test mock
  became unreachable, and the CLI call failed instead of writing the ledger
  line the test expected; reproduced locally by rendering a copy of
  `dispatch` the way an install would and reading the resulting
  `git_escalation CLI validation did not cover accepted operations and
  refusals` failure. The test now reads whatever value `dispatch`'s own
  `OPS=`/`GATE=` lines currently hold (token or rendered path) before building
  its sandbox, and fails with a named reason instead of silently passing if it
  can't.

  A follow-up master review on the same PR (#341 round 2) found three more
  gaps. `check_git_escalation_cli` now substitutes the longer of
  `OPS_REPO`/`RUNTIME_ROOT` first, since one value being a path prefix of the
  other (for example `RUNTIME_ROOT=/a`, `OPS_REPO=/a/ops`) previously left
  `OPS` resolved as `$work/ops` instead of `$work`; a new test case renders a
  copy of `dispatch` with exactly that shape and the function now also reads
  the rendered `OPS=`/`GATE=` lines back to confirm they resolve to the
  sandbox root. It also fails by name when the render still contains the
  original `OPS_REPO`/`RUNTIME_ROOT` value or came out byte-identical to the
  source, and the empty-value guard names which of the two was unreadable.
  `test-tracker-check-banner.sh`'s repeated `$TMP/pass-root/$OPS_BASENAME`
  path is now one variable.
