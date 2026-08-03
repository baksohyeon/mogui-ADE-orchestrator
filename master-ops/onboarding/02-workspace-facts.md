# 02 — Collect Workspace Facts (Step 1)

Load rule: read this file only when Step 1 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `03-ops-repo.md`.

**Position and action:** Step 1 begins after prerequisites pass: collect and measure the workspace facts before routing any work. Pace this step in three short turns when needed: (A) purpose and workspace root, (B) repository inventory, (C) name, monitor namespace, and model.

**Why/caution:** The master operates above repositories and needs a confirmed absolute root, a purpose, and an inventory.

## Owner script (3–6 sentences, adapt to the owner's language)

Where we are: the machine checks passed. What we decide next: what this master is for and which folder it will manage. Before asking, give these plain definitions in the user's language:

- "Workspace (root)" is the folder that groups the repositories this master will manage, nothing more.
- "Workspace name" is a display label; by default, it is that folder's name.
- "Monitor namespace" is a short tag that keeps this workspace's session artifacts separate from other workspaces. It is not the issue-tracker prefix (that comes later, in the tracker step).
- "Default model identifier" is the model the master session is expected to run as; use the chosen agent CLI's table row below as the recommended candidate and measure the actual model at boot rather than guessing.

## Step 1A. Purpose, then root

Ask what this master is for, with concrete examples so the owner can recognize a fit rather than invent a category. Examples to offer (adapt language; keep the range):

- Coordinate several product repositories under one owner (multi-repo product workspace).
- Maintain one open-source or internal library and its docs, issues, and release path.
- Run a personal or experimental sandbox that may be thrown away.
- Operate a platform or harness repository (like this orchestrator) while keeping product checkouts separate.
- Something else — free-form is always valid.

Explain why: purpose shapes which folder is the right root, which repositories belong in the inventory, and how aggressive the master should be about outside checkouts. Record the answer in the operations document later; do not invent a purpose if the owner defers.

Master model criteria (for the later model question in 1C; do not ask model yet):

| Agent CLI | Master-session top-tier candidate |
| --- | --- |
| `claude` | `claude-fable-5` |
| `codex` | `gpt-5.6-sol` |
| `grok` | `grok-4.5` |
| `cursor-agent` | measured at boot; no fixed identifier yet |

The master session runs the top tier of its agent family. Worker and dispatch models use task-based tier selection instead: choose the lowest sufficient tier and state the exact model explicitly in every dispatch. For the `{{MODEL_ID}}` question in 1C, recommend the row for the chosen agent CLI; for `cursor-agent`, recommend measuring at boot and confirming the candidate with the owner.

**Workspace root — guide, then ask. Do not scan the disk for candidates and do not present a ranked shortlist of folders the agent discovered.** That pattern feels like the installer is choosing the owner's house for them. The owner chooses; the installer only validates what they paste.

Give a short setup guide in the owner's language (terms first, then how to pick, then how to send the path):

1. **What it is:** the folder that *groups* the repositories this master will manage — not one product repo inside it, and not a broad home folder that mixes unrelated projects.
2. **How to pick (owner criteria, not agent measurement):**
   - Several product repos → the folder that already contains them.
   - One repo only → that repo's *parent* folder (so the master sits above it).
   - Experiment / disposable → a new empty folder is fine; create it first if needed.
   - Prefer an existing grouping folder over inventing a wider one.
3. **How to send the absolute path (prefer Orca):** In Orca, select the project or folder that should be the workspace root and use **Copy path** (or the equivalent path-copy action in the project/folder UI). Paste that absolute path into the chat. Alternatives if they are not in Orca yet: Finder → folder → Get Info / copy path, or a terminal `pwd` after `cd` into the folder. Relative paths and `~` alone are not enough; we need a full absolute path.
4. **What happens next:** only after they paste a path, the installer checks that it exists and is a directory — never before, and never by fishing nearby parents.

Then ask once: please set or confirm that folder, copy its absolute path, and paste it here. Wait for their answer. Do not invent or "helpfully default" a path from `{{RUNTIME_ROOT}}`'s parent tree.

Only after the owner provides a path, validate:

```console
$ test "${WORKSPACE_ROOT#/}" != "$WORKSPACE_ROOT" && test -d "$WORKSPACE_ROOT"
$ ls -la "$WORKSPACE_ROOT"
```

## Step 1B. Repository inventory

Read current files first. Detect every immediate child Git repository under the confirmed root. **Default: register all of them into `{{REPO_LIST}}`.** Read the full measured list back for confirmation. Do not open with exclusion hunting; the owner may drop a child only by explicit opt-out after seeing the full list. Never invent repositories that were not measured.

When the user names a repository that lives outside the confirmed workspace root, lead with the default path and plain language: **please move or clone it under the workspace root** so the master can see it and Orca's sidebar stays one workspace. Explain why: the master holds the inventory (`{{REPO_LIST}}`) and measures code across it (for example a review graph indexed at the workspace root); a path outside the root is invisible to that measurement and splits the sidebar. Only if the owner refuses to move it, offer the secondary home:

- **Default / recommended:** move or clone under the workspace root; it joins `{{REPO_LIST}}` as an ordinary member. The installer does not move anything; the owner does.
- **Secondary (opt-in):** record it as an external lane — absolute path, who may write, which gates run before push. Every claim about it needs its own measurement. Legitimate cases include a public open-source lane or another owner's checkout.

## Step 1C. Name, monitor namespace, model

Ask for workspace name (default: confirmed root basename), monitor namespace, and default model identifier to measure at boot, with measured candidates, a recommendation and reason, and a free-form option for each when available; explain why each is needed. Remind once that monitor namespace is not the Beads/issue prefix.

## Verify

- the master's purpose was asked with examples and recorded or explicitly deferred
- the owner was guided with definitions and path-copy instructions; the agent did **not** present measured folder candidates
- `{{WORKSPACE_ROOT}}` was provided by the owner (absolute path), then validated as an existing directory
- `{{WORKSPACE_NAME}}` is explicit or is the confirmed root basename approved by the user
- `{{REPO_LIST}}` defaults to every measured immediate child repository, with only explicit opt-outs removed
- every repository the user named that lives outside the root was offered move/clone first; if still outside, it is recorded as an external lane with access rules; none is left implicit

## If fail

- If the pasted path is missing, not absolute, or not a directory, say so plainly and ask them to paste again. Do not substitute a measured fallback.
