If a session opens in a fresh clone with no task given, you are this system's onboarding guide: say what it is in three sentences, then walk the user through `master-ops/ONBOARDING.md`. If you arrive with an explicit task (a contract, an issue, a fix request), that takes priority and you do not start onboarding.

# mogui-ADE-orchestrator Agent Entry Point

This repository contains the workspace/orchestrator runtime and the Stage 2 master-ops onboarding guide. Keep agent-host wording neutral: `claude` is an example CLI, and `AGENTS.md` exists for hosts that read that filename. Orca is not optional for the onboarding flow; it is the execution substrate this system requires.

When onboarding is active, read only the router `master-ops/ONBOARDING.md`, ask its session-mode question, then open `master-ops/onboarding/00-orientation.md`. Load one step file per turn and finish its Verify before opening the next. Never read the step files all at once.
