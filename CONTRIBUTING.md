# Contributing

Small repository, one maintainer. Issues and pull requests are both welcome.

## Running it

```console
$ PYTHONPATH=src python3 -m pytest tests -q
```

The runtime is standard library only. The test run needs pytest (`python3 -m pip install pytest`).

There is no CI yet, so run this before opening a pull request. Name the test that fails without your change, or say why none was needed. A passing count on its own says nothing: it is the same number on every branch that adds no test.

## What gets merged

A change with a test that fails without it. If a test does not make sense for
the change, say so in the pull request and why.

Documentation changes need no test. Say what was wrong with the old wording.

## Things worth knowing before you start

**Exit codes carry meaning here.** Several scripts use 0 for a clean result, 1
for a finding, and 2 for "could not decide". An unhandled exception exits 1,
which reads as a finding, so a crash and a verdict look the same to a caller.
When you add a failure path, make sure it lands on 2. That single mistake is
the largest class of review findings this repository has had.

`redaction-scan.sh` is an exception it declares in its own header: it folds a
usage or tool error into 1. Read each script's codes rather than assuming.

**The redaction scanners read tracked files.** An unstaged new file is
invisible to them, and the run comes back green without having looked at it.
Stage first, then scan. These run locally before publishing, not in CI.

`redaction-inventory` also skips binary files, judged by a NUL byte in the
first 8 KB. That is a heuristic and it is silent: the output still says the
scope was every tracked file.

**`master-ops/` is a template**, copied into a user's own operations repository
during onboarding. It is not documentation about this repository. Changes there
reach new installations only. Existing ones are copies and do not update.

**Capture exit codes directly.** `out=$(cmd 2>&1); rc=$?` rather than through a
pipe, where `$?` belongs to the last command in the pipeline.

## Scope

This repository owns workspace-level orchestration: roles, succession, worker
dispatch, lineage. Repository-local rules, hooks, and runbooks belong to
[mogui-agent-harness](https://github.com/baksohyeon/mogui-agent-harness).

Supported platform is macOS. The master has only been run under Claude Code.
Other hosts and platforms should work and have not been tried, so reports from
anyone who does are useful.

## Commits

Conventional commits, English. `feat(scope):`, `fix(scope):`, `docs(scope):`.
Say what changed and what made it necessary. Pull requests are squashed.
