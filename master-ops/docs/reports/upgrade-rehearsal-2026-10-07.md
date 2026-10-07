# Upgrade-mode onboarding rehearsal, 2026-10-07

Scope: a full run of the router's Upgrade mode (`onboarding/upgrade.md`) against a scratch
clone of the operations repository at `7c0c34e`, with this worktree's template root (`b4b11b6`, template
version `v0.5.239`) as the template. No code change, no push to the clone, no access to the real seat.
This PR adds this report, one changelog fragment, and the regenerated manifest.

## 1. Check

`template-check --ops <clone> --template <this worktree's template root> --json`, then the same without
`--json`:

| field | value |
|---|---|
| report_set | template-compare |
| installed_version | v0.5.230 |
| template_version | v0.5.239 |
| absent_required | 1: `docs/reports/test-audit-2026-10-06.md` |
| unknown_present | 48 paths (agent-harness configs, analysis/blame/postmortem docs, local-only test scripts, one compiled `.pyc`) |
| retired | 1: `scripts/hooks/bash-poll-warn.sh` |
| exit status | 1, both runs |

## 2. Dry run

`template-apply --ops <clone> --template <this worktree's template root>`, no `--placeholder`: exit 0,
no placeholder demand. 119 entries: 118 `planned` (117 `would overwrite existing file`, 1
`would create missing file`: `docs/reports/test-audit-2026-10-06.md`) and 1
`skipped-as-instance-owned` (`docs/runbooks/role-state.md`). One run was sufficient; the tool never
refused or prompted for a placeholder value at this stage.

## 3. Write pass

Rerun with `--write`. The confirmation prompt reads stdin directly (`sys.stdin.readline()`, no
`isatty` check), so piping the phrase `apply` on stdin was accepted without a terminal: exit 0, 118
`written`, 1 `skipped-as-instance-owned`, matching the dry-run plan exactly.

After the write, on the clone:
- `git status --short`: 66 lines (63 modified, 2 untracked files, 1 untracked directory:
  `scripts/__pycache__/`)
- `git diff --stat`: 63 files changed, 1187 insertions(+), 1916 deletions(-)

The clone was never pushed.

## 4. Refusals

Of the five named instance-owned paths, only `docs/runbooks/role-state.md` is refused by name in the
plan. `docs/lineage/`, `.beads/`, `config/`, and `contracts/` never appear in the plan at all, neither
as `planned` nor as any refusal outcome: `template-apply` builds its plan from the template's own
manifest entries and writes each to its matching ops path; a destination path with no template-side
counterpart is never visited, so it is invisible to the tool rather than refused. The same holds for
the 48 `unknown_present` paths from step 1: none of them appear in the dry-run plan by name.

Confirmed by code: forcing the tool to evaluate a specific path's refusal requires `--attempt`, a flag
present in the script but suppressed from `--help` and marked test-only ("prove refusal" in its own
source comment). Without it, nothing drives the tool to look at an ops-side path the template does not
also ship.

## 5. Re-check

`template-check --template <this worktree's template root>` on the written clone:

| field | value |
|---|---|
| installed_version | v0.5.239 |
| absent_required | 0 |
| unknown_present | 48 (unchanged) |
| retired | 1: `scripts/hooks/bash-poll-warn.sh` (unchanged, see Findings) |
| exit status | 0 |

## 6. Postconditions

`onboarding-rehearsal --workspace-root <empty scratch dir> --ops-repo <clone> --json`, no `--live`:

| ID | status | expected | observed |
|---|---|---|---|
| P01 | FAIL | router and step directory exist | missing |
| P02 | FAIL | no unresolved placeholders in ops repository | 43 files, see Findings |
| P03 | PASS | ops CLAUDE.md and AGENTS.md are byte-identical | byte-identical |
| P04 | FAIL | deployed root card equals ops canonical card | missing or different |
| P05 | FAIL | workspace descriptor satisfies loader rules and names this root | missing or invalid |
| P06 | FAIL | instance runtime names the master host runtime | missing or invalid |
| P07 | PASS | `docs/runbooks/role-state.md` exists | present |
| P08 | PASS | `docs/lineage/MASTER-LINEAGE.md` exists | present |
| L01 | GAP | live master seat is measured | live checks not requested |
| L02 | GAP | live master role identity is measured | live checks not requested |

P01, P04, P05, and P06 fail because the workspace root passed to the script was an empty directory:
this rehearsal never ran the router's onboarding steps against it, by design (contract scope is
template-apply and its gates, not a full onboarding). The contract names P04 and P05 as expected
GAP-or-FAIL for this reason; P01 and P06 fail for the identical cause and are reported as such rather
than faked.

## 7. Gates

`redaction-scan.sh` from the clone root: printed
`WARNING — organization-specific rules not loaded (REDACTION_EXTRA_PATTERNS unset or empty)`,
73 findings, exit 1 (fail-closed). Every finding is a `home_path` match in content the clone already
carried from GitHub (historical contracts and `.beads/interactions.jsonl`); none sit in a file this
rehearsal's write pass touched.

