This quickstart gets a local clone to the point where you can inspect the runtime, run tests, and start the master onboarding flow.

# Getting Started

This repository is meant to be used as an operations harness, not as a library dependency. Start by cloning it, running the local checks, then use the onboarding guide to create or configure the operations repository for your workspace.

## Clone

```bash
git clone <repository-url> orchestrator
cd orchestrator
```

## Inspect The Runtime

Run the test suite from the repository root:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Check which local adapter tools are visible:

```bash
scripts/adapter doctor
```

## Start An Agent Session

For first-time setup, do not try to boot the master inside the installer conversation. The onboarding guide explains how to collect workspace facts, initialize the operations repository, fill placeholders, choose the issue tracker, and create the Generation 1 master session.

Continue with:

- [master-ops/ONBOARDING.md](../../master-ops/ONBOARDING.md)

If your host supports Orca-managed terminals, onboarding can use `scripts/master-succeed spawn` to create the founding master. If it does not, open a clean agent session at the workspace root and paste the kickoff text produced during onboarding.

## First Boot Smoke

After onboarding creates the operating files, the first master boot should prove three facts:

```text
Role State is declared.
The configured model and measured model are reported separately.
Placement evidence matches the intended workspace.
```

The relevant script entry points are:

```bash
scripts/master-bootstrap \
  --charter master-ops/docs/MASTER-OPERATIONS.md \
  --json

scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

> Tip: Keep this page short. The onboarding guide owns the detailed setup flow, and the lifecycle guide owns boot and succession details.

Read next: [Concepts](concepts.md) or [Master Lifecycle](master-lifecycle.md).
