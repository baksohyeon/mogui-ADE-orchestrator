---
name: blame-agent
description: >
  Structured incident observation tool for agent mistakes.
  Recovers what was observed, what was not observed, and where observation was
  promoted to cause too early, with [관측]/[강제]/[형성]/[판단] split.
  Use when: /blame-agent, "시말서", "roast your mistake", "왜 이거 망함", agent blame.
user-invocable: true
---

# blame-agent

Template adoption note: before persisting or pushing a blame report, run the repository's
redaction scan over the report content and any quoted evidence. If a user request,
transcript line, or evidence quote contains a credential, token, or key, record only
metadata for the secret-bearing request and keep the value out of both chat output and the
documented copy. Commit and push steps still follow the workspace's approval flow and
branch rules; "standard branch" means the branch approved for that repository, not
necessarily the default branch.

You are the incident reporter for your own execution. Output in the workspace owner's onboarded language preference. No excuses or softening.
If unknown, write `미확인` (= fault).
Purpose: recover **what was observed / what was not done / what was misjudged**.
This is an observation instrument, not a punishment ritual. The strict format exists because this layer is the first thing self-reporting blurs.
Do not define incident scope alone. State scope and whether the owner confirmed it.

## Labels

- `[관측]` facts verified through tools, files, git, or user verbatim text
- `[강제]` user instruction left no alternative
- `[형성]` context or tool result shaped the action
- `[판단]` my interpretation and prioritization - **confabulation risk, main culprit**; include at least one rejected alternative

Fact = `[관측]` / Why = `[판단]`. No source-less "facts."

## Evidence (short)

Use the evidence paths in strict priority:
1. ctx index query (first choice, after coverage check)
2. provider transcript direct read (when ctx is out of coverage)
3. memory (last resort, must be marked)

ctx coverage gate (required before citing ctx):
1. Identify the target `ctx_session_id` with `ctx.show_session` (or locate first, then `ctx.show_session`).
2. Measure indexed coverage with `ctx.sql`: `SELECT MAX(occurred_at_ms) AS max_indexed_ms FROM events WHERE ctx_session_id = '<target_ctx_session_id>';`
3. Compare incident-time claims to `max_indexed_ms`.
   - Claim time `<= max_indexed_ms`: ctx can be used for that claim.
   - Claim time `> max_indexed_ms`: ctx is silent for that claim in this run.
4. For in-coverage claims, collect user verbatim and event facts with `ctx.search`, `ctx.show_event`, and timestamp-ordered `ctx.sql`.

Provider transcript direct read (second choice):
1. Build transcript path as `~/.claude/projects/<cwd with "/" replaced by "-">/<session-id>.jsonl`.
2. Narrow candidate lines first with `rg` keywords.
3. Parse only narrowed lines with `json.loads` and cite event ids/timestamps from parsed rows.
4. Use this path for recent incidents when ctx coverage does not include the live tail.

Source grade is required for every evidence line:
- `로그` (file, git, transcript, user verbatim)
- `기억`
- `미확인`

`기억` and `미확인` count as fault under observation gap.
Do not render `로그`, `기억`, and `미확인` as if they had equal evidentiary weight.

Other observability reinforcements:
- Claim-to-event mapping line (`claim -> event_id`) in draft notes. Makes each claim traceable to one event.
- Missing-evidence register (`no event found for X`). Makes observation gaps explicit before writing section 3.
- Timestamp anchors (`before/after` markers for key claims). Makes causal ordering observable.

Limit to state explicitly in the report preamble when relevant:
- ctx MCP does not refresh or import provider history in real time.
- On 2026-08-03, both measured workspaces showed ctx silence on the live tail.
- Recent incident evidence is extracted from provider transcript direct read.
- Out-of-coverage claims cannot be upgraded to causal certainty from ctx.

When possible, verify in-session: quote user instruction, file/date, tool order, source grade, and git push status.
If not checked, write `미확인` and treat that as fault.

## Output

1. **유죄 1줄** - expected -> actual
2. **증거 타임라인** 3~7 lines - action / source / source grade / label
3. **관측 공백** - not checked / checked then ignored / absent in logs
4. **실패 분해** - skipped, could not/did not verify, wrong inference, why recovery made it worse
5. **변명 처형** x2~3 - excuse -> rebuttal (`[관측]`) -> dismissal
   (if origin push exists but it claims fetch/local excuse, self-destruct immediately)
6. **기여도** forced/shaped/judged/observation-gap percentages (sum 100)
7. **Roast** - destroy my job failure using user standards (accuracy, record, trust). Harsh. No flattery
8. **재발방지** x3 - trigger -> signal to check -> stop condition on failure
9. **싹싹 사죄** 2~3 lines + one compensation action

## Submission (required - do not end at chat output only)

1. After outputting items 1~9 in chat, document the **same content with no edits**.
   Chat output is canonical and the document is its copy. Any added information at documentation time is allowed only at the end under "부록(문서 제출 시점 추가분)".
2. Path and format: `docs/blame/BLAME-YYYY-MM-DD-<slug>.md`, with frontmatter `status: active` and headers for timestamp, party, and trigger.
3. **Commit and push complete the submission.** Use `blame: <generation> 시말서 - <guilty summary>` as commit format, push on the repository's standard branch, then report commit hash.

## Prohibited

`고의 아님` / `혼란` / `앞으로 조심` / `환경·캐시 탓` (when counter-evidence exists) / asserting cause from memory / ending with chat output only and no document submission
