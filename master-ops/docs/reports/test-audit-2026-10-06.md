# Test audit, round two: dispatch's shell and Python regression suites

Scope: `scripts/test-dispatch-runtime.sh`, `scripts/test-dispatch-timeline.sh`,
`scripts/test-worker-wait.sh`, `tests/test_dispatch_gate.py`. No deletion in this PR; this
report is discovery and evidence only.

## Method

- Counts verified 2026-10-06: every count below was checked against both its table and a foreground
  run of the file it describes.
- `test-dispatch-runtime.sh` already pairs almost every positive assertion with its own inline mutant
  (a shell or Python source edit run in a subshell, printing an `ok : failability: ...` line). Re-deriving
  round one's result meant running the file itself in the foreground and reading its own mutant evidence,
  not writing new mutants.
- `test_dispatch_gate.py` (116 cases) was audited by the contract's lighter method for this round: one
  full `pytest` pass, cases grouped by the source function each one calls, and for every function with
  more than three cases, the two cases whose assertions look identical got one shared mutant. **This file's
  audit is assertion-based, not exhaustive mutation**: most of the 116 cases carry no mutant of their own.
- `test-dispatch-timeline.sh` and `test-worker-wait.sh` were read in full; a mutant was added only where a
  case's assertion looked, on inspection, like it might pass regardless of the behavior it claims to pin.
  Neither file needed one: both already carry inline mutants for every case non-trivial enough to want one.

## scripts/test-dispatch-runtime.sh

Full run: `timeout 120 bash scripts/test-dispatch-runtime.sh`: exit 0, 68 `ok` lines plus the
top-of-file agy regression line, for 72 cases (4 top-level checks + 68 feature assertions; 30 of the
68 are the dedicated `failability` mutant lines and the remaining 38 are the fixture assertions those
mutants protect, noted below).

Round one reported 35 cases (34 keep, 1 duplicate, 0 cannot-fail, 0 low-value) for this file. No round-one
artifact survived the termination at 600 s to check the duplicate against, so this round re-derives the
count from the file as it stands now. The file grew by 211 lines between round one and this round (PR
#160, merged as `eb7e326`, added `claude_pretrust_test`, `claude_pretrust_call_site_test`, and
`claude_hook_trust_marker_test`, accounting for 7 of the 68 `ok` lines). The remaining gap between round one's 35 and
this round's 72 could not be reconciled without round one's own case list; this round's count is the
measured one.

### Top of file: agy capability regression (4 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `agy:gemini` pattern present | dispatch still carries the agy-to-gemini runtime alias | keep | `grep -Fq` exits 1 and aborts the file if absent; exercised every run |
| `if runtime == 'agy': runtime = 'gemini'` pattern present | the Python-side alias line is intact | keep | same mechanism |
| `agy) echo "agy --model ..."` pattern present | the shell-side launch-command case for agy is intact | keep | same mechanism |
| `probe_args_expansion_guard_test` | `MODEL_PROBE_ARGS` expansion stays `set -u` safe when the array is empty, on bash 3.2 | keep | runs the guarded expansion under `bash -uc 'set -u; ...'`; a regression to unguarded `"${arr[@]}"` throws under `set -u` and the test aborts the file |

### `cursor_multivendor_test` (2 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| cursor accepts a model present in its own `models` list | multi-vendor host check uses the host's own model list, not a vendor prefix | keep | `ok : cursor accepts a model present in cursor-agent models output` |
| failability: dropping cursor from `MULTI_VENDOR_HOSTS` | the acceptance above is not a tautology | keep | `ok : failability: dropping cursor from MULTI_VENDOR_HOSTS makes this case fail` |

### `checkonly_ledger_test` (2 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `--check-only` leaves the real ledger's line count unchanged | check-only dispatch passes `--no-record` to dispatch-gate | keep | `ok : --check-only leaves the real ledger's line count unchanged` |
| failability: dropping `--no-record` | the unchanged-count assertion is not a tautology | keep | `ok : failability: dropping --no-record under --check-only would consume the fanout cap` |

