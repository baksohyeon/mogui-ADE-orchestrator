# §8. Boot, Hooks, And Observability

Governs boot configuration, hook wiring, and observability practices. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Hook wiring is a specification here. Apply concrete hook configuration through a human or dedicated security/operations session.

Orca command and orchestration references are grounded through `docs/orca-docs-grounding.md`; start there and never guess Orca flags.

Recommended hook spec:

- SessionStart: load master operations context, role state, and issue-tracker memory
- SessionStart on compact: run `scripts/compaction-probe.sh`
- PreCompact: reload or export issue-tracker memory
- UserPromptSubmit: inject the current role-state line from `docs/runbooks/role-state.md` and the `Proposal -> Approval -> Execution` rule. This pairing mechanically counters the host's autonomy defaults, which can override the charter unless the execution rule is present in every turn's context. See §9 for the incident that motivated this coupling.
- UserPromptSubmit: warn when unacknowledged orchestration inbox messages exist, using `scripts/hooks/orch-inbox-warn.sh`.
- PreToolUse(Bash): warn when a hand-rolled poll loop appears; event waits use `scripts/orca-wait`. See `docs/runbooks/orca-wait.md`.
- PreToolUse: warn when supervised dispatch is bypassed
- PostToolUse: collect non-sensitive audit markers when locally approved
- SessionStart: warn when the issue tracker is not reachable from `{{WORKSPACE_ROOT}}`, or when an environment variable points its database outside the workspace

The tracker SessionStart warning covers a failure that is otherwise silent. The
master runs at the workspace root, and a tracker that resolves its database
from the current directory finds nothing there, or finds a product repository's
database. Boot continues either way. Measure the environment variable in the
same shell the agent's tool calls use; a login shell can define a different
value, and reading the wrong one turns the check into a pass.

Every shipped hook should append one fail-open fire-log record to
`~/.mogui/hook-fire-log.jsonl` before doing its ordinary work, then continue
even if logging fails. Read `docs/runbooks/hook-fire-observability.md` and
`scripts/hook-coverage-report` when measuring whether hooks actually fire.

Context-quality monitor namespace: `{{MONITOR_NS}}`

Lineage is append-only observability metadata. Do not use Lineage as the bootstrap source, priority source, or model-evaluation source.

Git history and the issue tracker record what happened but cannot record what shaped the master's behaviour, what it nearly did, or what it declined to do. Without that layer the owner's only observation channel is a post-incident report, which arrives only after something broke. The observability suite (`docs/observability/README.md`) fills it with standing records: blame recovers what was observed and where observation outran cause, the retro ledger answers why a decision took the shape it did, and the travelog answers what happened. Attribution tags, the falsifiability rule for judgment claims, freshness honesty after compaction, and the requirement to list what did not fire are specified once in that index and apply to every genre.

**Probe a tool with a subcommand it must have, not a flag you assume.**
Observed: a health check ran `orca --version`. That flag does not exist: on one host it printed the usage banner and exited 0, so the check passed while proving nothing, and a Linux user reported the same command launching the GUI application instead of answering.
Measure: run the probe and read its output, not just its exit code. A probe whose output does not contain the fact you wanted is not a probe. Prefer the documented subcommand, here `status --json`, which fails cleanly when the tool is unusable.

**Publish gates read repository content and nothing else.**
Observed: pull request bodies, review comments, release notes, and issue text are not in the repository, so no scanner in this template reads them. An audit of one day's outgoing text found none, which is the point: it took a separate grep to know.
Measure: before posting outgoing text, grep it for organization identifiers the way the scan greps files. A green publish gate says nothing about prose written into a forge.

For conversation surfaces, use `scripts/pr-body-check` before posting or
updating a pull request body, and use `scripts/conversation-redaction-scan` for
periodic sweeps of PR bodies, PR comments, review comments, and issue bodies.
The scanner reports the surface and pattern class but not the matched value.

### Tool Boundaries

Each tool has a role and an edge. The edge is the part that gets lost first.

- The execution substrate owns worktrees, terminals, sessions, and supervised dispatch. Placement checks read its state; they are not a dispatch mechanism.
- The tracker owns execution state across sessions. Its memory is a pointer cache toward Git, kept small and curated; it is not the knowledge source of truth, and it is not a second copy of this document.
- The history index is a trace archive. Query it when the handoff, the ledger, and Git together do not answer a question. It does not belong in routine boot context.
- The secret scanner is a matching engine. Scope, commit messages, and what the run covered stay with the wrapper, because those are decisions rather than matches.
- The review graph earns its place on token cost and impact radius, not on correctness. Nothing gates on it.
- Documentation stays plain Markdown in Git. No format lock means any tool can read it, including the next one.
