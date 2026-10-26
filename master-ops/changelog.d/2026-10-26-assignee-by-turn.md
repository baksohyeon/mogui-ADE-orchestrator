`labeler.yml` now also triggers on `labeled` and `unlabeled`, with a new `assignee follows the turn`
step: every run sets the assignee to the author while `waiting-user-response` is on and the author
is not a bot, and to the maintainer otherwise. An assignee other than those two logins stays as it
is. Every assignment check reads current assignees first, and a 404 from a removed account does not
fail the workflow. The step runs in its own `assignee` job with its own concurrency group and
`cancel-in-progress: false`, so a push or a second label event queues behind it instead of
cancelling it mid-run. Every surviving run reconciles the desired assignee from the pull request's
current labels instead of the triggering event, so it converges to the same assignee no matter which
job starts first.
