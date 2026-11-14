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
- SessionStart on compact: `{{OPS_REPO}}/scripts/compaction-probe.sh`
- PreCompact: reload or export tracker memory
- UserPromptSubmit: role-state line + `Proposal -> Approval -> Execution` (see charter §8 / §9)
- PostToolUse (all tools) and UserPromptSubmit: `{{OPS_REPO}}/scripts/hooks/compact-rehydration-hook.sh` restores the work layer once the compact recall record is present, or after the bounded recall wait
- UserPromptSubmit: dispatch tracker-card gap warning (`{{OPS_REPO}}/scripts/hooks/bd-gap-warn.sh`) alongside the orchestration inbox warning
- PreToolUse: supervised-dispatch bypass warning
- PreToolUse: `{{OPS_REPO}}/scripts/hooks/bash-poll-warn.sh` runs before a polling command
- PreToolUse: `{{OPS_REPO}}/scripts/hooks/bash-bare-cd-warn.sh` reports bare `cd` commands
- PreToolUse: `{{OPS_REPO}}/scripts/hooks/bash-output-trim-warn.sh` reports unbounded large-output commands
- UserPromptSubmit: `{{OPS_REPO}}/scripts/hooks/worker-block-warn.sh` reports panes waiting for coordinator action
- PostToolUse: `{{OPS_REPO}}/scripts/hooks/bash-output-size-warn.sh` runs when tool output exceeds the inline budget
- PreToolUse(Edit|Write|NotebookEdit) and PreToolUse(Bash): fail closed for
  product-repository writes with `{{OPS_REPO}}/scripts/hooks/product-path-guard.sh`; configure
  the instance `product_repositories` array (or the one-entry `product_repo`
  string) during onboarding before enabling it. The measured Bash inversion is
  opt-in via `MOGUI_PRODUCT_GUARD_FAIL_CLOSED=1`; it is off by default so an
  unmeasured allowlist is never the default policy. With the flag on, Bash
  allows only command classes measured as read-only in the event log when they
  target territory under any listed product repository; unresolved targets
  and unmeasured product-targeting commands are denied. If the owner declines
  naming any product repository, leave the guard unwired until at least one
  real path is configured; otherwise its fail-closed behavior intentionally
  blocks all matching tool calls, including operations-repository paths that
  cannot be classified without a product root.
- PostToolUse: non-sensitive audit markers when locally approved
- SessionStart: tracker reachability from `{{WORKSPACE_ROOT}}`
- Shipped skills under `master-ops/skills/` (for example blame-agent) and the recommended methodology / restraint / tracker skill layers named in the stack table below

The host settings must merge the following hook fragment alongside the SessionStart,
UserPromptSubmit, and other hooks listed above. Every command names the installed
script through the rendered operations-repository path, so a hook keeps resolving
from a worker worktree. This is a fragment, not a complete settings object; the
exact host settings file remains owner-managed:

This fragment has no shipped-hook exclusions: every `master-ops/scripts/hooks/*.sh`
script appears below or in the compact rehydration block that follows.

```json
"env": {
  "MOGUI_OPS_REPO": "{{OPS_REPO}}"
},
"bashOutputMaxChars": 6000,
"hooks": {
  "SessionStart": [
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/role-state-inject.sh\" SessionStart"}]},
    {"matcher": "compact", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/compaction-probe.sh\""}]},
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/tracker-check.sh\""}]}
  ],
  "PreToolUse": [
    {"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/product-path-guard.sh\""}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/product-path-guard.sh\""}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/bash-poll-warn.sh\""}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/bash-bare-cd-warn.sh\""}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/bash-output-trim-warn.sh\""}]}
  ],
  "UserPromptSubmit": [
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/role-state-inject.sh\""}]},
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/orch-inbox-warn.sh\""}]},
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/bd-gap-warn.sh\""}]},
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/worker-block-warn.sh\""}]}
  ],
  "PostToolUse": [
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/bash-output-size-warn.sh\""}]}
  ]
}
```