### `contract_delivery_test` (2 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `--contract` delivers the file with an ack token and updates `$SPEC` | contract delivery writes the ack-token section and rewrites the spec in place | keep | `ok : --contract delivers the file with an acknowledgement token and updates the spec` |
| failability: dropping the token-append line | the ack-token assertion is not a tautology | keep | `ok : failability: dropping the token-append line leaves the delivered file without ack-<token>` |

### `cursor_pretrust_test` (3 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| succeeds against a trusted summary | `ensure_cursor_pretrust` passes when the pre-trust binary reports a trusted summary | keep | `ok : ensure_cursor_pretrust succeeds against a fake cursor-worker-pretrust reporting a trusted summary` |
| fails closed on a skipped summary | a skipped pre-trust run blocks the launch instead of proceeding | keep | `ok : ensure_cursor_pretrust fails closed on a skipped pre-trust summary` |
| failability: the `*skipped*)` case stops matching | the fail-closed assertion above is not a tautology | keep | `ok : failability: dropping the *skipped*) case makes the fail-closed assertion above fail` |

### `claude_pretrust_test` (3 cases, new in PR #160)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| succeeds against a trusted summary | `ensure_claude_pretrust` passes when the pre-trust binary reports a trusted summary | keep | `ok : ensure_claude_pretrust succeeds against a fake claude-worker-pretrust reporting a trusted summary` |
| fails closed on no `Summary` line | an unmeasured or broken pre-trust binary blocks the launch | keep | `ok : ensure_claude_pretrust fails closed on a missing pre-trust summary` |
| failability: the empty-summary case stops matching | the fail-closed assertion above is not a tautology | keep | `ok : failability: dropping the empty-summary case makes the fail-closed assertion above fail` |

### `claude_pretrust_call_site_test` (2 cases, new in PR #160)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| dispatch calls `ensure_claude_pretrust` before `orca terminal create` | the wiring, not just the function, calls pre-trust before launch | keep | `ok : dispatch calls ensure_claude_pretrust before orca terminal create` |
| failability: dropping the call | the ordering assertion is not a tautology | keep | `ok : failability: dropping the ensure_claude_pretrust call makes the ordering check fail` |

### `claude_hook_trust_marker_test` (2 cases, new in PR #160)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| claude's folder-trust dialog classifies as hook-trust | the "Quick safety check" pane is recognized and stops the dispatch before a false success | keep | `ok : a pane carrying claude's folder-trust dialog classifies as hook-trust` |
| failability: dropping the claude marker | the classification assertion is not a tautology | keep | `ok : failability: dropping the claude folder-trust marker misclassifies the dialog pane (got 'unknown')` |

### `codex_launch_flags_test` (2 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| codex launch carries `--model`, reasoning effort, update-check off, migration ack | the exact launch string codex needs is produced | keep | `ok : codex launch carries --model, reasoning effort, update-check off, and the migration ack * rc=0` |
| failability: dropping `check_for_update_on_startup=false` | the exact-string assertion is not a tautology | keep | `ok : failability: dropping check_for_update_on_startup=false breaks the exact-string match (mutant rc=0)` |

