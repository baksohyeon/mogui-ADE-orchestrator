---
status: active
---

# ctx Query Doctrine

`ctx` is installed by onboarding preflight on every instance. Installation was never the
problem. **When to reach for it** was never written down, and four generations of masters
answered "I searched the files and found nothing" to questions whose answers were sitting in
the conversation index.

This file is the missing half. It names the tools, states the conditions that require them,
states the conditions that forbid them, and records the query recipes that actually returned
results.

## The tools, by name

These are the callable names. Do not describe them, call them.

| Tool | What it does |
|---|---|
| `mcp__ctx__search` | Search the local index by text query or touched-file path |
| `mcp__ctx__show_event` | One event plus its surrounding window — this is how you read the *answer* to a decision |
| `mcp__ctx__show_session` | One session transcript by ctx session id |
| `mcp__ctx__sql` | One read-only SQL statement against the index; scripts use the `ctx_*` views |
| `mcp__ctx__sources` | Which local agent history sources were discovered |
| `mcp__ctx__status` | Index status, coverage, daemon state |

**They are deferred. Knowing the name is not enough.** The parameter schema is not loaded, so
a direct call fails with `InputValidationError`. Load first, in one call:

```
ToolSearch(query="select:mcp__ctx__search,mcp__ctx__show_event,mcp__ctx__show_session,mcp__ctx__sql,mcp__ctx__status", max_results=5)
```

One `ToolSearch` call takes a comma-separated list. Do not issue one call per tool.

## Reach for ctx when

Each trigger below is a measured failure, not a hypothesis. The failure mode is always the
same shape: the master searched a surface that structurally cannot hold the answer, found
nothing, and reported the nothing as a finding.

1. **You are looking for the basis of a decision or an agreement, and files, tracker, and git
   return zero.** Decisions are born in conversation. Documentation is later, or never. Zero
   hits in Git is evidence about Git, not about whether the decision exists.
2. **The owner asks a memory-check question** — "didn't we decide to…", "I told you already",
   "wasn't that settled". Treat the phrasing itself as the trigger.
3. **You are looking for a decision made in another workspace.** Cross-workspace transfer
   omission is the normal state here, not an exception.
4. **You are after a predecessor's judgment basis following a succession.** The kickoff card is
   a summary written by someone under time pressure; it has been wrong at every succession so
   far. The predecessor's transcript is the record.
5. **You are reconstructing an incident for a blame or retro record.** See the coverage gate
   below; `blame-agent` already requires this and its procedure is authoritative for that genre.

## Do not reach for ctx when

The counter-signal matters as much as the trigger, because a conversation index is a bad
instrument for present state.

- **Code, paths, file contents, current repository state.** Measure those in the repository.
  ctx tells you what was *said*, never what *is*.
- **Whether a rule is currently in force.** A conversation may contain a superseded decision.
  The rule file is the authority; ctx is how you find out why the rule exists, or that it was
  agreed and never written.
- **Anything you can answer with one `grep` you have already validated.** ctx payloads are
  large (see cost discipline).

## Coverage gate — required before citing ctx

Reused verbatim in shape from [blame-agent](../../skills/blame-agent/SKILL.md), which already
established this grammar. Do not invent a second one.

1. Identify the target `ctx_session_id` with `mcp__ctx__search` or `mcp__ctx__show_session`.
2. Measure indexed coverage with `mcp__ctx__sql`:
   `SELECT MAX(occurred_at_ms) AS max_indexed_ms FROM events WHERE ctx_session_id = '<id>';`
3. Compare the claim's time to `max_indexed_ms`.
   - claim time `<= max_indexed_ms` — ctx may be cited for that claim.
   - claim time `> max_indexed_ms` — **ctx is silent for that claim.** Say silent, not absent.
4. For in-coverage claims, collect verbatim with `mcp__ctx__search`, `mcp__ctx__show_event`, and
   timestamp-ordered `mcp__ctx__sql`.

`ctx` is read-only and does not refresh provider history on demand. For an incident whose tail
is newer than the index, read the provider transcript directly — `blame-agent` documents that
fallback path and it stays the second choice, not the first.

## Query recipes that returned results

Measured 2026-08-05 unless noted.

