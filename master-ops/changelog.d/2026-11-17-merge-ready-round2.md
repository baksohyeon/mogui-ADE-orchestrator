- `scripts/merge-ready` round 2 (#330), fixing two ways the master's own review found for a PR
  author to reach exit 0 on their own say-so: the `rate-limited:` line in the PR body no longer
  exempts any required check (a required check never skips, from anywhere); and exit 0 now needs
  a separate `merge-ready-master-pass sha=... critical=0 important=0` marker the master posts
  after its own review, never the worker's own `merge-ready-worker-pass` pre-check marker, since
  master and worker share one GitHub account and the marker name is a convention, not an identity
  check this script can verify (documented in `docs/runbooks/merge-ready.md`).
- New `config/merge-ready-bots.txt` roster (starting with `cubic-dev-ai` and `coderabbitai`):
  each listed bot must show a review or a recent comment on the exact head, or `merge-ready` is
  not ready, naming the bot; a genuine rate-limit notice from that bot ("review limit reached" /
  "rate limited by", case-insensitive) posted at or after the head commit's own timestamp counts
  as covering it. An empty required-checks list (`gh pr checks --required` returning `[]`) and an
  empty bots file now both fail closed instead of reading as "nothing to measure, so pass".
- The stop list and the `--contract` writes-scope check now run once early, right after the head
  sha is resolved and before the tarball test re-run starts; when either already decides "ask",
  the test re-run (and every later measurement) never runs at all, and the summary line says so.
  Added to the stop list: CI workflow and CODEOWNERS definitions, `.claude/**`, the redaction
  scanner and its allowlist, `hooks/pre-push`, succession and bootstrap code, root
  `CLAUDE.md`/`AGENTS.md`, `master-ops/MANIFEST.json`, onboarding and skills content, and
  `scripts/test-merge-ready.sh` itself, each checked against `origin/main`'s real file tree.
- `gh api ... --paginate --slurp` for the files and comments fetches, flattened back into one
  array by the script itself rather than relying on `--paginate` alone to combine pages; every
  `python3 -c` call now takes its file paths as `sys.argv` instead of interpolating them into the
  source text, and the repeated `${TMP_DIR}/pr-early*.err`-shaped literals are named variables.
