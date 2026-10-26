`labeler.yml` now also triggers on `labeled` and `unlabeled`, with a new `assignee follows the turn`
step: adding `waiting-user-response` moves the assignee from the maintainer to the pull request
author, removing it moves the assignee back, and a pull request opened with no assignee gets the
maintainer. A bot author is never assigned; the maintainer stays assignee in that case. Every
assignment check reads current assignees first, and a 404 from a removed account does not fail the
workflow. The step runs in its own `assignee` job with its own concurrency group and
`cancel-in-progress: false`, so a push or a second label event queues behind it instead of
cancelling it mid-run.
