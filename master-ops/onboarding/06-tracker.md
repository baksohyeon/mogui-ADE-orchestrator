# 06 — Initialize The Issue Tracker (Step 5)

Load rule: read this file only when Step 5 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). Next file after Verify passes: `07-user-rules.md`.

**Position and action:** Step 5 begins with a localized ops repository: initialize the chosen tracker there and make it resolve from `{{WORKSPACE_ROOT}}`.

**Why/caution:** Execution state belongs in the tracker, but upward resolution can silently select a database above the workspace or stop at the wrong Git root.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the ops repository is filled in, and now the Herald prepares the Master's task tracker. What we decide next: where day-to-day working state lives. Explain ELI5 that the supported Beads tracker is the Master’s working memory for tasks: it is reloaded at boot and after compaction, while long-term decisions still live in Git. Ask whether to initialize Beads now and which short issue prefix to use; propose a two- or three-character prefix beside the default and explain that IDs are spoken to the owner. Remind that this prefix is not the monitor namespace from the workspace-facts step.

## Run

For Beads, run only after approval:

```console
$ cd "{{OPS_REPO}}" && bd init --prefix <approved prefix>
$ { [ -e "{{WORKSPACE_ROOT}}/.beads" ] || [ -L "{{WORKSPACE_ROOT}}/.beads" ]; } \
    && echo "already exists, inspect before linking" \
    || ln -s "$(cd "{{OPS_REPO}}" && pwd)/.beads" "{{WORKSPACE_ROOT}}/.beads"
$ cd "{{WORKSPACE_ROOT}}" && bd where
```

Immediately after `bd init`, compare `CLAUDE.md` and `AGENTS.md` before continuing. **Announce-and-proceed — do not open a choice for the byte-only case.**

- If they differ only at the byte level (whitespace, blank lines, or block order) while the semantic content is the same: re-unify automatically, write the same common block to both files, and tell the owner in ELI5 once, for example: "Two instruction files for different agent hosts had drifted in formatting only; I made them match again so both hosts see the same rules. No decision needed from you." Then continue.
- If any substantive line or block exists in only one file: stop and ask whether to accept host-specific divergence before proceeding. That is the only branch that needs a question.

Ask before creating the workspace → ops `.beads` link. Record active work in the tracker and seed only load-bearing memory pointers and rules.

## Verify

From `{{WORKSPACE_ROOT}}`, not inside the ops repository:

- `bd where` or its equivalent resolves to the ops repository
- this workspace database differs from every product repository database
- no tracker database exists above `{{WORKSPACE_ROOT}}` on the path to the filesystem root
- any tracker environment override printed from the agent's actual shell is empty or points inside the workspace

## If fail

- If the prefix is wrong, `bd rename-prefix` rewrites database IDs and references but not Markdown.
- For another tracker, stop and add a complete initialization and verification branch before asking the owner to choose it.
