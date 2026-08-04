# 01 — Pass The Required Preflight (Step 0)

Load rule: read this file only when Step 0 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `02-workspace-facts.md`.

**Position and action:** Step 0 starts after orientation, with no workspace state changed: run `bash scripts/onboarding-preflight.sh` from `{{RUNTIME_ROOT}}` and fix every FAIL before continuing.

**Why/caution:** Orca, an orchestration Run bound to this terminal, the Orca skills, Beads, Python, the named agent CLI, at least one worker runtime to dispatch to, Git, the GitHub CLI (`gh`), and the organization rules file are all required; do not offer a non-Orca fallback. Never suggest skipping the preflight itself: that discards every other check with it.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the Herald has explained the map, and nothing on the machine has been changed yet. What we decide next: whether this machine has the tools needed to raise the Master safely. Explain gently that these are read-only checks: we are looking at doors and keys, not moving furniture. Ask whether the owner is ready for local read-only checks, and which program they expect to use to run the Master (for example `claude`). If a check fails, say plainly that we fix it together before moving on; nothing is skipped silently, because a missing tool would make the later summoning look mysterious.

**Measured-fallback for the agent CLI:** if this installer session can measure its own runtime (process name, parent argv, or a host-exported selection such as `ORCA_AGENT_CLI`), that measurement is the recommended candidate and beats an empty ask. Still confirm with the owner when measurement and their expectation could diverge. Never invent a runtime name when nothing was measured.

## Run

Show the owner-facing form with `$` when you narrate the check; the agent may run the same lines without asking the owner to type them:

```console
$ cd "{{RUNTIME_ROOT}}"
$ ORCA_AGENT_CLI="<user-named agent CLI>" bash scripts/onboarding-preflight.sh
$ command -v "<user-named agent CLI>"
$ command -v git
```

Use `bash scripts/onboarding-preflight.sh --fix` only with approval; it may add or refresh the global Orca skills, while application installs remain manual.

## Land the agent CLI answer in the instance runtime config

After the agent CLI is confirmed, write it into the instance-owned runtime config so later scripts do not hardcode one installation's host. Copy the example once if the filled file is missing, then set `master_host_runtime` to the confirmed CLI name. Do not commit the filled file; the template ships only the example.

```console
$ cd "{{RUNTIME_ROOT}}"
$ test -f config/instance-runtime.json || cp config/instance-runtime.example.json config/instance-runtime.json
# set master_host_runtime to the confirmed agent CLI (JSON); leave other keys for later steps
```

Schema (one sentence each): `master_host_runtime` is the agent CLI the master runs on; `transcript_globs` maps each runtime name to a glob for that runtime's session transcripts used by the model probe; `product_repo` is the optional absolute path of the primary product repository. Resolution order for consumers: environment override → this file → honest unconfigured (never a baked guess).

## Agent-inventory consent and instance tier policy

The dispatch gate matches worker model strength to task weight and caps fan-out of expensive top-tier models. That only works when the tier file lists models this machine actually has. A hardcoded template list cannot ship as the live policy.

**Owner ask (warm ELI5, yes/no):** May I check which agent programs are installed on this machine, and which model names they advertise when a CLI exposes them? I use that list for two reasons only: to match each dispatched task to a strong-enough model instead of always picking the most expensive one, and to stop accidental fan-out of top-tier models. You can say no; then we fill the list with only the agents and models you name by hand, and any unknown model still gets the tight fan-out cap.

- **Consent yes:** measure every runtime candidate the preflight already knows on `PATH` (master host CLI plus worker runtimes). For each: record `runtime`, `version` from a measured `--version` / equivalent when available (else `unknown`), and `model_ids` only when the CLI advertises them (help text, a list subcommand, or a documented config the installer can read without guessing). Never invent a model id; unmeasurable fields are the string `unknown`. Place measured ids into `tiers.top` / `tiers.efficient` only when the CLI or owner clearly marks strength; otherwise leave the id out of named tiers so the gate treats it as `unknown` (capped). Write `consent: "yes"`.
- **Consent no:** do not probe. Ask the owner to name the runtimes and model ids they want listed; write only those entries; set `consent: "no"`. Empty `tiers` lists are valid — unlisted models still use `fanout_caps.unknown`.
- Copy the example once if missing, then write the instance file (never commit the filled copy):

```console
$ cd "{{RUNTIME_ROOT}}"
$ test -f config/model-tier-policy.json || cp config/model-tier-policy.example.json config/model-tier-policy.json
# fill version 2 shape: agents[], tiers, fanout_caps (unknown required), window_seconds, consent
```

Schema (gate-consumed fields): `version` must be `2`; `tiers` maps tier name to model-id lists; `fanout_caps` must include `unknown`; `window_seconds` is the rolling window. Extra keys (`agents`, `consent`, `_docs`) are documentation for the install and are ignored by the gate parser. Resolution for the gate: environment `DISPATCH_TIER_POLICY` → `config/model-tier-policy.json` when present → template `master-ops/model-tier-policy.json`.

## Verify

- the preflight exits zero, Orca status was measured, a non-legacy orchestration Run is bound to this terminal, required skills resolve, `bd` is present and resolves to the ops repo when one exists, and Python is present
- the named agent CLI is set and resolves on `PATH`; an unset selection is a FAIL, because it silently downgrades the agent-specific checks to INFO
- `{{RUNTIME_ROOT}}/config/instance-runtime.json` exists (instance-owned, not committed) with `master_host_runtime` equal to the confirmed agent CLI; the template example was not replaced in git
- the agent-inventory consent question was asked with both purposes stated; `config/model-tier-policy.json` exists (instance-owned, not committed) with `version: 2`, `fanout_caps.unknown`, and either measured `agents`/`tiers` (consent yes) or only owner-named entries (consent no); no model id was guessed; the template example was not replaced in git
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