Merge the `MOGUI_OPS_REPO` entry into the host settings' existing `env` object,
preserving unrelated entries. This persistent setting reaches fresh master
sessions and their tools, including `master-succeed`, `model-identity-probe`,
and the product-path hooks. Codex workers do not need this variable: `dispatch`
exports `INSTANCE_RUNTIME_CONFIG` itself when it launches them.

Register the compact rehydration hook in the existing `hooks` object. Append the
PostToolUse entry to its event array and merge the UserPromptSubmit entry with
the existing UserPromptSubmit array. An empty PostToolUse matcher covers every
tool, while the UserPromptSubmit entry handles a turn that ends immediately
after the recall append:

```json
"hooks": {
  "PostToolUse": [
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/compact-rehydration-hook.sh\""}]}
  ],
  "UserPromptSubmit": [
    {"matcher": "", "hooks": [{"type": "command", "command": "bash \"{{OPS_REPO}}/scripts/hooks/compact-rehydration-hook.sh\""}]}
  ]
}
```

The optional `work_layer_extra_lines` array in the instance runtime config
declares seat-specific lines. Entries may be strings, `{ "label": "...",
"value": "..." }`, or `{ "label": "...", "path": "..." }` for a JSON
array/object count; the hook keeps these lines after the ops-repository status
count and treats unreadable entries as unavailable.

Place `bashOutputMaxChars` in the master's workspace-level project file `.claude/settings.json`; the user-wide `~/.claude/settings.json` reaches every project. Tool output is the largest context cost of a long master session. Claude Code v2.1.261 or later applies this setting to successful Bash or PowerShell commands: above 6000 characters, it saves the result to a session file and sends the model a short preview plus the file path; an oversized failed command receives a head-and-tail excerpt instead. The dispatch script starts each worker with a separate per-task `--settings` file containing only worker guard hooks, so workers do not receive the master's cap.

Record in the ops notes that harness wiring is default-on as of this install. Reuse the dependency-set approval from Step 0; if it was not asked there, ask it once here and name the `ctx` local history indexing side effect before running `--fix`. Ask a separate host-edit approval before changing host `settings.json`, hooks, or plugin configuration. If host-edit approval is declined, print the commands, record that wiring as pending, and continue only where unconfigured execution is allowed.

### Antigravity folder trust and contract command approvals

When `agy` is a worker runtime, run `{{RUNTIME_ROOT}}/scripts/agy-worker-pretrust <absolute-existing-worktree-path>` immediately before its launch. By default, the wrapper writes `~/.gemini/antigravity-cli/settings.json`; `AGY_SETTINGS_PATH` overrides the complete settings file, and `AGY_CONFIG_HOME` overrides the `.gemini` directory. It strips one trailing slash, refuses literal root and home paths, nonexistent paths, dot components, and glob characters, then writes one exact path under `trustedWorkspaces`; it preserves the other settings, never writes a wildcard, and prints a `Summary:` line. It keeps the path as typed and does not canonicalize symlink or repeated-slash equivalents. The measured first-run sequence on 2026-11-13 showed the `Do you trust the contents of this project?` screen before the CLI input screen; after selecting `Yes, I trust this folder`, the before/after diff added one array entry under `trustedWorkspaces` in that settings file, while `~/.gemini/trustedFolders.json` was unchanged.

The same host-edit approval covers agy's contract command allowlist. Merge these entries into the existing `permissions.allow` array and preserve unrelated entries:

```json
{
  "permissions": {
    "allow": [
      "command(git add)",
      "command(git commit)",
      "command(git push)",
      "command(gh pr create)",
      "command(gh pr view)",
      "command(orca orchestration ask)",
      "command(orca orchestration send)",
      "command(orca orchestration worker-start)",
      "command(orca orchestration reply)",
      "command(orca orchestration check)",
      "command(PYTHONPATH=src python3 -m pytest tests -q)"
    ]
  }
}
```

