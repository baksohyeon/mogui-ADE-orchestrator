---
status: active
---

# Finding Duplicate Issues Before Filing, and a Weekly Sweep

`scripts/issue-similar` searches `gh` for issues that may already cover a title and body,
using lexical search only: no GitHub Action, no secret, no API key, and no model call. See
"Why these tools" in the repository README for the five questions that choice answers.

## Usage

```bash
scripts/issue-similar --repo <owner/name> --title "<text>" [--body-file <file>] \
    [--state open|all] [--limit N] [--exclude N] [--json]
```

It builds a handful of search queries from the title and body (backtick spans, quoted
strings, and slash-paths first, then a bounded set of distinctive plain words, up to
`--max-code-terms` and `--max-words` of each), runs each through `gh search issues`, and
scores every issue returned against that same bounded term set: a shared path, script name,
or quoted string is worth 3 points, a shared plain word 1, and anything scoring 3 or more is
printed as a likely duplicate. At most five
candidates print by default (`--limit` to change that); `--json` emits the same ranking as
structured data for the sweep below. `--exclude <n>` drops that issue number from the
results, the mechanism the sweep needs so an issue never reports itself as its own
duplicate.

### Exit codes

| Exit code | Condition | Response shape that triggers it |
| --- | --- | --- |
| `0` | The run completes with no ranked candidate at or above the threshold. | `gh repo view <repo> --json name` returns an object with a nonempty string `name`; every `gh search issues` call returns a JSON list; every returned issue has a positive integer `number`; and the highest remaining score is below 3. |
| `1` | `--body-file` cannot be read. | Opening the named file, or reading stdin for `--body-file -`, raises `OSError`. |
| `1` | The title and body produce no usable search terms. | Code terms, words, and the qualifier filter leave no query, so no GitHub response is requested. |
| `1` | Repository validation fails. | `gh repo view <repo> --json name` times out, fails, returns nothing, returns invalid JSON, or returns JSON that is not an object with a nonempty string `name`. |
| `1` | An issue search fails. | `gh search issues` times out, fails, returns nothing, returns invalid JSON, or returns JSON that is not a list. |
| `1` | One or more returned issues are skipped as malformed. | A search JSON list contains an issue whose `number` is not a positive integer; the skipped count is written to stderr. |
| `2` | Argument parsing or a value validation fails. | A required flag is missing, a choice or integer is invalid, or `--limit`, `--query-delay`, `--max-words`, or `--max-code-terms` fails its range check; no external response is required. |
| `3` | At least one ranked candidate reaches the duplicate threshold. | The valid response shapes above produce a highest remaining score of 3 or more, and the candidates are printed as a table or JSON. |

## (a) Before filing an issue

Run `issue-similar` with the title (and body, via `--body-file`, if drafted already) before
`gh issue create`. On exit `3`: read the printed candidates, and either comment on the
existing issue instead of filing, or file the new issue and link the near match in its body.
On exit `0` or `1`, follow the exit code above; a `1` means the check did not run to
completion, not that nothing matched. Every issue filed this way carries
`--assignee` for the repository maintainer (in this template, `baksohyeon`); an installation
should change that value to its own maintainer.

## (b) Weekly sweep

The master runs this, or dispatches it, once a week:

1. List every open issue's number, title, body, and assignees (`gh issue list --state open
   --limit 1000 --json number,title,body,assignees`; the default limit is 30, which silently
   drops older issues once the repository has more open issues than that).
2. For each one, run `issue-similar --repo <owner/name> --json --exclude <its own number>`
   (the same repository as step 1) with that issue's own title as `--title` and its own body
   piped in via `--body-file -`, searching the others.
   An exit `1` or `2` is a failed check for that issue, not "no duplicates found"; name it in
   the sweep's own report instead of folding it into the no-duplicate table.
3. Collect every pair that crossed the threshold into a short table: issue, candidate,
   score, matched terms.
4. List every open issue whose `assignees` came back empty in step 1, in its own short
   table (issue, title): a second, unrelated kind of gap the same sweep surfaces for free.
5. The master reads both tables: closes a duplicate only with a comment linking the
   survivor, never a silent batch close, and assigns an unassigned issue or says why it
   stays unassigned.

Pacing: GitHub's search endpoint allows 30 requests per minute, and one `issue-similar`
call can itself make several (`--max-words` default 4 plus `--max-code-terms` default 3).
Every query, including the last one in a run, is followed by a `--query-delay` sleep (2.0s
by default), so back-to-back invocations in the sweep's own loop are paced the same as
queries inside one invocation. Run the sweep sequentially, issue by issue, and do not lower
`--query-delay` to speed it up; on a 24-issue repository the sequential pacing takes a few
minutes, which is the right trade against a rate-limited `gh` call turning into a false
"failure, not duplicate" read.

## Honest limits

This is lexical overlap, not semantic understanding: two issues about the same bug
described in unrelated words score low, and the threshold (3 points: one shared path/quoted
string, or three shared plain words) is a tuned heuristic, not a guarantee. Common
repository boilerplate ("follow-ups", "from #NNN review", "dispatch") scores as an
ordinary shared word like any other; a title built mostly from that vocabulary scores
indistinguishable near-matches against several unrelated issues, which is why path and
quoted-string terms are weighted higher; a title and body with neither will fall back to
nothing but plain-word overlap. `gh search issues`'s own relevance ranking is not used for
scoring, only as a candidate source: every printed score is this script's own count,
matched directly against the fetched issue's title and body, so it does not change if
GitHub's ranking does. A short non-English title (a 2-to-3-word Korean title, say) can still
land below the threshold even against its own exact duplicate, since each matched word is
worth only 1 point and there may be only two or three of them to match; the fallback that
keeps the words at all (instead of scoring every candidate 0) only closes part of that gap.
A bare one-segment slash phrase (`and/or`, `CI/CD`, a date like `2026/11/17`) is deliberately
not scored as a path or script name, since real paths and script names in this repository
nearly always have a segment longer than four characters, but an unusually short real path
component could in principle fall on either side of that cutoff. A plain word matches
whole-word only (`auth` does not match `oauth`, `base` does not match `database`); a
backtick, quoted, or path term still matches as a substring.

Wiring this into `rules/standing-rules.md` or `scripts/dispatch` so filing is checked
automatically is a deliberate follow-up, after #338 lands (that PR is already changing both
files).
