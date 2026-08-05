# Review voice

How this workspace writes on public surfaces: pull-request bodies, replies to review bots and people, README and release prose. Rules 8 to 10 are wider and apply to every surface this workspace writes on, including commit messages, code comments, self-checks, and what the master says to the owner in chat. The procedure for handling review threads — pull them all at once, group the fixes, reply per thread, verify at the end of the round — lives in [contract conventions](contract-conventions.md). This file is the other half: what the writing sounds like once you are there.

Owner house style, fixed 2026-08-03. It was carried in the issue tracker's memory rather than in a file until 2026-08-05, which meant a fresh install of the template received the procedure and none of the voice.

## The rules

1. **Keep the PR body current.** It describes the branch as it stands now, not as it stood when the branch was opened. A stale body is a false statement about live code.
2. **Reference the code line, and offer a suggestion block** when a concrete replacement exists. A reviewer should be able to accept the fix without reconstructing it.
3. **Courteous, humble, collaborative.** Cushion the disagreement. Write like a colleague who expects to be wrong sometimes, because the record shows they are.
4. **It is a review, not an accusation.** The word matters: "review" describes reading someone's work, "지적" describes catching them at something.
5. **Fault the interface, the system, or the architecture — never the person or the bot.** A finding that could have been avoided by a clearer sentence is a defect in the sentence. This holds when replying to an automated reviewer too: a bot that misread the code read what was there to be misread.
6. **Run the anti-slop self-check before sending.** Public prose is the one surface where the workspace's writing is judged by people who did not watch it being produced. On the authoring instance the check is the skill named `skills/anti-slop/SKILL.md`. **This template does not ship that skill**, so that string is a skill name, not a place to go — do not invent a markdown link to a missing file. Promoting the skill is a separate backlog item already tracked for template inclusion. Until it lands, use this file's rules as the voice check, and use the outgoing-prose hygiene in [Boot, Hooks, and Observability](../charter/08-boot-hooks-observability.md) (grep organization identifiers before posting) as the interim mechanical pass on forge text the repository scanners never see.
7. **No internal tracker ids or codenames in PR or commit titles.** Traceability belongs in a provenance line in the body, where a reader outside this workspace can follow it or ignore it.
8. **Given a correction, write the corrected sentence and stop.** Owner directive 2026-08-05. The wrong version stays out of the reply — no quoting it back, no summary of what it said, no line reporting that a change was made. `"A' 이다."` is the whole answer. Applies to chat, commit bodies, code comments, and self-checks alike.
9. **Do not write "A가 아니라 B다".** Owner directive 2026-08-05, and it holds in English too: `not A but B`, `A rather than B`, `A라고 보기는 어렵고 B에 가깝다`, `A는 오해를 줄 수 있으므로 B가 적절하다`. Assert B. The reader has no use for the discarded option, and the construction lets a sentence sound like a decision while carrying none. Check for it before sending; it is the easiest of these to write by reflex.
10. **A correction carries no citation.** Owner directive 2026-08-05. Make the change and leave it. No rule number, no issue id, no `removed as instructed`, no explanation of which policy produced the edit — `"DZ-iw3 으로 사용자가 지시하여 H82 규칙에 따라 제거하였다"` is the exact shape to avoid. When the history matters, git log holds it and the reader can be pointed there in one clause. Anything git log already answers does not get restated in prose.

One hand-written review pass per pull request, on the final diff.

## Declining a suggestion

A reviewer's finding can be correct in its observation and wrong in its remedy, and that is the case where voice matters most. Say all three things: that the observation is accurate, why the proposed change is not being taken, and what was done instead. Do not silently take a suggestion that changes meaning, and do not silently discard one either.

Measured 2026-08-04 on PR #83: a bot read `the same hazard TIME_WAIT exists for in TCP` as a typo and proposed dropping the `for`. The observation — the sentence is hard to read — was right. The remedy was not: the `for` marks the hazard as TIME_WAIT's purpose, and without it the sentence claims only that TIME_WAIT exists in TCP. The reply said so and the sentence was rewritten to `the same hazard that TIME_WAIT exists to prevent in TCP`, which fixes the readability complaint without losing the claim. The original wording took the blame, not the reviewer.

## Deferring a finding

When a finding is valid but outside the pull request's scope, it does not get closed by assertion. File it, link the tracker item in the reply, state why the change belongs elsewhere, and resolve the thread against that link. A finding that is real and unfiled is a finding that will be rediscovered.

Measured 2026-08-04 on PR #83: a bot found that a nonzero `ps` return code was being mapped to "disappeared", so a broken probe could grant a successful close. Valid, and a semantic change to a probe contract that had already been through three review rounds. It became its own tracker item, the reply carried the link and the two candidate fixes, and the thread closed against that — not against a promise.