### `codex_start_screen_test` (11 cases: 6 fixture cases + 5 failability)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `ready` pane returns rc 0 | a genuinely ready pane is never flagged as a start-screen problem | keep | `ok : case ready * rc=0`; covered transitively: every failability mutant below targets the *other* branches, so a regression that started flagging `ready` would need its own case, which this one is |
| `footer-mismatch` returns rc 1 | a footer naming a different model/effort than requested is caught | keep | `ok : case footer-mismatch * rc=1`; own failability mutant below |
| `update` returns rc 1 | an update-available notice is caught | keep | `ok : case update * rc=1`; own failability mutant below |
| `limit` returns rc 1 | a provider-limit notice is caught | keep | `ok : case limit * rc=1`; own failability mutant below |
| `menu` returns rc 1 | the model-retirement migration menu is caught | keep | `ok : case menu * rc=1`; own failability mutant below |
| `no-footer` returns rc 2 | an empty pane (no footer yet) is reported distinctly from a real problem | keep | `ok : case no-footer * rc=2`; own failability mutant below |
| failability: limit-marker | `limit` is not caught by accident | keep | `ok : failability: limit-marker mutant changes rc 1 -> 0` |
| failability: update-phrase | `update` is not caught by accident | keep | `ok : failability: update-phrase mutant changes rc 1 -> 2` |
| failability: menu-pattern | `menu` is not caught by accident | keep | `ok : failability: menu-pattern mutant changes rc 1 -> 2` |
| failability: no-footer-yet | `no-footer` is not caught by accident | keep | `ok : failability: no-footer-yet mutant changes rc 2 -> 1` |
| failability: footer-mismatch-compare | `footer-mismatch` is not caught by accident | keep | `ok : failability: footer-mismatch-compare mutant changes rc 1 -> 0` |

### `codex_start_screen_wiring_test` (3 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| a migration-menu pane never reaches `--inject` | the wiring, not just the classifier, blocks on a bad start screen | keep | `ok : a migration-menu codex pane never reaches orca orchestration dispatch --inject` |
| a ready pane reaches `--inject` | the wiring does not over-block | keep | `ok : a ready codex pane reaches orca orchestration dispatch --inject` |
| failability: disabling the gate conditional | the two assertions above are not tautologies | keep | `ok : failability: disabling the gate conditional injects on a migration-menu pane (status=0, injected=yes)` |

### `codex_hooks_vet_test` (20 cases: 11 fixture cases + 9 failability)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `all-local` rc 0 | an all-local-command hooks.json passes | keep | `ok : case all-local * rc=0`; positive path, not separately mutated |
| `builtin-first-word` rc 0 | a shell-builtin first word (e.g. `cd`) passes without a PATH lookup | keep | `ok : case builtin-first-word * rc=0`; positive path, not separately mutated |
| `bad-abs-path` rc 1 | a missing absolute-path command is caught | keep | `ok : case bad-abs-path * rc=1`; failability: `abs-path-check` |
| `bad-path-word` rc 1 | a first word absent from PATH is caught | keep | `ok : case bad-path-word * rc=1`; failability: `path-word-check` |
| `bad-event-shape` rc 1 | a malformed per-event entry shape is caught | keep | `ok : case bad-event-shape * rc=1`; failability: `entries-shape-check` |
| `top-level-empty-dict` rc 1 | a `{}` document is caught with a controlled message | keep | `ok : case top-level-empty-dict * rc=1`; failability: `top-level-noop` |
| `top-level-json-list` rc 1 | a `[]` document is caught with a controlled message | keep | `ok : case top-level-json-list * rc=1`; failability: `top-level-noop` |
| `missing-hooks-json` rc 2 | a home with no hooks.json at all is reported distinctly (not found vs. rejected) | keep | `ok : case missing-hooks-json * rc=2`; failability: `missing-file-check` |
| `orca-managed-hook-shape` rc 0 | Orca's own quoted-path-then-`;` command tokenizes correctly | keep | `ok : case orca-managed-hook-shape * rc=0`; failability: `tokenizer-regression` |
| `comment-hash-not-dropped` rc 1 | a `#` inside a command is not treated as a shell comment that hides the rest | keep | `ok : case comment-hash-not-dropped * rc=1`; failability: `comment-hash-check` |
| `redirect-target-not-checked` rc 0 | a redirect target that does not yet exist is not treated as a missing command | keep | `ok : case redirect-target-not-checked * rc=0`; failability: `redirect-target-check` |
| failability: abs-path-check | `bad-abs-path` is not caught by accident | keep | `ok : failability: abs-path-check mutant changes rc 1 -> 0` |
| failability: path-word-check | `bad-path-word` is not caught by accident | keep | `ok : failability: path-word-check mutant changes rc 1 -> 0` |
| failability: missing-file-check | `missing-hooks-json` is not caught by accident | keep | `ok : failability: missing-file-check mutant changes rc 2 -> 0` |
| failability: entries-shape-check | `bad-event-shape` is not caught by accident | keep | `ok : failability: entries-shape-check mutant changes rc 1 -> 0` |
| failability: early-stop | the vet keeps checking commands after the first one in an event, not just the first | keep | `ok : failability: early-stop mutant changes rc 1 -> 0` |
| failability: tokenizer-regression | `orca-managed-hook-shape` is not caught by accident; reverting the shlex tokenizer fix re-fuses the quoted-path-plus-`;` token | keep | `ok : failability: tokenizer-regression mutant (shlex.split restored) rc 0 -> 1, naming the fused-semicolon token` |
| failability: comment-hash-check | `comment-hash-not-dropped` is not caught by accident | keep | `ok : failability: comment-hash-check mutant changes rc 1 -> 0` |
| failability: redirect-target-check | `redirect-target-not-checked` is not caught by accident | keep | `ok : failability: redirect-target-check mutant changes rc 0 -> 1` |
| failability: top-level-noop | disabling the top-level shape guard still exits 1 on both `{}` and `[]` (an uncaught exception also exits 1), but drops the controlled message. The mutant is caught on the message, not the exit code, and the function-header comment says so | keep | `ok : failability: top-level-noop mutant drops to an uncaught exception on both fixtures (rc stays 1/1, controlled message gone)` |