**Mixed-language keywords work, and beat either language alone.** The index runs a hybrid
lexical plus semantic backend (`intfloat/multilingual-e5-small`), so a query mixing the
workspace's languages hits paraphrases in the other one.

```
mcp__ctx__search(query="SSOT origin/main {{OPS_REPO}} dev prod sync recursive self-improvement", limit=5)
→ rank 0.78, <session id>, 2026-08-03T08:53:52Z
→ recovered the owner's standing declaration that remote origin is canonical,
  which no file in any repository contained
```

A prior measured instance, recorded 2026-08-01: a query for `agent-journey field-notes skill
remove eliminate deprecate` located a decision in a *different* workspace (<session id>,
<event id>) after files, tracker, and git had all returned zero.

**Narrow, then read.** `mcp__ctx__search` returns session-level results carrying
`more_matches_in_session` and `rank`. Use those two to pick one session, then
`mcp__ctx__show_event` with a window to read the actual exchange. A search result's snippet is
a fragment; the decision usually lives in the reply that followed it.

## Cost discipline

**Keep `limit` low. Start at 3 to 5.** The payload carries full citation blocks, retrieval
diagnostics, and suggested commands per result. Measured 2026-08-05: a single search at
`limit=15` consumed a large share of a context window, and this exact cost had already been
predicted before it happened. One narrow search plus one `show_event` costs far less than a
broad search, and answers better.

## Non-happy paths

The index is not a guarantee. Measured on this instance 2026-08-05 with `mcp__ctx__status`:
1,819 indexed sessions, 294,606 indexed events, semantic coverage ratio 1.0 — **and at the same
time** 19 failed inventory units, 297 stale inventory units, 297 stale source-import files, and
a background history refresh reporting 752 failures with 3,774 events skipped.

| Condition | How it appears | What to say |
|---|---|---|
| Empty or uninitialised index | `mcp__ctx__status` shows `initialized: false` or zero indexed sessions | "ctx is not indexed here", never "no such decision" |
| Claim newer than coverage | claim time `> max_indexed_ms` | "ctx is silent for this claim"; fall back to the provider transcript |
| `source_exists: false` | present on real results today — the indexed session's file has since moved or been deleted | The index entry is still citable; the file is not re-readable. Say which |
| Other workspaces mixed in | a search for this workspace's terms returned sessions from unrelated projects | Filter with the `workspace` parameter, or check `cwd`/`source_path` on each result before citing |
| Stale units present | the counters above | Report the counts. A nonzero stale count means "partial coverage", not "clean" |
| A `cwd` or `workspace` filter returns empty | the target session's events carry `cwd: null`, so the filter removes the whole session | Re-run the coverage count without the filter and compare. Measured at the peer seat 2026-09-16: filtered 0 events, unfiltered 3,333 for the same session, and the empty result had been read as an absent index |

The rule underneath all six rows is the same one `scripts/measure` exists for: **a search that
finds nothing and a search that could not run print the same thing.** Read the status, then
report which one happened.

## Worker probe form

A worker can be told to run this. The dispatch text names the tools and the load step, because
a worker on a fresh host has the same deferred-tool problem:

> Load the tools first with one call:
> `ToolSearch(query="select:mcp__ctx__search,mcp__ctx__sql,mcp__ctx__show_event", max_results=3)`.
> Then run `mcp__ctx__status` and report `initialized`, `indexed_sessions`, and every nonzero
> `failed_*` and `stale_*` counter verbatim. Then run the assigned query at `limit=3` and report
> `rank`, `ctx_session_id`, `source_exists`, and the timestamp for each hit. Do not summarise a
> hit you did not open with `mcp__ctx__show_event`.

## Why this file exists

Opened 2026-08-04 on owner instruction, after a master reported zero results from files,
tracker, and git for a decision that was in the index the whole time. On 2026-08-05 the next
generation reproduced the identical failure — declared a standing owner instruction absent from
every repository, having never called `mcp__ctx__search` — and also wrote a comment into the
tracking issue without opening the issue body that describes exactly that failure.

Twice in two days, by two generations, with the tool installed and a preflight check
guaranteeing it. That is why the criteria are written down instead of assumed, and it is the
same lesson as a commit from this history: a tool that is only described does not get called.
