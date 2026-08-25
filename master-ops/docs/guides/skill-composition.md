# Skill Composition Guide

This guide documents the skill composition this workspace has adopted and why it is ordered the way it is.
All claims below are tied to direct measurements taken on 2026-08-25 or to existing instruction text in this repository.
If a point could not be measured from this checkout, it is labeled `unmeasured`.

## Measurement Baseline

- Worktree check (contract-required first action): `pwd` returned (tilde-normalized) `~/dev/personal/mogui/mogui-ADE-orchestrator/.orca/worktrees/docs-skill-composition`, and `git branch --show-current` returned `baksohyeon/docs-skill-composition`.
- Host skill source 1: `ls ~/.claude/skills | wc -l` => `280` entries.
- Host skill source 1 representative names: `orchestration`, `blame-agent`, many `gsd-*` entries (for example `gsd-debug`, `gsd-plan-phase`, `gsd-verify-work`).
- Host skill source 2 (superpowers plugin cache): `~/.claude/plugins/cache/claude-plugins-official/superpowers/` has `3` cached builds (`6.2.0`, `6.3.0`, `b36e0829c6d0`), and each build exposes `14` skills under `skills/`.
- Superpowers representative names from cache: `brainstorming`, `writing-plans`, `executing-plans`, `systematic-debugging`, `verification-before-completion`, `using-superpowers`.
- Workspace discovery path measured from `scripts/harness-selfcheck.sh`: `SKILLS_DISCOVERY_PATH="$WORKSPACE_ROOT/.claude/skills"`.
- Workspace discovery path contents (measured): `ls ~/dev/personal/mogui/.claude/skills` => `2` entries (`anti-slop`, `blame-agent`).
- Workspace `.claude/settings.json` contains hook wiring and no explicit skill-source field; skill-source override in settings is `unmeasured`.
- Template-shipped ops skills measured from this repository: `ls skills | wc -l` => `1`, and the entry is `blame-agent`.

## What Each Layer Contributes

Process skills decide how work proceeds before implementation starts. In this composition, they force sequence and discipline: brainstorm before designing, design before execution, debug by evidence before fix proposals, and verify before claiming completion; these controls reduce fast-but-wrong execution.

Restraint (ponytail) decides how much to build while work is in progress. The ladder is: does this need to exist, is it already present, does the platform already solve it, can it be one line, and only then build; this counters over-building pressure.

Domain and operations skills provide workspace-specific execution behavior once process and restraint have set direction. In this workspace, those include the observability genres the owner runs as separate artifacts (blame, retro, travelog, journal) and local ops routines such as dispatch and stewardship.

## The Composition Rule

Process skills come first and set the approach, restraint stays active throughout, and implementation/domain skills carry out the resulting plan.
The measured failure this prevents is a master that reaches for tooling before deciding the approach, which builds the wrong thing efficiently.
These two layers pull in opposite directions on purpose, and the ordering rule is what makes that tension productive.

## Where It Lands In This Template

The routing table below is adapted from `workspace-card/CLAUDE.md` (identical in `workspace-card/AGENTS.md`):

> When a request matches a row, invoke the skill FIRST - before answering, exploring, or editing.
>
> - New feature, design change, or improvement request -> `superpowers:brainstorming`, then a worker contract.
> - Bug, unexpected behavior, or "why is this broken" -> `superpowers:systematic-debugging` before proposing any fix.
> - Any dispatch, worker, or multi-agent coordination -> `orchestration` skill; vendor-direct CLIs are never a dispatch path.
> - Review-bot threads on PRs -> dispatched fix worker per charter section 4 (`docs/charter/04-worker-routing-review.md`); reply style is `docs/runbooks/review-voice.md`.
> - Session observability (journey notes, field notes, retros) -> skills under `skills/` when present; judgment retros and generation logs go to the genres in `docs/observability/`.
> - Shipping product changes -> repo gate conventions, PR flow, squash merge only after zero unresolved review threads.

## What Is Not Shipped

The template ships only its own ops skill(s): measured in this checkout as `skills/blame-agent`.
The process stack (`superpowers:*`) and restraint layer (`ponytail`) are host-level installs added by the operator, sourced from host skill stores like `~/.claude/skills` and plugin caches like `~/.claude/plugins/cache/claude-plugins-official/superpowers/<build>/skills/`.
An installation without these host-level layers still runs the template mechanics (hooks, gates, dispatch), but it loses this composition behavior.

## Adoption Notes From Workspace History

From the 2026-08-24 contract addendum measurements (`unmeasured` in this checkout; reported at `dionz-ops/docs/reference/blog-claims-ledger.md` commit `3c9f133`): the file records five single-tool adoption criteria and explicitly states that fame/first impression were not criteria; `ponytail` appears zero times there.
Observed implication: those five criteria evaluate tools one at a time and do not expose combination utility, so this workspace added a practical sixth question: what one adopted tool covers that another adopted tool fails at.
This is documented as an observation from this workspace's adoption history, not a ratified universal rule.

## Attribution

This composition is the workspace owner's assembly, documented here as adopted practice.
