# 10 — Hand The Human A Card, Then Close The Installer (Step 10)

Load rule: read this file only when Step 10 begins. Router: [`../ONBOARDING.md`](../ONBOARDING.md). This is the last step file.

**Position and action:** Step 10 runs after the master reports a clean boot: verify the conversation actually happened, hand the user something portable, then let the newborn master close the installer terminal using the kill switch from Step 8.

**Why/caution:** Everything installed here is worthless if the user does not know the four or five sentences that operate it, and an installer session left running is a second agent holding the same repository. The installer does not close itself; the master closes the installer after the installer has printed the operating card and verified that the master is alive.

## Agent-only check first

Verify the conversation, not just the artifacts. The steps above ask questions; a run that produced files without answers is a run that guessed. Check that the workspace facts were confirmed rather than inferred, that the component choices are recorded including declines, and that each essential decline was re-asked once. If any answer is missing, ask now rather than recording an assumption as a decision.

## Owner script (kind ELI5, adapt to the owner's language)

Where we are: the Master booted clean; the Master is raised, and the installation is done. What happens next: the Herald hands the owner a short operating card — keep it wherever you keep notes, as plain text under a name you will find again, such as `llm.txt`; it is written to be pasted into any agent, so it does not depend on this installer session existing. Explain plainly that the card is not symbolic: it is the small set of phrases that lets the owner ask for role state, propose work, approve execution, delegate, and request succession. After that, the Master closes this installer terminal with the kill switch I handed it, because two agents holding one repository is how uncommitted work gets lost and the Herald has no further role. The Master's terminal stays running.

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
  "Dispatch <task> to a worker"     it checks preconditions, sends the work to a
                                     worker, and reviews the result before accepting

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

If the user lingers with Orca questions before retirement, answer them here under the Orca Context Charter (grounded in the docs snapshot and the concepts guide); a user who leaves onboarding still confused about workspaces will misplace the next master by hand.

## Installer retirement

After the card is printed and the checks above pass, send the newborn master the warm resume note and kill switch from Step 8. The note must say that this installer has completed Step 10, the operating card was printed, the master terminal is the living session, and a resumed installer should do no further work unless it proves the master is absent. The master then closes the installer terminal with `ORCA terminal close --terminal <installer handle> --json`; if the close command fails or the handle is unavailable, report the failure plainly to the owner and leave the installer idle rather than guessing another terminal.

## Verify

- the card was printed in full, with placeholders replaced and the declined line filled or explicitly none
- the user was told where to keep it and that it works when pasted into any agent
- the newborn master was given the warm resume note and installer kill switch
- the newborn master closed the installer terminal, or the close failure was reported without guessing another terminal
- the master's terminal was left running
