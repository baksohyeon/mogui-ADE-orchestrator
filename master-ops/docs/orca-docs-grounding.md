# Orca Docs Grounding — foundational knowledge charter

Owner directive (2026-08-04): these two source-grounded references are the workspace's foundational knowledge for Orca. The master and every dispatched worker treat them as the first stop for any Orca question beyond the version-matched `orca skills get` output.

## Charter clause: orca-first for agent lifecycle

Orca is this workspace's ADE infrastructure. Agent lifecycle concerns — waiting on events, monitoring workers, terminal control, worktree lifecycle, messaging — use Orca primitives first (`check --wait` with deliveryId ack-chaining, `terminal wait`, `worktree create/remove`, dispatch/inject), wrapped by the host harness only for notification delivery. Hand-rolled sleep/poll loops around state Orca can already block on are a measured anti-pattern (2026-08-04: owner killed three bash poll watchers; the native `check --wait` replaced them). Never guess Orca flags — measure with `--help`, `orca skills get`, or these references.

## Source 1: Orca Documentation (operational reference, 22 pages)

- Human page: https://grok-wiki.com/public/docs/stablyai-orca-2036d532bf1c
- Agent index (read first): https://grok-wiki.com/public/docs/stablyai-orca-2036d532bf1c/llms.txt
- Full Markdown (only when whole-docs context is needed): https://grok-wiki.com/public/docs/stablyai-orca-2036d532bf1c/llms-full.txt
- Snapshot: 2026-06-01

Covers: overview/install/quickstart, worktrees and repos, terminals and agents (`TuiAgent` catalog, `ORCA_*` env injection), runtime environments (`orca serve`, pairing codes), repository hooks (`orca.yaml`, trust prompts), CLI scripting workflow, **agent orchestration** (send/check/reply, task DAGs, dispatch/inject, decision gates), SSH remotes, scheduled automations, browser automation, source-control integrations, CLI core + selector/JSON reference, settings, develop/build/testing/contributing, troubleshooting, telemetry.

## Source 2: Orca Developer Reference Wiki (internals, 6 pages)

- Human page: https://grok-wiki.com/public/wiki/stablyai-orca-47ffb1f68457
- Agent index (read first): https://grok-wiki.com/public/wiki/stablyai-orca-47ffb1f68457/llms.txt
- Full Markdown (only when whole-wiki context is needed): https://grok-wiki.com/public/wiki/stablyai-orca-47ffb1f68457/llms-full.txt
- Snapshot: 2026-05-27

Covers: three-process Electron architecture, **relay server & agent communication protocol** (WebSocket relay every agent subprocess connects to), **worktree & parallel agent orchestration internals** (agent-awake service, trust presets, hook lifecycle, removal safety checks), git/source-control integration layer, renderer/Zustand state, **CLI/skills/extension points** (agent-hook relay, SSH remote runtime, MCP config).

Use the docs (source 1) for operating Orca; use the wiki (source 2) when a behavior needs explaining from internals (why injection lands where it does, how trust gates fire, what the relay sees).

## Reading protocol

Start with the agent index and fetch the smallest relevant page before the full Markdown. Both are read-only generated snapshots; URL hashes may change between snapshots — on 404, resolve the current snapshot from grok-wiki and update this file. For live behavior, prefer `orca skills get orca-cli` / `orca skills get orchestration` from the installed binary because those are always version-matched; the snapshots explain design, the binary defines current flags.

Repository: [stablyai/orca](https://github.com/stablyai/orca)