### `hooks_answer_bin_path_test` (3 cases)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| `HOOKS_ANSWER_BIN` resolves to `codex-hooks-review-answer` under the real `SCRIPTS_DIR` | the answer tool is found beside the wrapper, by name | keep | `ok : HOOKS_ANSWER_BIN resolves to an existing executable (codex-hooks-review-answer) under the real SCRIPTS_DIR` |
| failability: pointed at `dispatch` instead | an `-x`-only check would wrongly accept any executable beside the wrapper | keep | `ok : failability: an assignment pointed at dispatch resolves to an executable (dispatch) and fails the name compare` |
| failability: empty `SCRIPTS_DIR` | a `SCRIPTS_DIR` with nothing in it fails the existence check | keep | `ok : failability: an empty SCRIPTS_DIR fails the existence check (rc=1)` |

### `codex_hooks_vet_wiring_test` (13 cases: 8 fixture + 5 failability/enumeration)

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| a vetted-pass pane answers the modal and reaches `--inject` | the happy path works end to end | keep | `ok : a vetted-pass hooks-review pane answers the modal and reaches orca orchestration dispatch --inject` |
| a missing `HOOKS_ANSWER_BIN` takes the exit-3 path | a missing answer tool refuses instead of attempting the call | keep | `ok : a missing HOOKS_ANSWER_BIN takes the exit-3 path without answering the modal or reaching --inject`; failability below |
| failability: disabling the existence check | the missing-tool refusal is not a tautology | keep | `ok : failability: disabling the existence check attempts the call instead of refusing it (status=3, message dropped)` |
| a directory at `HOOKS_ANSWER_BIN` takes the exit-3 path | `-x` alone would pass for a directory; the guard also checks `-f` | keep | `ok : a directory at HOOKS_ANSWER_BIN takes the exit-3 path without answering the modal or reaching --inject`; failability below |
| failability: dropping the `-f` check | the directory refusal is not a tautology | keep | `ok : failability: dropping the -f check lets an executable directory through instead of refusing it (status=3)` |
| an answer tool exit 1 takes the exit-3 path | the answer tool's own exit code is honored, not assumed | keep | `ok : an answer tool exit 1 takes the exit-3 path without injecting (status=3)`; failability below |
| failability: ignoring the answer tool's exit code | the honored-exit-code assertion is not a tautology | keep | `ok : failability: ignoring the answer tool's exit code injects despite the modal never clearing (status=0)` |
| a vet-failed pane never answers the modal | `codex_hooks_vet_homes` actually gates the answer | keep | `ok : a vet-failed hooks-review pane prints the vet's line and never answers the modal`; failability below |
| failability: disabling the vet gate | the never-answers assertion is not a tautology | keep | `ok : failability: disabling the vet gate answers the modal on a vet-failed home (status=0)` |
| a failing account-seat home blocks the modal | every codex home is checked, not just `$HOME` | keep | `ok : a failing account-seat home blocks the modal despite a passing $HOME hooks.json (status=3)` |
| a failing worktree `.codex/hooks.json` blocks the modal | a project source under `.orca/worktrees/` is in scope | keep | `ok : a failing worktree .codex/hooks.json blocks the modal (status=3)` |
| a failing repository-root `.codex/hooks.json` blocks the modal | the repo root itself is in scope via the `.orca/worktrees` derivation | keep | `ok : a failing repository-root .codex/hooks.json blocks the modal via the .orca/worktrees derivation (status=3)`; failability below |
| failability: a `codex_hooks_homes` that never resolves `WORKTREE` | the repo-root-blocks assertion is not a tautology | keep | `ok : failability: a codex_hooks_homes that never resolves WORKTREE answers the modal despite the failing repo-root hooks.json (status=0)` |