The `permissions.allow` key and `command(...)` entries were observed in agy 1.5.8's own settings file. This general template covers commands used by every worker contract; targeted shell regression scripts remain repository test commands rather than general worker approvals. A host may add an exact repository-specific test command when its checkout uses a different interpreter or test runner. The measured syntax does not establish a narrower remote/ref rule for `git push`, so force-push variants remain an explicit operator decision until that syntax is measured.

### Agent notes — disable guidance (for the master later)

When the owner asks to turn something off, explain the piece in one sentence, state what behaviour changes, then apply the disable only after they confirm:

| piece | what it does | how to disable later |
| --- | --- | --- |
| Role-state injection (UserPromptSubmit) | Restates the active role and Proposal→Approval→Execution every turn | Remove or comment the UserPromptSubmit hook entry in the host settings that points at the role-state inject script; re-enable by restoring it |
| Compaction probe (SessionStart on compact) | Checks that the master still knows required facts after compaction | Remove the compact SessionStart hook that runs `{{OPS_REPO}}/scripts/compaction-probe.sh` |
| Compact rehydration (PostToolUse and UserPromptSubmit) | Restores tracker work after the recall measurement is recorded or bounded | Remove the two hook entries for `{{OPS_REPO}}/scripts/hooks/compact-rehydration-hook.sh`; restore them to re-enable |
| Dispatch / supervised-dispatch warning (PreToolUse) | Warns when a worker path bypasses the dispatch gate | Remove the PreToolUse warn hook for bare worker invocation |
| Product-path guard (PreToolUse) | Blocks master writes into product repositories; optionally enables measured fail-closed Bash decisions and records decisions in the event log | Remove the two PreToolUse hook entries for `{{OPS_REPO}}/scripts/hooks/product-path-guard.sh`; restore them to re-enable |
| Bash poll hook (PreToolUse) | Runs before a polling command so bounded foreground checks remain visible | Remove the PreToolUse hook entry for `{{OPS_REPO}}/scripts/hooks/bash-poll-warn.sh`; restore it to re-enable |
| Bash bare-cd hook (PreToolUse) | Reports bare `cd` commands whose shell state can persist between calls | Remove the PreToolUse hook entry for `{{OPS_REPO}}/scripts/hooks/bash-bare-cd-warn.sh`; restore it to re-enable |
| Bash output-trim hook (PreToolUse) | Reports large-output commands without a bounded filter | Remove the PreToolUse hook entry for `{{OPS_REPO}}/scripts/hooks/bash-output-trim-warn.sh`; restore it to re-enable |
| Worker-block hook (UserPromptSubmit) | Reports panes waiting for coordinator action | Remove the UserPromptSubmit hook entry for `{{OPS_REPO}}/scripts/hooks/worker-block-warn.sh`; restore it to re-enable |
| Bash output-size hook (PostToolUse) | Runs when a tool result exceeds the inline output budget | Remove the PostToolUse hook entry for `{{OPS_REPO}}/scripts/hooks/bash-output-size-warn.sh`; restore it to re-enable |
| Bash output cap | Limits successful Bash or PowerShell output shown inline for the master | Remove `bashOutputMaxChars` from the master's workspace `.claude/settings.json` and start a fresh session; use `.claude/settings.local.json` for a temporary project-local value |
| Tracker reachability warning (SessionStart) | Warns when the issue tracker is not reachable from the workspace root | Remove the SessionStart tracker-check hook |
| Inbox / orch-inbox warn | Surfaces unread orchestration mailbox items | Remove the UserPromptSubmit hook for `orch-inbox-warn.sh` when present |
| Dispatch card gap warning | Surfaces today's registered dispatches without a tracker card | Remove the UserPromptSubmit hook for `bd-gap-warn.sh` when present |
| Blame-agent skill | Structured incident observation skill | Uninstall or unload the skill from the host skill path; documents stay in `master-ops/skills/blame-agent/` |
| Methodology / restraint skill layers | How the master plans, verifies, and limits scope | Uninstall the host skill pack; charter remains readable as advice without them |
| Worker runtime plugin | In-session delegation to another CLI | `/plugin` uninstall (or host equivalent) for that worker plugin |