Every `scripts/test-*.sh` in the clone: 21 scripts, 19 pass, 2 fail
(`test-dispatch-multi-vendor-host.sh`, `test-tracker-check-banner.sh`; see Findings).

## Findings

| step | what happened | exact message | classification |
|---|---|---|---|
| 2/3 | `template-apply --write` with no `--placeholder` completed at exit 0 while leaving every `{{...}}` token in every written file untouched. `substitute()` only replaces a token when its key is present in the `--placeholder` values dict; with no flags passed, that dict is empty, so nothing is substituted and nothing warns. | n/a (silent; confirmed by reading `substitute()` in `scripts/template-apply`) | template defect |
| 3/7 | One of the untouched tokens is load-bearing in executable code: `scripts/dispatch` line 8 reads `OPS={{OPS_REPO}}` verbatim after the write. `test-dispatch-multi-vendor-host.sh` fails on exactly this: `FileNotFoundError: [Errno 2] No such file or directory: '{{OPS_REPO}}/model-tier-policy.json'`. | `FileNotFoundError: [Errno 2] No such file or directory: '{{OPS_REPO}}/model-tier-policy.json'` | template defect |
| 3/5 | `config/template-retirements.json` on the clone lists `scripts/hooks/bash-poll-warn.sh` as retired, with a reason. `template-apply` has no reference to retirements anywhere in its source and recreated the file on the write pass; the step-5 re-check still reports it `retired`, meaning `template-check` and the ops install agree it should be gone while `template-apply` just put it back. | n/a (confirmed: `grep -i retire scripts/template-apply` has no match) | template defect |
| 4 | Refusal-by-name covers only `docs/runbooks/role-state.md`. `docs/lineage/`, `.beads/`, `config/`, `contracts/`, and the 48 `unknown_present` paths are never evaluated for refusal; reaching that code path at all requires the undocumented, help-suppressed `--attempt` flag. | n/a | template defect |
| 7 | `test-tracker-check-banner.sh` asserts `~/.mogui/hook-fire-log.jsonl`'s line count is unchanged across its run. The assertion failed (`before=52453 after=52454`) because this rehearsal ran inside a live, hook-instrumented session whose own tool calls append to that same file. | `FAIL: real hook fire log changed before=52453 after=52454` | expected (environmental; not isolated from the host session's own hook activity) |
| 6 | P01, P04, P05, P06 fail because the scratch workspace root was never onboarded; no router run, no `config/workspace-descriptor.json`, no `config/instance-runtime.json` exist there. | see table above | expected |
| 7 | Redaction scan's 73 findings are pre-existing `home_path` matches in content the clone already carried from GitHub history, and the organization-rules warning means only generic patterns ran. | `WARNING — organization-specific rules not loaded` | expected |

## What the real re-stamp does by hand

- **Owner confirmation.** The write pass has no `--yes`; the operator (or an agent acting for them) must
  type `apply` at the interactive prompt. A headless pipe satisfies the prompt (confirmed working above),
  but the phrase itself still has to come from a deliberate step, not a default.
- **Placeholders.** `template-apply` will not prompt for, warn about, or refuse a missing placeholder; it
  silently ships `{{...}}` tokens verbatim, including inside executable script source. The real re-stamp
  must supply all eight documented placeholders (`WORKSPACE_NAME`, `WORKSPACE_ROOT`, `OPS_REPO`,
  `MONITOR_NS`, `MODEL_ID`, `REPO_LIST`, `RUNTIME_ROOT`, `TEMPLATE_VERSION`) explicitly via repeated
  `--placeholder KEY=VALUE`, reading the values from the seat's own `config/workspace-descriptor.json`
  and already-substituted files per `ONBOARDING.md`. This rehearsal's bare GitHub clone had no
  such config to read from, so this step could not be rehearsed end to end here; it is the first thing
  the real re-stamp needs that this rehearsal does not cover.
- **The retired file.** `scripts/hooks/bash-poll-warn.sh` is in the seat's own
  `config/template-retirements.json`. The write pass will recreate it regardless; after the real write
  pass, the operator needs to remove it again by hand to keep the seat's retirement in effect.
- **Refused paths needing a hand merge.** Only `docs/runbooks/role-state.md` is refused by name. Nothing
  else protects `docs/lineage/`, `.beads/`, `config/`, or `contracts/` beyond the fact that the template
  does not ship matching paths today; a future template change that did add a path under one of those
  prefixes would need a manual diff and merge, not an automatic refusal.
- **Instance-owned files that drift.** The 48 `unknown_present` paths (this seat's own agent-harness
  configs, analysis/blame/postmortem docs, local test scripts, and one compiled `.pyc`) are untouched by
  `template-apply` and will keep showing up in every future `template-check` run; the re-stamp does not
  need to reconcile them.
