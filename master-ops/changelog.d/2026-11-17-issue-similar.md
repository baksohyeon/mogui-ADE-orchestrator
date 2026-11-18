- Dedupe check for new issues (new feature, milestone E). `master-ops/scripts/issue-similar`
  searches `gh search issues` for likely duplicates of a title and body before filing: no
  GitHub Action, no secret, no API key, and no model call, by owner choice over the
  `claude-code-action`/`/dedupe` and `pullfrog` patterns seen elsewhere. It builds several
  small queries from backtick spans, quoted strings, slash-paths, and a bounded set of
  distinctive plain words (GitHub's search ANDs bare terms, so a single query built from a
  whole reworded title would match nothing), scores every candidate locally (a shared
  path/quoted string outweighs a shared plain word), and exits `0` below threshold, `3` at
  or above it, `1` on any `gh` failure, timeout, or unparseable response (never `0` on a
  failure). `master-ops/docs/runbooks/issue-dedupe.md` covers filing-time use and a weekly
  sweep over open issues, paced to stay under `gh`'s 30-requests-per-minute search limit.
  `master-ops/scripts/test-issue-similar.sh` exercises the whole thing against a stubbed
  `gh`, so none of it ever makes a real network call.

  Out of scope here, by the owner's instruction: wiring the check into
  `rules/standing-rules.md` or `scripts/dispatch` so filing is checked automatically, which
  waits on #338 (already changing both files).