**Runtime.sh totals: 72 cases, 72 keep, 0 duplicate, 0 cannot-fail, 0 low-value.**

The three account/worktree/repo-root "blocks the modal" cases (account-seat, worktree, repo-root) look
parallel on the case table above; they are not duplicates. Each names a different hooks.json source that
`codex_hooks_vet_homes` must enumerate, and only the repo-root case has a failability mutant because it is
the one added most recently (the `.orca/worktrees` derivation).

## tests/test_dispatch_gate.py (assertion-based, 116 cases)

`PYTHONPATH=src python -m pytest tests/test_dispatch_gate.py -q`: **116 passed in 1.14s**.

Cases group into 14 source-function buckets (by reading each test body and naming the function or CLI
subcommand it calls; a test that calls `gate.check()` only to set up a ticket before the real assertion is
grouped under the function the assertion targets, not under `check`):

| source function | cases | mutant run? |
|---|---:|---|
| `DispatchGate.check` (core tier/budget/ticket decision) | 45 | yes |
| `DispatchGate.register_job` + `_model_verification` | 24 | yes |
| CLI `main`/`_check`/`_register`/`_watch` (`scripts/dispatch-gate`) | 14 | yes |
| `_contract_lint_warnings` (via `DispatchGate.check`) | 8 | yes |
| `_default_tier_policy_path` / `_load_tier_policy`(`_v2`) | 6 | yes |
| `_issue_dispatch_ticket` / `_write_dispatch_ticket` | 4 | yes |
| CLI `_report` (`scripts/dispatch-gate`) | 4 | yes |
| `_probe_orchestration_task` (`scripts/dispatch-gate`) | 3 | no (≤3 cases) |
| `watchdog.check_stall` | 2 | no (≤3 cases) |
| `_default_ledger_path` | 2 | no (≤3 cases) |
| `DispatchGateConfig` (positional-arity shim) | 1 | no (≤3 cases) |
| `_measure_worker_model` (`scripts/dispatch-gate`) | 1 | no (≤3 cases) |
| `_probe_contains_job_id` (`scripts/dispatch-gate`) | 1 | no (≤3 cases) |
| docs cross-check (`docs/public/*.md`, no single source function) | 1 | no (≤3 cases) |

