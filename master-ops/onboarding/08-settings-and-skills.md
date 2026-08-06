# 08 — Settings Layer, Skill Layer, Gate Scope (Steps 7, 7.5, 7.6)

Load rule: read this file only when Step 7 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `09-spawn.md`.

## Step 7. Explain the settings layer (default-on harness wiring)

**Position and action:** Step 7 begins with durable user rules seeded: identify the host and the owner of settings and sensitive configuration, then wire the shipped harness **on by default**.

**Why/caution:** The template specifies hook behavior but does not ship hidden deny lists, credentials, secret paths, or environment-specific security implementation. A harness whose pieces are individually opt-in protects nothing — install everything on, and disable later by asking.

### Owner script (kind ELI5, adapt to the owner's language)

Where we are: the Master's ground rules are saved, and the Herald now prepares the host-side safeguards before the Master rises. What happens next: we turn on the safety hooks and skills this template ships, all together, so the Master wakes with the same guards every install. Explain in simple terms that hooks are small host-side actions: some prepare the Master's context when it starts or resumes, some refresh it during a session, and some warn before risky actions. One warm sentence for the owner: **everything is on by default, and any piece can be turned off later by just asking the Master — who will explain what that piece does before disabling it.** Confirm who owns host settings and security-sensitive configuration (often the owner themselves). Do **not** ask per-hook or per-skill enable questions. Present the hook wiring spec from `docs/MASTER-OPERATIONS.md` in agent notes, not as a wall of text at the owner; delegate auth, permission, secrets, credentials, and production-data work to a dedicated security/operations session.

### Default-on wiring (agent actions)

Wire every shipped hook and skill this template documents, without offering an opt-out menu:

- SessionStart: master operations context, role state, tracker memory
- SessionStart on compact: `scripts/compaction-probe.sh`
- PreCompact: reload or export tracker memory
- UserPromptSubmit: role-state line + `Proposal -> Approval -> Execution` (see charter §8 / §9)
- PreToolUse: supervised-dispatch bypass warning
- PreToolUse(Edit|Write|NotebookEdit) and PreToolUse(Bash): fail closed for
  product-repository writes with `scripts/hooks/product-path-guard.sh`; configure
  the instance `product_repo` path during onboarding before enabling it. The
  measured Bash inversion is opt-in via `MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1`;
  it is off by default so an unmeasured allowlist is never the default policy.
  With the flag on, Bash allows only command classes measured as read-only in
  the event log; unresolved targets and unmeasured commands are denied. If this is a multi-product
  workspace or the owner declines a primary product, leave the guard unwired
  until a real primary path is configured; otherwise its fail-closed behavior
  intentionally blocks all matching tool calls, including operations-repository
  paths that cannot be classified without a product root.
- PostToolUse: non-sensitive audit markers when locally approved
- SessionStart: tracker reachability from `{{WORKSPACE_ROOT}}`
- Shipped skills under `master-ops/skills/` (for example blame-agent) and the recommended methodology / restraint / tracker skill layers named in the stack table below

The host settings must merge the following `PreToolUse` fragment for both matchers,
alongside the SessionStart, UserPromptSubmit, and other hooks listed above. This is a
fragment, not a complete settings object; the exact host settings file remains
owner-managed:

```json
"PreToolUse": [
  {"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/product-path-guard.sh\""}]},
  {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/product-path-guard.sh\""}]}
]
```

Record in the ops notes that harness wiring is default-on as of this install. Do not edit host `settings.json` yourself when the host requires the owner to approve plugin installs — print the install commands and treat "printed and ready" as wired for onboarding purposes when the host blocks unattended writes.

### Agent notes — disable guidance (for the master later)

When the owner asks to turn something off, explain the piece in one sentence, state what behaviour changes, then apply the disable only after they confirm:

| piece | what it does | how to disable later |
| --- | --- | --- |
| Role-state injection (UserPromptSubmit) | Restates the active role and Proposal→Approval→Execution every turn | Remove or comment the UserPromptSubmit hook entry in the host settings that points at the role-state inject script; re-enable by restoring it |
| Compaction probe (SessionStart on compact) | Checks that the master still knows required facts after compaction | Remove the compact SessionStart hook that runs `scripts/compaction-probe.sh` |
| Dispatch / supervised-dispatch warning (PreToolUse) | Warns when a worker path bypasses the dispatch gate | Remove the PreToolUse warn hook for bare worker invocation |
| Product-path guard (PreToolUse) | Blocks master writes into product repositories; optionally enables measured fail-closed Bash decisions and records decisions in the event log | Remove the two PreToolUse hook entries for `scripts/hooks/product-path-guard.sh`; restore them to re-enable |
| Tracker reachability warning (SessionStart) | Warns when the issue tracker is not reachable from the workspace root | Remove the SessionStart tracker-check hook |
| Inbox / orch-inbox warn | Surfaces unread orchestration mailbox items | Remove the UserPromptSubmit hook for `orch-inbox-warn.sh` when present |
| Blame-agent skill | Structured incident observation skill | Uninstall or unload the skill from the host skill path; documents stay in `master-ops/skills/blame-agent/` |
| Methodology / restraint skill layers | How the master plans, verifies, and limits scope | Uninstall the host skill pack; charter remains readable as advice without them |
| Worker runtime plugin | In-session delegation to another CLI | `/plugin` uninstall (or host equivalent) for that worker plugin |

Never re-introduce per-item opt-out questions into this onboarding step. Disable is a post-install conversation with the master.

### Land host answers in the instance runtime config

`transcript_globs` is keyed by **runtime name** (agent CLI name such as `claude` or `codex`), not by machine or host nickname. The optional primary product path is `product_repo` in `{{RUNTIME_ROOT}}/config/instance-runtime.json`. For each runtime name the master or a worker probe will use — at minimum the current `master_host_runtime`, plus any other runtime the owner names for master sessions or that the preflight measured on `PATH` and expects to probe — ensure `transcript_globs.<runtime>` in `{{RUNTIME_ROOT}}/config/instance-runtime.json` is either measured on this machine or explicitly supplied. Prefer measurement: locate that runtime's session JSONL tree when the host exposes one; do not paste another workspace's encoded path. Keep `master_host_runtime` equal to the preflight agent CLI, and update the matching glob key if the owner explicitly changes it. Verify that the configured keys are the runtime names the probe will look up (including `master_host_runtime` itself).

When `--transcript` is omitted, consumers such as `{{RUNTIME_ROOT}}/scripts/model-identity-probe` resolve transcript location with environment override (`MOGUI_TRANSCRIPT_GLOB`) → this config file → unconfigured (exit 2 with an honest message). An explicit `--transcript` still wins over both. They must never fall back to a baked default glob.

### Verify (Step 7)

- shipped hooks and skills are treated as default-on; no per-item enable questions were asked
- the owner heard the single sentence that everything is on and any piece can be disabled later by asking the master
- the hook spec is documented, no sensitive implementation was added, and its owner is explicit or unresolved
- `config/instance-runtime.json` has a `transcript_globs` entry for `master_host_runtime` (and any other runtime names the owner expects to probe) when measurement or an explicit owner value exists; keys are runtime names, not host nicknames; missing globs are left unset rather than guessed

## Step 7.5. Skill layer (default-on shipped stack; print install commands)

**Position and action:** Step 7.5 begins before the master is born: explain the stack this install wires by default, print host install commands for pieces the template cannot embed, and stop.

**Why/caution:** Skills load into the founding session. Default-on means the recommended stack is on unless the owner later asks the master to disable a piece. Do not run a per-component shopping quiz during install.

Explain each component in one sentence. Print approved install commands and stop; do not run them or edit `settings.json`, hooks, or plugin configuration unless the owner already approved unattended host edits earlier in this session.

**Agent notes — five questions for any *new* component proposed after install** (not an install-time opt-in menu):

1. does it require an API key
2. does it force telemetry, or collect more than the job needs
3. does it add a management point
4. does it still work if the operation grows past one person
5. every tool claims to help with agent context. What else does this one actually resolve

A component that fails the first three is usually a subscription pretending to be a dependency. A component that passes them but answers nothing for the fifth is a preference, and should be labelled as one.

The stack this template was built against (default-on for this install), with what each one is for and what it is deliberately not used for:

| component | role here | not used for |
|---|---|---|
| Orca | execution substrate: worktrees, terminals, sessions, supervised dispatch | required infrastructure, not a swappable preference |
| tracker (Beads) | execution state that survives a session, as an issue graph | its memory is a short pointer cache toward Git, not the knowledge source of truth |
| `ctx` | trace archive: cross-provider session history, queryable when handoff, ledger, and Git do not answer | not part of routine boot context |
| `gitleaks` | matching engine for the publish gate | not the scope decision, which the wrapper keeps |
| methodology skills | how the master plans and verifies | without them the charter reads as advice rather than procedure |
| restraint skills | how much the master builds | pairs with the methodology layer rather than competing |
| review graph | impact radius and review context, locally parsed | optional; its value is token cost, not correctness |
| spec-driven framework | phase discipline from research through verification | installs lifecycle hooks; still default-on here — disable later via the master if unwanted |
| worker runtime plugin | lets the master delegate implementation from inside its own session | one wiring of the adapter layer, not a harness requirement |

Each host carries its own agent model and worker runtime plugin ecosystem. A worker runtime such as Codex is a first-class executor rather than a fallback. Expect the preference to split hard between the two camps; the contracts hold either way, which is the point of an agent-neutral template.

One asymmetry to plan around rather than discover: an agent without an interactive query interface cannot run the steps of this document that ask the user a question. Onboarding is a conversation. Run it from an agent that can ask, or supply every answer in the dispatch contract up front and record that the questions were answered in advance rather than asked.

Install commands for the Claude Code case, printed and not run (default-on intent: the owner is expected to run these unless they already have the worker plugin):

```console
$ /plugin marketplace add openai/codex-plugin-cc
$ /plugin install codex@openai-codex
$ /reload-plugins
$ /codex:setup
```

Name the load-bearing consequence of each layer in one sentence while presenting the table, not as a decline quiz:

- a methodology skill layer changes how the master plans and verifies; without it the master still runs, and reads the charter as advice rather than procedure
- a restraint skill layer keeps the master from over-building; without it, expect larger diffs and more speculative structure
- a tracker skill layer is what makes execution state survive a session; without it, state lives only in the transcript
- a worker runtime is what makes delegation possible at all; without at least one, the master does every task itself

If the owner spontaneously declines a default-on piece during this step, restate the specific behaviour that changes, confirm once, then record the decline with what is being accepted. Do not open with declines. Disable paths for later are in the Step 7 agent notes table.

### Verify (Step 7.5)

- the explanation preceded commands; the agent did not run a per-item opt-in menu; default-on intent is recorded
- nothing was installed or configured by the agent unless the owner already approved unattended host edits
- any spontaneous decline was re-confirmed once with its consequence restated and recorded

## Step 7.6. State what the publish gates do not cover

**Position and action:** Step 7.6 follows immediately, while the gates are fresh: tell the user what the redaction gates check and, more importantly, where they are silent.

**Why/caution:** A gate that is trusted beyond its scope is worse than no gate, because it converts an unchecked surface into a believed-clean one.

### Owner script (kind ELI5, adapt to the owner's language)

The gates read repository content. This is one of the places where the Herald must be especially plain: name the surfaces they do not read, so nobody assumes coverage that does not exist. Those surfaces are pull request titles, bodies, and review comments; release notes and issue text; anything typed into a forge web interface. None of those are in the repository, so no scanner in this template sees them — and they are where internal names most easily arrive, because they are written in prose rather than code. The habit that works is to grep your own outgoing text for organization identifiers before posting it, exactly as the scan does for files. Explain the gap once, in plain language, then continue.

Tell the user that organization-specific patterns live in a file outside version control, that the gates fail closed without it, and that its format is one rule per line as `id|description|regex`. That file is what makes the gates able to catch a workspace name; the shipped rules only catch generic provider secrets.

Do **not** run a comprehension quiz or ask the owner to recite a surface back. A quiz reads as condescension and adds no durable record.

### Verify (Step 7.6)

- the uncovered surfaces were named in conversation
- the organization rules file exists, or its absence is recorded as a known gap
- no quiz or "prove you understood" prompt was used
