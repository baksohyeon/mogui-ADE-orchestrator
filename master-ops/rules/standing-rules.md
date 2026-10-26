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
branch --show-current>` next to the base sha the dispatching contract states.

## voice

Everything on the pull request is written in English, the same voice in
every reply and commit message. Keep the PR body current with the branch as
it stands now. Point at the code line and include a concrete replacement a
reviewer can take as written. Write courteous, humble, and collaborative,
like a colleague who expects to be wrong sometimes. Fault the interface, the
system, or the architecture, never the person or the bot that read what was
there to be misread. State the kept option on its own, without first naming
the one left behind. No long dash anywhere, no stock opening line that
praises, flags, or pivots before the point lands, and no absolute home path
or username anywhere. Full text: `docs/runbooks/review-voice.md` in the
template checkout, a sibling of this file's own `rules/` directory.

## pr-house

Titles follow `<type>: <lowercase description>`, `<type>` one of feat, fix,
docs, refactor, test, chore, perf, or ci. The assignee is set at creation,
never after. The body fills every section the repository's pull request
template names, including the four narrative ones: Problem, Why this
approach, What this changes, Expected effect, plus a provenance line. A
review-bot thread gets a reply inside the thread and a resolve; a silent
batch resolve is never acceptable.