**116 total.** Every mutant below used a scratch copy of `src/master_runtime` (or, for the two
`scripts/dispatch-gate` mutants, a reverted scratch copy of that file) under `PYTHONPATH`; the committed
source was never edited for longer than the one command that confirmed the revert.

### Mutants, one per function with more than three cases

**`DispatchGate.check`**: closest assertion pair: `test_runtime_allowlist_allows_known_runtime` and
`test_runtime_allowlist_missing_key_keeps_existing_behavior` (both assert only `decision.allow is True` and
`decision.reason == ReasonCode.OK`). Mutant: the runtime-allowlist guard
(`if tier_policy.runtimes is not None and runtime not in tier_policy.runtimes:`) replaced with `if True:`.
Result: **both tests failed** (`2 failed, 114 deselected`). The pair is not a duplicate of each other in
the sense that matters here (one pins a runtime present in an explicit allowlist, the other pins the
behavior when the policy omits the `runtimes` key entirely), but the two are the closest thing to a
duplicate in this file: three more cases (`test_tier_policy_allows_worker_model`,
`test_v2_uncapped_tier_allows_a_large_fanout`, `test_case_variant_of_allowed_model_stays_allowed`) assert
the same bare `allow is True` / `reason == OK` shape against five different preconditions. None are
duplicates of each other: each pins a different precondition reaching the same shallow outcome. A
future reader should not assume five tests cover five behaviors; they cover five preconditions converging
on one shallow assertion shape.

**`DispatchGate.register_job` + `_model_verification`**: closest pair:
`test_register_allows_a_measured_model_in_a_looser_tier_with_a_warning` and
`test_register_under_a_v1_policy_warns_but_cannot_rank` (both assert only
`ReasonCode.MODEL_MISMATCH in decision.warnings` and `decision.allow is True`). Mutant: the final
`return ReasonCode.MODEL_MISMATCH, None` in `_model_verification` (the v2 strictness-comparison fallthrough)
replaced with `return None, None`. Result: **1 failed, 1 passed**: `..._looser_tier_with_a_warning` failed
(it reaches that exact line); `..._v1_policy_warns_but_cannot_rank` passed unaffected (it returns earlier,
from the `if policy.version < 2:` branch). Not duplicates; two different early-return branches of the same
function happen to produce the same observable warning.

**CLI `main`/`_check`/`_register`/`_watch`**: no two cases share an identical assertion shape (each test's
normalized assertion set differs in at least one line); the closest pair by shared target function is
`test_cli_register_denies_unverified_orchestration_task_with_ledger_entry` and
`test_cli_register_emits_finding_event_for_unverified_orchestration_denial`, both calling
`_deny_unverified_orchestration`. Mutant: removed the `mogui_emit(...)` finding-event call from that
function. Result: **1 failed, 1 passed**: the finding-event test failed as expected
(`assert 0 == 1`); the ledger-entry test passed unaffected. Not duplicates; one pins the ledger write, the
other pins the telemetry emit, both inside the same denial path.

**`_contract_lint_warnings`**: closest pair: `test_contract_lint_accepts_mcp_with_trust_handling` and
`test_contract_lint_accepts_mcp_with_korean_trust_handling` (both assert only
`ReasonCode.MCP_TRUST_UNHANDLED not in decision.warnings`). Mutant: the trust-handling regex's two Korean
alternatives (meaning "trust" and "dialog") dropped, leaving only the English `trust` alternative.
Result: **1 failed, 1 passed**: the Korean-language case
failed as expected; the English case passed unaffected. Not duplicates; one pins the English trust phrase,
the other pins the Korean one, same ReasonCode.

**`_default_tier_policy_path`**: closest pair: `test_default_tier_policy_uses_template_when_instance_absent`
and `test_default_tier_policy_prefers_instance_when_present` (both reduce, after normalizing literals, to
the same `assert _default_tier_policy_path(...) == expected` shape). Mutant: the
`if instance_path.is_file(): return instance_path` branch removed, always falling through to the template
path. Result: **1 failed, 1 passed**: `..._prefers_instance_when_present` failed as expected; the
instance-absent case passed unaffected (it already expects the template path). Not duplicates.

