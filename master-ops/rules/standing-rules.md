# Standing rules

Five named rule blocks, each a `## <name>` heading. A contract's front matter
may name any subset of these under `standing_rules: [...]`; `scripts/dispatch`
reads the named blocks and appends their text to the dispatched spec, so a
worker receives the rule as part of its own task text instead of needing a
human to paste it in by hand. A seat may add further blocks in the overlay
`config/standing-rules.overlay.md`, which this file ships none of. This file
refreshes on every template re-stamp; the overlay, in the instance-owned
`config/` directory, never does.

## headless

You are headless. Do not background any command, do not use any
background-task facility, never start a watch and end your turn. Poll in the
foreground with a bounded loop.

## ack-token

The worker types the acknowledgement token bare in its completion message. The
token never appears in a commit, a pull request body, or a review reply.

## placement

The first action reports three lines and no absolute path: `in_expected_worktree:
yes|no`, `is_master_checkout: yes|no` (yes stops the task), and `branch: <git
branch --show-current>` next to the expected base sha.

## voice

Everything on the pull request is written in English. The rules of
`docs/runbooks/review-voice.md` apply to the body, the commit messages, and
every reply, including rule 9's ban on naming a discarded option before
asserting the kept one. No absolute home path or username appears anywhere,
and sentences use plain punctuation, never the long dash.

## pr-house

Titles follow `<type>: <lowercase description>`, `<type>` one of feat, fix,
docs, refactor, test, chore, perf, or ci. The assignee is set at creation,
never after. The body fills every section the repository's pull request
template names, including the four narrative ones: Problem, Why this
approach, What this changes, Expected effect, plus a provenance line. A
review-bot thread gets a reply inside the thread and a resolve; a silent
batch resolve is never acceptable.
