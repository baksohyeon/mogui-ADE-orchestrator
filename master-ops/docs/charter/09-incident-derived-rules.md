# §9. Incident-Derived Rules

Records rules that came from production incidents and their measurement criteria. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Every rule below was paid for. Each one names the observation that produced it and the measurement that settles it, because a rule without its evidence gets argued away by the next reader, and a rule without a measurement cannot be checked. Add to this section the same way: rule, what was observed, how to measure it. Do not add a rule you cannot measure.

**Acknowledgement is part of reading. A handle is routing metadata; a Run address is an identity. A loopback test proves nothing about reachability from outside.**
Observed: two masters could not reach each other on 2026-08-03 because a mailbox that had been read and never acknowledged held the head of the queue while every later message stacked behind it invisibly. Both senders saw successful sends, both receivers saw nothing to read. Each blamed a different wrong cause first: a runtime version difference (both were on the same version) and malformed call shapes (real, but not what was blocking). The third item was confirmed by a self-addressed test that succeeded under any binding.
Measure: `orca orchestration check` with `--terminal <handle>` returns the oldest unacknowledged delivery; one that keeps returning until `--ack` is passed names a read that was never acknowledged and a stalled queue. `orca orchestration run-current --json` with the CLI resolved the way Step 0's preflight resolves it names the terminal's actual bound Run, the address that routes cross-master traffic instead of a handle that dies with app restart or session relocation. A self-addressed message succeeds under any binding; only a message sent from a different session proves reachability from outside.

**Reachability is not capability. A record is not an effect.**
Observed: an orchestration RPC answered reads normally while every write returned `effectsApplied: false`, because a coordinator retained across a state migration could not prove its original process identity. A dispatch was recorded as dispatched while the worker's heartbeat stayed absent and its terminal stayed empty.
Measure: `orca orchestration run-current --json`, with the CLI resolved the way Step 0's preflight resolves it, reports a bound non-legacy Run. Do not accept "the call returned" as evidence that anything landed.

**Silence is not a pass.**
Observed: three consecutive hook experiments produced no output, for three different reasons, and one of those silences was reported as "applied".
Measure: feed the instrument a case it must object to, and watch it object. Until you have seen it speak, its silence is unmeasured; after that, absence of output is a result. Prevention, which is to arrange that one such case exists before trusting any quiet run, follows from the measurement rather than replacing it.

**A declaration is not a measurement.**
Observed: the dispatch gate enforces the model identifier a caller declares at `check`, and `register` takes no model at all. The incident that motivated the tier policy was a worker default-inheriting a top-tier model, which a compliant declaration does not prevent.
Measure: `{{RUNTIME_ROOT}}/scripts/model-identity-probe` for what a session runs now, `{{RUNTIME_ROOT}}/scripts/model-drift-audit` for transitions across a whole transcript. For `model-identity-probe`, exit 2 means drift or undecided, and exit 0 without an expected model is only an informational no-assertion result. For `model-drift-audit`, exit 2 means undecided. Do not read any of those states as a pass.

**Put the guard where the incident was.**
Observed: ten workers were fanned out at once and every one of them silently inherited the runtime's default top tier. That cost incident is why the tier policy exists. The policy encodes model identifiers, so it stops neither half of what happened: a single top-tier dispatch passes it, and `unknown_model: "deny"` blocks any model the file has not been hand-edited to name, including cheaper or stronger ones released later.
Measure: replay the incident's shape against the guard and read the verdict. Ten agents at a top tier must deny, and so must ten single-agent dispatches at that tier one after another; a guard that permits either is attached to the wrong variable however reasonable its condition reads. This gate already computes `n_agents × est_chars`, so a ceiling in those terms is measurable against both replays.

**Say whether a constraint came from availability or from policy.**
Observed: a worker reported that one model "is the only available model and matches the policy". The single option came from the CLI offering exactly one model, and the policy merely also allowed it; an earlier attempt failed because the requested identifier does not exist in this installation at all. Read quickly, that sentence blames the policy for a host fact.
Measure: read the output and try to answer, from it alone, which candidates the host lacks and which the policy forbids. If the two cannot be told apart without opening the policy file, the report does not distinguish them. A policy answers whether a model is permitted; it never answers which model fits, and it is not the reason a host has only one.

**Fix the pair, or the survivor lies.**
Observed: repeatedly, in one working day, code lost a claim its documentation still made, or documentation kept describing behaviour the code had dropped. Grepping a removed identifier finds the code and misses the prose, because prose names the same thing in different words.
Measure: after changing behaviour, grep the identifier and grep the words that describe it, then count the surviving mentions that still assert the old behaviour. That count must be zero. It is rarely zero on the first grep, because prose names the same thing in different words than code does.

**A green light must name its scope.**
Observed: a redaction scan reports success with organization-specific rules absent, covering generic patterns only, and the inventory silently drops rules that fail to compile. Both look identical to a clean result.
Measure: look at the green line and try to tell "checked everything and found nothing" from "checked almost nothing". If the output carries no scope, files scanned and rules loaded, the two are indistinguishable and the green is not a pass. A gate that can narrow its own coverage must print what it covered.

**A gate nobody can pass is a gate nobody runs.**
Observed: an onboarding preflight blocked a host the harness had been operating on all day, with two of three failures false. The pressure that creates is to skip the preflight, which discards every other check with it.
Measure: run the gate on a known-good host. If it cannot pass there, the check is wrong. Provide a waiver that is printed and counted rather than an escape that is silent.

**Do not read a blocker. Test it.**
Observed: deny lists and hook wiring that were documented as enforced turned out not to be, and two waiver behaviours that read correctly were only confirmed by breaking them.
Measure: mutate the check so it should fail, and watch the test fail. A check with no failing case has not been verified.

**A squash merge erases the base a stacked branch was built on.**
Observed: two stacked branches had to be rebased mid-flight after their base merged, because the squash commit shares no history with the branch's parent.
Measure: after the base merges, `git rebase --onto origin/main <old-base-sha>`, then confirm the branch is one commit and the expected file set before pushing.

**Reverting a file discards work that was never committed.**
Observed: `git checkout --` was used to undo a deliberate mutation during testing, and it also removed uncommitted work in the same file, which had to be reconstructed.
Measure: before reverting a path, run `git status --porcelain <path>` and read it. Every line there is work the revert will discard, so an empty result is the only state in which revert is safe. The same procedure was safe an hour earlier because that result was empty then; the safety belonged to the state, not to the procedure.

**Host-injected autonomy defaults override the charter unless mechanically countered.**
Observed: on 2026-08-03 a master on a hook-rich host repeatedly implemented product changes inline and executed without proposals, despite §2 and §3. Each time the owner interrupted with an explicit instruction to propose first. The host's instruction surface provided a default behaviour — act autonomously, do not ask, keep going — that outweighed the charter in context. Host defaults are agent-neutral and apply to any high-compliance model; the charter is paper without the mechanical coupling.
Measure: wire the §8 UserPromptSubmit hook to inject both the role-state line and the `Proposal -> Approval -> Execution` rule into every user turn; feed each hook a case it must object to and watch it object before trusting any quiet run. Until the UserPromptSubmit pairing is wired, audit sessions by counting explicit owner corrections of unproposed execution in the transcript — the pass is that count staying zero.