**`_issue_dispatch_ticket`**: closest pair: `test_check_deny_does_not_issue_dispatch_ticket` and
`test_issue_dispatch_ticket_allow_guard_skips_deny_decision` (both assert only
`not (tmp_path / "dispatch-tickets").exists()`). Mutant: the `if not decision.allow: return` guard removed
from `_issue_dispatch_ticket`, leaving only the `if decision.contract_sha is None: return` guard. Result:
**1 failed, 1 passed**: the direct-call test (`..._allow_guard_skips_deny_decision`) failed as expected;
`test_check_deny_does_not_issue_dispatch_ticket`, which reaches `_issue_dispatch_ticket` through the real
`check()` path on a `BUDGET_EXCEEDED` denial, passed unaffected. That denial path never sets
`contract_sha`, so the second guard alone already protects it. **This case does not exercise the
allow-guard it sits beside in the table above**, a narrower claim than its name suggests. Worth a note for
a future reader, not a deletion: it still pins a real property (budget denial through the public `check()`
API writes no ticket), just not the specific guard line.

**CLI `_report`**: closest pair: `test_cli_report_uses_stored_cost_and_labels_legacy_computation` and
`test_cli_report_skips_non_object_and_invalid_timestamps` (both reduce to `"..." in output` plus
`script["main"](...) == 0`). Mutant: `_entry_cost_proxy`'s legacy-computation return
(`return max(0, est_chars) * max(0, n_agents), True`) replaced with `return 0, True`. Result: **1 failed, 1
passed**: the legacy-cost test failed as expected (`est_cost_proxy=60` never appeared); the
malformed-timestamp test passed unaffected (its cost values come from a stored `cost_proxy` field, not the
legacy computation). Not duplicates.

**Gate.py totals: 116 cases, 0 duplicate confirmed by mutant evidence, 0 cannot-fail, 0 low-value.** Every
"identical assertion shape" pair this round found turned out, under a shared mutant, to protect a different
branch, precondition, or side effect of its source function.

## scripts/test-dispatch-timeline.sh

Full run: `timeout 90 bash scripts/test-dispatch-timeline.sh`: exit 0, 15 `ok` lines.

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| root: `MOGUI_RUNTIME_ROOT` wins over a valid two-up layout | the override takes priority | keep | `ok: root: MOGUI_RUNTIME_ROOT wins over a valid two-up layout (exit 0)` |
| root: no override and no two-up layout prints SKIP | a test with nothing to measure skips instead of failing | keep | `ok: root: no override and no two-up layout prints SKIP and signals not-found (exit 1)` |
| root: a stale override falls back to a valid two-up layout | an existing-but-wrong `MOGUI_RUNTIME_ROOT` does not win | keep | `ok: root: a stale MOGUI_RUNTIME_ROOT without the marker falls back to the valid two-up layout` |
| failability: the old unconditional two-up `ROOT=` line | the override-wins assertion is not a tautology against the pre-fix code | keep | `ok: failability: the old ROOT line ignores MOGUI_RUNTIME_ROOT` |
| json: three sources join in time order, none missing | `--json` merges ledger, event-log, and `dispatch-show` and sorts by timestamp | keep | `ok: json: exit 0, all three sources joined in time order, none missing` |
| failability: removing the sort | the time-order assertion is not a tautology | keep | `ok: failability: removing the sort puts the ledger row first instead of the earlier event-log row` |
| restored: sort reappears | the mutant above only ran against a scratch copy | keep | `ok: restored: unmutated core module sorts the event-log row first again` |
| json: an id with nothing in any source names all three as missing | `missing_sources` is accurate when every source is empty | keep | `ok: json: an id with nothing anywhere names all three sources as missing` |
| usage: `--since` with a positional id exits 2 | the two modes are mutually exclusive at the CLI | keep | `ok: usage: --since with a positional id exits 2` |
| usage: `--since nan/inf/-1` each exit 2 | non-finite and negative hours are rejected at parse time | keep | `ok: usage: --since nan exits 2` (and `inf`, `-1`) |
| since: a positive window lists the existing fixture | `--since` actually filters and lists dispatches | keep | `ok: since: a positive window lists ctx_demo/task_demo from the existing fixtures` |
| failability: emptying `list_since` | the positive-window assertion is not a tautology | keep | `ok: failability: emptying list_since drops the previously-listed dispatch id` |
| human-readable: an out-of-range timestamp prints `unparseable` | an overflow timestamp degrades gracefully instead of crashing | keep | `ok: human-readable: an out-of-range timestamp prints 'unparseable' instead of crashing` |

