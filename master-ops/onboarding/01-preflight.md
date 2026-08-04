# 01 — Pass The Required Preflight (Step 0)

Load rule: read this file only when Step 0 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `02-workspace-facts.md`.

**Position and action:** Step 0 starts after orientation, with no workspace state changed: run `bash scripts/onboarding-preflight.sh` from `{{RUNTIME_ROOT}}` and fix every FAIL before continuing.

**Why/caution:** Orca, an orchestration Run bound to this terminal, the Orca skills, Beads, Python, the named agent CLI, at least one worker runtime to dispatch to, Git, the GitHub CLI (`gh`), and the organization rules file are all required; do not offer a non-Orca fallback. Never suggest skipping the preflight itself: that discards every other check with it.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the Herald has explained the map, and nothing on the machine has been changed yet. What we decide next: whether this machine has the tools needed to raise the Master safely. Explain gently that these are read-only checks: we are looking at doors and keys, not moving furniture. Ask whether the owner is ready for local read-only checks, and which agent CLI they expect to use (for example `claude`). If a check fails, say plainly that we fix it together before moving on; nothing is skipped silently, because a missing tool would make the later summoning look mysterious.

## Run

Show the owner-facing form with `$` when you narrate the check; the agent may run the same lines without asking the owner to type them:

```console
$ cd "{{RUNTIME_ROOT}}"
$ ORCA_AGENT_CLI="<user-named agent CLI>" bash scripts/onboarding-preflight.sh
$ command -v "<user-named agent CLI>"
$ command -v git
```

Use `bash scripts/onboarding-preflight.sh --fix` only with approval; it may add or refresh the global Orca skills, while application installs remain manual.

## Verify

- the preflight exits zero, Orca status was measured, a non-legacy orchestration Run is bound to this terminal, required skills resolve, `bd` is present and resolves to the ops repo when one exists, and Python is present
- the named agent CLI is set and resolves on `PATH`; an unset selection is a FAIL, because it silently downgrades the agent-specific checks to INFO
- at least one of the worker runtimes this master dispatches to resolves on `PATH`; the others are reported as warnings, since routing every lane through one executor is a normal setup
- `gitleaks` was measured: present passes, absent warns without blocking, because publishing needs it (the redaction gate exits 2 without its engine) while running a master does not. Treat the warning as a real install item on any host that will publish
- `ctx` was measured: present with a reachable index passes, absent or unreachable warns without blocking, because the records practice cannot query cross-provider history without it while a master still runs. Ignore the warning only on a host that does no history work
- Git is present, and `gh` state was reported: a missing binary blocks, while unauthenticated or a missing `workflow` scope warns, because local-only work needs no forge credentials
- every waiver in the summary was intended, and `PREFLIGHT_WAIVE` entries that matched no check are corrected rather than left, since a misspelled waiver leaves the check enforced
- the organization rules file loads at least one rule and no rule is malformed; the preflight reports counts only and never the file's contents

## If fail

- A host that legitimately cannot satisfy one required check sets `PREFLIGHT_WAIVE=<check-label>`, which downgrades that FAIL to a printed and counted waiver; the summary then reads READY WITH WAIVERS and names them, because a required check that was waived was not satisfied.
- Orchestration is measured by capability rather than reachability. Two states measured on real hosts: a retained legacy coordinator answers reads and drops writes with `effectsApplied:false`, and an unbound coordinator fails the whole task family with `run_required`. A binding can also drop later without any signal, after which `check` returns `count:0`, so an empty mailbox and a missing binding look identical. If the preflight reports either state, bind a fresh Run with `orca orchestration run-create` and measure again; restarting the app does not clear the legacy one.
- Do not attribute a lost injection to binding state without a control: a lost task and a delivered task inside the same Run were measured on 2026-08-02, which rules binding out as that discriminator.
