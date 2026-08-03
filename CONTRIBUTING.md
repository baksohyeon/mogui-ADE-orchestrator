# Contributing

Small repository, one maintainer. Issues and pull requests are both welcome.

## Adding a component to the harness

Answer these five before proposing any tool, and put the answers in the pull request. A component that arrives without them is one nobody can argue out later.

1. Does it require an API key?
2. Does it force telemetry, or collect more than the job needs?
3. Does it add a management point?
4. Does it still work if the operation grows past one person?
5. Every tool claims to help with agent context. What else does this one actually resolve?

The first three are usually disqualifying on their own: a component that fails them is a subscription presenting itself as a dependency. A component that passes them and answers nothing for the fifth is a preference. Preferences are allowed, and they get labelled as preferences, and nothing gates on them.

This is a maintainer question rather than an operator one. An installation does not choose the stack; it receives one, and the onboarding flow (`master-ops/onboarding/08-settings-and-skills.md`, routed from `master-ops/ONBOARDING.md`) carries the same five questions for the narrower decision an installer does make, which is what to install of what is offered.

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
Stage first, then scan.

CI (`.github/workflows/gates.yml`) runs the test suite and the scan with the
committed ruleset on every pull request. The organization rules file is
deliberately not in the repository, so the full scan with those rules still
runs only locally. To make the local scan automatic, enable the committed
pre-push hook once per clone:

```console
$ git config core.hooksPath hooks
```

The hook runs the scan and nothing else — the test suite stays out of it, so
the hook stays fast enough that nobody reaches for `--no-verify`.

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

Developed and run on macOS, under Claude Code. Orca ships Linux and Windows
builds and one user has reported the Linux install working, but nothing here is
exercised on either. Other hosts and platforms should work and have not been
tried, so reports from anyone who does are useful.

## Commits

Conventional commits, English. `feat(scope):`, `fix(scope):`, `docs(scope):`.
Say what changed and what made it necessary. Pull requests are squashed.

Much of this repository is written by an AI agent under a maintainer's
direction. Where that is true the commit carries a `Co-Authored-By` trailer
naming the model. Commits before this convention was adopted do not have one,
so absence means "written earlier", not "written by hand".