**Totals: 13 distinguishable cases (the three bad-`--since` values share one case, each independently
confirmed `exit 2`), all keep, 0 duplicate, 0 cannot-fail, 0 low-value.** No additional mutant was added:
every case's assertion names a specific exit code or a specific substring of the real tool's output, and
each is capable of failing against its own described regression.

## scripts/test-worker-wait.sh

Full run: `timeout 90 bash scripts/test-worker-wait.sh`: exit 0, 6 `ok` lines.

| case | pinned behavior | verdict | evidence |
|---|---|---|---|
| once/json: DEAD verdict for a recorded pid that is not alive | `--once --json` probes the exact recorded pid and reports DEAD | keep | `ok: once/json: exit 0, DEAD verdict for a recorded pid that is not alive` |
| failability: dropping the `DEAD` return | the DEAD-verdict assertion is not a tautology | keep | `ok: failability: dropping the DEAD return makes this case fail` |
| restored: DEAD reappears | the mutant above only ran against a scratch copy | keep | `ok: restored: unmutated script reports DEAD again` |
| lock held by a live pid: second waiter exits 2 | a concurrent waiter is refused with a one-line message | keep | `ok: lock held by a live pid: second waiter exits 2 with a one-line message` |
| failability: dropping the lock-alive check | the refusal assertion is not a tautology | keep | `ok: failability: dropping the lock-alive check no longer exits 2 (lock bypassed)` |
| restored: the held lock still refuses | the mutant above only ran against a scratch copy | keep | `ok: restored: unmutated script still refuses the held lock with exit 2` |

**Totals: 2 distinguishable cases (DEAD verdict, lock refusal), each already carrying its own inline
mutant, 0 duplicate, 0 cannot-fail, 0 low-value.** No additional mutant was needed.

## Summary

| file | cases | keep | duplicate | cannot-fail | low-value |
|---|---:|---:|---:|---:|---:|
| `scripts/test-dispatch-runtime.sh` | 72 | 72 | 0 | 0 | 0 |
| `tests/test_dispatch_gate.py` | 116 | 116 | 0 | 0 | 0 |
| `scripts/test-dispatch-timeline.sh` | 13 | 13 | 0 | 0 | 0 |
| `scripts/test-worker-wait.sh` | 2 | 2 | 0 | 0 | 0 |
| **total** | **203** | **203** | **0** | **0** | **0** |

## Candidate deletions

None. Every case this round measured earns its keep; no deletion in this PR either way.

## Follow-ups

- `tests/test_dispatch_gate.py`'s `DispatchGate.check` bucket (45 cases) carries five tests whose
  assertions reduce to the same bare `allow is True` / `reason == OK` shape over five different
  preconditions (noted above). None are duplicates, but a reader auditing this file later should start
  there instead of re-deriving the same finding.
- `test_check_deny_does_not_issue_dispatch_ticket` does not exercise `_issue_dispatch_ticket`'s own
  allow-guard (noted above); it is protected by a different guard in the same function. No action needed.
  Recorded so a future edit to the allow-guard does not assume this test would catch a regression in it.
