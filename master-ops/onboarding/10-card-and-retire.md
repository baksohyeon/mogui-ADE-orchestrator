# 10 — Hand The Human A Card, Then Close The Installer (Step 10)

Load rule: read this file only when Step 10 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). This is the last step file.

**Position and action:** Step 10 runs after the master reports a clean boot: verify the conversation actually happened, hand the user something portable, and ask them to close the installer terminal.

**Why/caution:** Everything installed here is worthless if the user does not know the four or five sentences that operate it, and an installer session left running is a second agent holding the same repository.

## Agent-only check first

Verify the conversation, not just the artifacts. The steps above ask questions; a run that produced files without answers is a run that guessed. Check that the workspace facts were confirmed rather than inferred, that the component choices are recorded including declines, and that each essential decline was re-asked once. If any answer is missing, ask now rather than recording an assumption as a decision.

## Owner script (3–6 sentences, adapt to the owner's language)

Where we are: the master booted clean; the installation is done. What happens next: I hand you a short operating card — keep it wherever you keep notes, as plain text under a name you will find again, such as `llm.txt`; it is written to be pasted into any agent, so it does not depend on this session existing. After that, please close this installer terminal: two agents holding one repository is how uncommitted work gets lost, and the installer has no further role. I will not close it myself, and the master's terminal stays running.

## The operating card

Print it in full:

```text
# Operating this workspace

Master lives in: {{WORKSPACE_ROOT}}          Ops repository: {{OPS_REPO}}
State: the issue tracker in the ops repository. Long-term decisions: Git.

To start work, tell the master:
  "Role State?"                     it reports its active role and lock
  "Propose <goal>"                  it plans, then waits for your approval
  "Approved, execute"               it executes only what you approved

To delegate, tell the master:
  "Dispatch <task> to a worker"     it runs the gate, dispatches, and verifies
                                     the result before accepting it

Before publishing anything, the master runs:
  the test suite, the redaction scan, the redaction inventory
  A green scan covers repository content only. Pull request text,
  release notes, and issue prose are not scanned by anything.

When a session gets long:
  "Propose succession"              it audits, spawns a clean successor,
                                     and freezes itself

If the master behaves unlike the documents, check what was declined at
onboarding before assuming a defect. Declined at install:
  <declined components, or the word none>

New to Orca? Concepts, and labels that look alarming but are normal:
  {{RUNTIME_ROOT}}/docs/public/orca-concepts.md
```

Fill the declined slot (the `<declined components, or the word none>` line) from the recorded choices. If nothing was declined, write the word none rather than leaving it blank, because a blank line reads as unknown. The angle-bracket slots in the card are filled by hand at print time; do not introduce a new `{{...}}` placeholder for them, since the placeholders step verifies that no `{{...}}` placeholder remains in the generated repository.

If the user lingers with Orca questions instead of closing, answer them here under the Orca Context Charter (grounded in the docs snapshot and the concepts guide) before retiring; a user who leaves onboarding still confused about workspaces will misplace the next master by hand.

## Verify

- the card was printed in full, with placeholders replaced and the declined line filled or explicitly none
- the user was told where to keep it and that it works when pasted into any agent
- the user was asked to close the installer terminal, with the reason given
- the master's terminal was left running
