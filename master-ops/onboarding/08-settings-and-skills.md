# 08 — Settings Layer, Skill Layer, Gate Scope (Steps 7, 7.5, 7.6)

Load rule: read this file only when Step 7 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `09-spawn.md`.

## Step 7. Explain the settings layer

**Position and action:** Step 7 begins with durable user rules seeded: identify the host and the owner of settings and sensitive configuration.

**Why/caution:** The template specifies hook behavior but does not ship hidden deny lists, credentials, secret paths, or environment-specific security implementation.

### Owner script (kind ELI5, adapt to the owner's language)

Where we are: the Master's ground rules are saved, and the Herald now checks which host-side safeguards should be prepared before the Master rises. What we decide next: who owns the host settings and security-sensitive configuration, and which safety hooks to turn on. Explain ELI5 that hooks are small host-side reminders or checks that help the Master wake with the right state. Ask which hosts run the Master, who owns hooks/security-sensitive configuration, and whether dispatch warning, role-state injection, and compaction probe hooks should be enabled. Present the hook wiring spec from `docs/MASTER-OPERATIONS.md` in agent notes, not as a wall of text at the owner; delegate auth, permission, secrets, credentials, and production-data work to a dedicated security/operations session.

### Land host answers in the instance runtime config

`transcript_globs` is keyed by **runtime name** (agent CLI name such as `claude` or `codex`), not by machine or host nickname. For each runtime name the master or a worker probe will use — at minimum the current `master_host_runtime`, plus any other runtime the owner names for master sessions or that the preflight measured on `PATH` and expects to probe — ensure `transcript_globs.<runtime>` in `{{RUNTIME_ROOT}}/config/instance-runtime.json` is either measured on this machine or explicitly supplied. Prefer measurement: locate that runtime's session JSONL tree when the host exposes one; do not paste another workspace's encoded path. Keep `master_host_runtime` equal to the preflight agent CLI, and update the matching glob key if the owner explicitly changes it. Verify that the configured keys are the runtime names the probe will look up (including `master_host_runtime` itself).

When `--transcript` is omitted, consumers such as `{{RUNTIME_ROOT}}/scripts/model-identity-probe` resolve transcript location with environment override (`MOGUI_TRANSCRIPT_GLOB`) → this config file → unconfigured (exit 2 with an honest message). An explicit `--transcript` still wins over both. They must never fall back to a baked default glob.

### Verify (Step 7)

- the hook spec is documented, no sensitive implementation was added, and its owner is explicit or unresolved
- `config/instance-runtime.json` has a `transcript_globs` entry for `master_host_runtime` (and any other runtime names the owner expects to probe) when measurement or an explicit owner value exists; keys are runtime names, not host nicknames; missing globs are left unset rather than guessed

## Step 7.5. Offer the skill layer

**Position and action:** Step 7.5 begins before the master is born: explain the optional stack in README, then ask which parts the user wants.

**Why/caution:** Skills load into the founding session; some installers, especially GSD, modify lifecycle hooks and require deliberate user choice.

Explain each component in one sentence before showing any command. Print approved install commands and stop; do not run them or edit `settings.json`, hooks, or plugin configuration.

These five questions decided what is in the stack, and they are worth repeating when a component is proposed later:

1. does it require an API key
2. does it force telemetry, or collect more than the job needs
3. does it add a management point
4. does it still work if the operation grows past one person
5. every tool claims to help with agent context. What else does this one actually resolve

A component that fails the first three is usually a subscription pretending to be a dependency. A component that passes them but answers nothing for the fifth is a preference, and should be labelled as one.

The stack this template was built against, with what each one is for and what it is deliberately not used for. Name the role before the install command, because a tool adopted without its boundary becomes the next thing to unwind:

| component | role here | not used for |
|---|---|---|
| Orca | execution substrate: worktrees, terminals, sessions, supervised dispatch | required infrastructure, not a swappable preference |
| tracker (Beads) | execution state that survives a session, as an issue graph | its memory is a short pointer cache toward Git, not the knowledge source of truth |
| `ctx` | trace archive: cross-provider session history, queryable when handoff, ledger, and Git do not answer | not part of routine boot context |
| `gitleaks` | matching engine for the publish gate | not the scope decision, which the wrapper keeps |
| methodology skills | how the master plans and verifies | without them the charter reads as advice rather than procedure |
| restraint skills | how much the master builds | pairs with the methodology layer rather than competing |
| review graph | impact radius and review context, locally parsed | optional; its value is token cost, not correctness |
| spec-driven framework | phase discipline from research through verification | installs lifecycle hooks, so it needs a deliberate yes |
| worker runtime plugin | lets the master delegate implementation from inside its own session | one wiring of the adapter layer, not a harness requirement |

Each host carries its own agent model and worker runtime plugin ecosystem. A worker runtime such as Codex is a first-class executor rather than a fallback. Expect the preference to split hard between the two camps; the contracts hold either way, which is the point of an agent-neutral template.

One asymmetry to plan around rather than discover: an agent without an interactive query interface cannot run the steps of this document that ask the user a question. Onboarding is a conversation. Run it from an agent that can ask, or supply every answer in the dispatch contract up front and record that the questions were answered in advance rather than asked.

Install commands for the Claude Code case, printed and not run:

```console
$ /plugin marketplace add openai/codex-plugin-cc
$ /plugin install codex@openai-codex
$ /reload-plugins
$ /codex:setup
```

Say which of them are optional in name only. The template carries documents and scripts; it cannot carry the host layer that makes a master behave the way the documents describe, so a component listed here as recommended is often load-bearing. State the consequence of declining each one in a sentence, in the same breath as the offer, rather than leaving the user to discover it later:

- a methodology skill layer changes how the master plans and verifies; without it the master still runs, and reads the charter as advice rather than procedure
- a restraint skill layer keeps the master from over-building; without it, expect larger diffs and more speculative structure. It pairs with the methodology layer rather than competing with it: one decides how to approach work, the other decides how much to build
- a tracker skill layer is what makes execution state survive a session; without it, state lives only in the transcript
- a worker runtime is what makes delegation possible at all; without at least one, the master does every task itself

When the user declines a component the preflight treats as essential, ask once more. Not as a nag: restate the specific behaviour that changes, then ask whether to proceed without it. One re-ask, then take the answer as final.

The reason to ask twice is that the first no is usually answering a different question. A component list reads as preferences, so the first pass is "do I want this", while the question that matters is "am I accepting this behaviour". Restating the consequence is what turns one into the other.

Record the confirmed decline together with what is being accepted, in the user's own terms where possible. A declined component is a fact about the installation, and later behaviour that looks like a master defect is often a declined component instead.

Where the agent running onboarding has no interactive query interface, the re-ask cannot happen at all. In that case the dispatch contract carries the confirmed declines up front, and the record says they were confirmed in advance rather than asked.

### Verify (Step 7.5)

- the explanation preceded commands, nothing was installed or configured by the agent, every essential decline was re-asked once with its consequence restated, and the user's choice, including no installation, is recorded with what it accepts

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
