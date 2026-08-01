# Security Policy

One maintainer, no company behind it. This document says what that means for a
vulnerability report so you can decide whether to send one here or handle it
another way.

## Reporting

Use [private vulnerability
reporting](https://github.com/baksohyeon/mogui-ADE-orchestrator/security/advisories/new).
It opens a private thread with the maintainer and does not disclose anything
until an advisory is published.

Do not open a public issue for a vulnerability. Public issues are the right
place for everything else, including a bug that merely looks alarming.

## What to expect

Best effort, no service level agreement. A realistic expectation is
acknowledgement within a week and a fix or a decision within a month. If a
month passes with no reply, treat the report as unread and disclose on whatever
timeline you think is right. Silence here means the maintainer missed it, not
that disclosure is unwelcome.

Fixes land on `main` and in the next release. There are no backports: while the
major version is 0, only the latest release is supported.

| Version | Supported |
| --- | --- |
| latest release | yes |
| anything earlier | no |

## Scope

This is an orchestrator that runs coding agents on your machine, under your
account, against your repositories. It runs with whatever the shell it launched
from can reach.

In scope:

- The runtime under `src/master_runtime/` and the scripts under `scripts/`
- Anything that causes the orchestrator to run a command, read a path, or
  dispatch a worker outside what the caller asked for
- The redaction scanners reporting clean when they did not read what they
  claimed to read

Out of scope:

- The agent runtimes it dispatches to. Report those to their own projects.
- The template under `master-ops/`, which is copied into your repository and
  becomes yours to review before you run it
- A model producing wrong or harmful output. That is a property of the model,
  and this project's answer to it is verification before acceptance rather than
  trust.

## Known limits, already public

These are documented rather than fixed, so they are not vulnerabilities:

- No CI at 0.1.0. The scanners and tests run locally before a push, so a green
  result in a pull request is the author's word.
- The redaction scanners read tracked files only. An unstaged new file is
  invisible to them and the run still reports clean.
- `redaction-inventory` skips binary files, judged by a NUL byte in the first
  8 KB, and does not say so in its output.

If you find that one of these is worse than described, that is worth a report.
