# Standing rules

Seven named rule blocks, each a `## <name>` heading. A contract's front matter
may name any subset of these under `standing_rules: [...]`; `scripts/dispatch`
reads the named blocks and appends their text to the dispatched spec, so a
worker receives the rule as part of its own task text instead of needing a
human to paste it in by hand. A seat may add further blocks in the overlay
`config/standing-rules.overlay.md`, which this file ships none of. This file
refreshes on every template re-stamp; the overlay, in the instance-owned
`config/` directory, never does.

`mail-before-done` is the one exception to "named under `standing_rules`":
`scripts/dispatch` appends it to every brief whether or not a contract's
front matter names it, the same way it always appends the worker token
budget line below the standing-rule blocks. Naming it explicitly in
`standing_rules` is harmless (the gate accepts it as a known block, same as
the other six) but has no further effect, since the wrapper was going to add
it anyway.

## headless

You are headless. Do not background any command, do not use any
background-task facility, never start a watch and end your turn. Poll in the
foreground with a bounded loop.

## headless-browser-first

When checking a web page, use Orca's embedded browser first with `orca tab create`,
`orca snapshot`, `orca screenshot`, and page actions such as `orca click` or
`orca fill`. If that does not cover the check, use a headless Chrome screenshot
or an already-installed Playwright, and use `curl` for plain HTTP or HTML
structure. Use Computer Use or drive the owner's browser only when the work
requires a visible GUI these options cannot cover; ask the coordinator first and
name why.

## ack-token

The worker types the acknowledgement token bare in its completion message. The
token never appears in a commit, a pull request body, or a review reply.

## mail-before-done

Before `worker_done`, run `orca orchestration check` in a loop, up to 10
calls. Its default call returns and marks handled only the oldest unread
FIFO batch (`orca orchestration check --help`), so a single call can leave
newer mail unread. Apply each returned batch before reporting, or say in
the completion message why not, and keep calling until one returns no
mail. Stop at 10 calls even if mail remains and name that cap in the
completion message. If a check itself fails, name the failed check and
its error text in the completion message.

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