Never re-introduce per-item opt-out questions into this onboarding step. Disable is a post-install conversation with the master.

### Land host answers in the instance runtime config

`transcript_globs` is keyed by **runtime name** (agent CLI name such as `claude` or `codex`), not by machine or host nickname. The optional product repositories are the array `product_repositories` (or the one-entry string `product_repo`) in `{{OPS_REPO}}/config/instance-runtime.json`. For each runtime name the master or a worker probe will use — at minimum the current `master_host_runtime`, plus any other runtime the owner names for master sessions or that the preflight measured on `PATH` and expects to probe — ensure `transcript_globs.<runtime>` in `{{OPS_REPO}}/config/instance-runtime.json` is either measured on this machine or explicitly supplied. Prefer measurement: locate that runtime's session JSONL tree when the host exposes one; do not paste another workspace's encoded path. Keep `master_host_runtime` equal to the preflight agent CLI, and update the matching glob key if the owner explicitly changes it. Verify that the configured keys are the runtime names the probe will look up (including `master_host_runtime` itself).

When `--transcript` is omitted, consumers such as `{{RUNTIME_ROOT}}/scripts/model-identity-probe` resolve transcript location with environment override (`MOGUI_TRANSCRIPT_GLOB`) → this config file → unconfigured (exit 2 with an honest message). An explicit `--transcript` still wins over both. They must never fall back to a baked default glob.

### Verify (Step 7)

- shipped hooks and skills are treated as default-on; no per-item enable questions were asked
- the owner heard the single sentence that everything is on and any piece can be disabled later by asking the master
- the hook spec is documented, no sensitive implementation was added, and its owner is explicit or unresolved
- `{{OPS_REPO}}/config/instance-runtime.json` has a `transcript_globs` entry for `master_host_runtime` (and any other runtime names the owner expects to probe) when measurement or an explicit owner value exists; keys are runtime names, not host nicknames; missing globs are left unset rather than guessed

## Step 7.5. Skill layer (default-on shipped stack; single approval)

**Position and action:** Step 7.5 begins before the master is born: explain the stack this install wires by default, reuse the Step 0 dependency-set approval when it exists, then either install the approved set or print the commands for manual execution. Host settings, hooks, and plugin configuration use a separate host-edit approval.

**Why/caution:** Skills load into the founding session. Default-on means the recommended stack is on unless the owner later asks the master to disable a piece. Do not run a per-component shopping quiz during install.

Explain each component in one sentence. The dependency approval question is for the tool set as a whole: using this harness means using the tools it runs on, the way a package manager installs a dependency tree. If the owner approves, run only the known-good install commands and re-measure each dependency after installation instead of trusting the installer exit code. If the owner declines, print the commands and continue only where the resulting consequences allow. Ask separately before editing `settings.json`, hooks, or plugin configuration; if that host-edit approval is declined, print the commands, record wiring as pending, and continue only where unconfigured execution is allowed.

**Agent notes — five questions for any *new* component proposed after install** (not an install-time opt-in menu):

1. does it require an API key
2. does it force telemetry, or collect more than the job needs
3. does it add a management point
4. does it still work if the operation grows past one person
5. every tool claims to help with agent context. What else does this one actually resolve

A component that fails the first three is usually a subscription pretending to be a dependency. A component that passes them but answers nothing for the fifth is a preference, and should be labelled as one.

The stack this template was built against (default-on for this install), with what each one is for, its install surface, and what changes if the owner declines:

| component | role here | install surface | consequence of declining |
|---|---|---|---|
| Orca | execution substrate: worktrees, terminals, sessions, supervised dispatch | macOS Homebrew cask: `brew install --cask stablyai/orca/orca`; other hosts use the official desktop installer | onboarding cannot proceed as the documented live orchestration flow |
| tracker (Beads) | execution state that survives a session, as an issue graph | no known-good installer is embedded here; install the `bd` CLI and create or sync the local `.beads` database before onboarding | onboarding blocks until `bd` resolves in the ops repository; there is no degraded master path for a missing tracker |
| `ctx` | cross-provider agent history in one local queryable index, including prior session text, decisions, commands, and summaries | `curl -fsSL https://ctx.rs/install \| CTX_INSTALL_NO_MODIFY_PATH=1 sh`; setup creates or updates the local history index; semantic search may add roughly 90MB later if enabled | the master cannot query cross-provider history; this workspace has repeatedly missed indexed decisions without a reachable index |
| `gitleaks` | matching engine for publish-time redaction gates | macOS/Linux Homebrew formula: `brew install gitleaks`; other hosts use an official package or release binary | publishing is blocked by the redaction wrappers, but running a master that never publishes is not blocked |
| methodology skills | how the master plans and verifies | host skill pack or plugin install for the selected agent | without them the charter reads as advice rather than procedure |
| restraint skills | how much the master builds | host skill pack or plugin install for the selected agent | expect larger diffs and more speculative structure |
| review graph | impact radius and review context, locally parsed | local parser/index tooling when installed | reviews use direct file reading without the token-saving graph |
| spec-driven framework | phase discipline from research through verification | host plugin install; it may install lifecycle hooks | phase discipline is manual, and its lifecycle hooks are absent |
| worker runtime plugin | lets the master delegate implementation from inside its own session | selected agent's plugin install command | the master can still run, but delegation through that adapter is unavailable |

Each host carries its own agent model and worker runtime plugin ecosystem. A worker runtime such as Codex is a first-class executor rather than a fallback. Expect the preference to split hard between the two camps; the contracts hold either way, which is the point of an agent-neutral template.

One asymmetry to plan around rather than discover: an agent without an interactive query interface cannot run the steps of this document that ask the user a question. Onboarding is a conversation. Run it from an agent that can ask, or supply every answer in the dispatch contract up front and record that the questions were answered in advance rather than asked.

Known dependency install commands may be run only after dependency-install approval, and only on hosts where the named package manager or installer applies. Host plugin, settings, and hook commands require the separate host-edit approval; without it, print those commands and record the wiring as pending:

```console
# macOS with Homebrew
$ brew install --cask stablyai/orca/orca
$ brew install gitleaks

# Unix ctx installer
$ curl -fsSL https://ctx.rs/install | CTX_INSTALL_NO_MODIFY_PATH=1 sh

# Claude Code plugin host-edit flow
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
- without a reachable `ctx` index, the master cannot query cross-provider history, and earlier generations of this workspace have reported an indexed decision as absent
- without `gitleaks`, publish-time redaction wrappers cannot decide; this does not block a master that never publishes

If the owner spontaneously declines a default-on piece during this step, restate the specific behaviour that changes, confirm once, then record the decline with what is being accepted. Do not open with declines. Disable paths for later are in the Step 7 agent notes table.

### Verify (Step 7.5)

- the explanation preceded commands; the agent asked once for the dependency set rather than running a per-item opt-in menu; default-on intent is recorded
- every command that was run had a known install command and was re-measured afterward; commands that could not be run are named as unverified
- nothing was installed unless the owner approved dependency installation, and no host settings, hooks, or plugin configuration were changed unless the owner separately approved host edits
- declined host edits were printed as commands and recorded as pending wiring, not treated as configured
- dependency rows without a known install command are recorded as prerequisites or unverified work, not as completed by `--fix`
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
