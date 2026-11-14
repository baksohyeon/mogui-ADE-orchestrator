Codex workers launched in linked worktrees now receive the repository's shared Git
directory as the only extra writable root. The dispatch ledger accepts one locked
`git_escalation` event per reported retry with the dispatch id, worktree, operation,
escalation state, and first refusal line.

The shared Git directory includes `.git/hooks` and `.git/config`, so this owner-chosen
scope allows a worker to plant a hook or change `core.hooksPath`, `core.fsmonitor`, or
an alias that could run later when the owner or master runs Git in the main checkout.
When the wrapper observes a completed dispatch, it compares the shared config hash and
the hooks directory listing with each hook's bounded content digest and mode bits
against the dispatch-time snapshot and prints one warning line if either changed.
Special hook entries are recorded without reading them, so the snapshot remains
bounded even when a writable hooks directory contains a FIFO. Symlink targets are
recorded with `readlink` without opening the target. The warning is informational
and does not block completion.
