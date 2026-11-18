# Redaction scan (public-release guard)

Prevents secrets and internal identifiers from leaving the machine on `git push`.

## Script

```bash
# Full tracked tree (CI / manual audit)
scripts/redaction-scan.sh

# Staged index only
scripts/redaction-scan.sh --staged

# Commits about to be pushed, and those commits' messages (pre-push)
scripts/redaction-scan.sh --range "$remote_sha..$local_sha"

# Commit messages for any range, in any mode
scripts/redaction-scan.sh --commit-messages "$remote_sha..$local_sha"
```

- **Fail-closed:** any match that is not exempted → exit 1.
- **Engine:** gitleaks does the matching. The script scopes the scan to tracked content, scans commit messages, translates the organization rules, and reports what it covered.
- **Tools:** `bash`, `git`, `python3`, and `gitleaks` on `PATH`. The former `rg` and `grep -E` paths are gone.
- **Committed rules:** `config/gitleaks.toml`, extending gitleaks' maintained default set.
- **Exemptions:** a `.gitleaksignore` fingerprint for one finding, or an allowlist block in `config/gitleaks.toml` for a class. The old `scripts/redaction-allowlist.txt` format is retired, and a file still holding entries in it exits 2 rather than being ignored.

### Scope is stated in the output

A green line that does not name its scope cannot be told apart from a full audit, so every run says what it read:

```console
$ scripts/redaction-scan.sh
redaction-scan: OK: 0 findings (mode=tracked, files=144, commit-messages=not-scanned, org-rules=10, org-rules-source=workspace-root, profile=export, export-only-skipped=0)
```

`commit-messages=not-scanned` is the honest reading in tracked and staged modes. gitleaks does not read commit messages: a key present only in a message returns no findings while the same key in file content is found. That is measured, and it is why the message loop lives in this script.

`org-rules=N` counts rules actually loaded into the run, not lines the file happens to hold.
`org-rules-source` names whether the file came from the environment, the workspace root, or the legacy home path. `profile=export` is the safe default and loads every valid rule. `profile=internal` skips rules whose id starts with `workspace_` and reports them as `export-only-skipped=N`.
`pre-existing=N` and `stale-fingerprints=N` are explained below.

### `--range` judges the lines the range itself touches

A full-tree or staged scan flags every match on the file, full stop. `--range` is different: a finding on a line the range adds or changes still blocks, exactly as before, but a finding on a line already present on the range's base prints as a pre-existing warning (count, file, line, rule) and does not affect the exit code. Measured case: a lineage file whose append added zero new findings was blocked by 114-115 that were already there before this change; `--range` no longer does that.

```console
$ scripts/redaction-scan.sh --range origin/main..HEAD
redaction-scan: WARNING — 1 pre-existing finding(s) outside this range's added lines (not blocking in range mode, still exempt only via .gitleaksignore):
  notes.md:40  [internal_host] Internal or corp hostname  :: ci.cor…
redaction-scan: OK: 0 findings (mode=range, files=3, ..., pre-existing=1, ...)
```

Every finding row records whether it came from file content or a commit message. Only file-content rows consult the added-lines map. A commit-message row keeps blocking even when a later empty file happens to use its `commit:<12 hex>` display label, so the path text cannot change its origin.

The judgment only ever makes a file's findings *more* lenient, never adds scope: a file the range diff cannot be read for safely (an unreadable or empty diff for a file the range lists as changed, most commonly a binary file) fails the whole scan (exit 2) rather than guessing either way, and a file the working tree no longer matches at the range's own tip is left out of the judgment entirely, so every finding in it stays blocking. Full-file and staged modes never consult this at all.

### Stale `.gitleaksignore` fingerprints

A file fingerprint is `path:rule:line`. gitleaks 8.30.1 has no content-based fingerprint (confirmed against its own source, `detect/detect.go`: the fingerprint is built from the file path, rule id, and start line alone), so adding a line above an exempted finding shifts it to a new fingerprint, and the old one silently stops matching anything, which is not visible on its own: the finding it used to cover either reappears as a live, blocking finding (safe, if noisy) or the fingerprint simply goes unused forever (invisible drift). A commit-message fingerprint has the same `rule:line` shape but no file, so it reads as `:rule:line`.

In tracked-mode runs, when `.gitleaksignore` holds entries, the scan reruns the same files with ignore-matching disabled, and, when this run also scanned commit messages, those same commits the same way, then reports any listed fingerprint that now matches nothing live:

```console
redaction-scan: WARNING — 2 .gitleaksignore fingerprint(s) match no current finding (stale; the exempted line likely shifted or was removed); review .gitleaksignore:
secret.txt:aws_access_key:1
secret.txt:aws-access-token:1
```

This never fails the scan on its own: a fingerprint going stale because its line really did move with the secret still present already fails the normal pass above, on its own merits. The unfiltered reports in this block are used only to collect live fingerprints, so their paths and origins never enter the blocking or pre-existing classification. Staged and range-mode runs skip this check, since they only ever touch a subset of files and would misreport an untouched file's still-valid fingerprint as stale. A run without `--commit-messages` leaves every commit-message-shaped (`:rule:line`) entry unchecked for the same reason: it never rescanned the commits that would confirm one way or the other.

### Organization-specific rules (`REDACTION_EXTRA_PATTERNS`)

Real company, product, and personal identifiers are deliberately **not** committed to the
scanner: this repository is public, so hardcoding them would leak what the scan protects.
Supply them per checkout instead.

```bash
# keep this file out of version control; the workspace root is one directory above the repository
cat > ../.redaction-extra.txt <<'RULES'
company_acme|Company identifier acme|(?i)acme
personal_handle|Personal handle|(?i)(?<![A-Za-z0-9_])myhandle(?![A-Za-z0-9_])
RULES

# This explicit path is optional. Without it, the scan checks the workspace
# root file first, then ~/.config/redaction-extra.txt.
export REDACTION_EXTRA_PATTERNS=../.redaction-extra.txt
```

Each line is `id|description|regex`. Blank lines and `#` comments are ignored. Only the first two pipes separate fields, so a regex may contain a pipe.

Both `redaction-scan.sh` and `redaction-inventory` use the same lookup order. Set `REDACTION_WORKSPACE_ROOT` when the main checkout and linked worktree layout cannot identify the workspace root. Inventory output includes `org-rules-source`, `profile`, and `export-only-skipped` so its coverage statement stays aligned with the scanner.

The file is translated into a gitleaks config that extends the committed one, so this format is unchanged and no checkout converts anything. A line that is malformed, or whose regex does not compile, is skipped with a warning that counts it rather than dropped in silence.

Use `REDACTION_PROFILE=internal` in the operations repository's own pre-push hook and steward gates when workspace-local rules should be excluded from those private scans. The public template and export checks use `REDACTION_PROFILE=export`, which is also the default; credentials and generic rules behave the same in both profiles.

When no such rules are loaded, the scan prints a warning to stderr and still exits 0, so a
green result means "generic patterns only" — not "fully audited". In CI or before a public
push, make that gap fail instead:

```bash
bash scripts/redaction-scan.sh --require-extra    # or REDACTION_REQUIRE_EXTRA=1
```

Exit codes: `0` clean, `1` findings, `2` cannot decide — `gitleaks` missing, required organization rules missing, retired allowlist entries present, or a usage error.

## What this scan does not cover

The scan reads repository content. It does not read pull request titles or bodies, review comments, release notes, or issue text, because none of that is in the repository. Those are also where internal names arrive most easily, since they are prose rather than code. Grep outgoing text before posting it.

`scripts/redaction-inventory` answers the inverse question, which tokens no rule covers, and has no gitleaks equivalent. It uses the same rules lookup and profile filter as the scanner; under `internal`, `workspace_` rules are counted as `export-only-skipped` and excluded from coverage.

### What it flags

| Class | Examples |
|-------|----------|
| Secrets | PEM private keys, `AKIA…`, `ghp_`/`gho_`, Slack `xox…`, `sk-` / `sk-ant-`, `Bearer …`, `password=` / `api_key=` assignments, exported secret env vars |
| Internal IDs | prior-redact company/personal codenames (rules `company_*` / `personal_*`), Jira `HF-*`, Slack URLs, `*.internal` / `*.corp` hosts, RFC1918 IPs |
| Home paths | `/Users/<name>/…` except synthetic fixture prefixes (`/Users/dev/`, …) |

Document / test placeholders (`example.com`, `YOUR_API_KEY`, `sk-test-…`, AWS example key id, etc.) are ignored.

## Wire as `pre-push` hook

This repo has no husky/lefthook. Use a local git hook (not committed under `.git/`):

```bash
# from repo root
cat > .git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
# stdin: <local_ref> <local_sha> <remote_ref> <remote_sha>
zero=0000000000000000000000000000000000000000
while read -r local_ref local_sha remote_ref remote_sha; do
  if [[ "${local_sha}" = "${zero}" ]]; then
    continue   # delete
  fi
  if [[ "${remote_sha}" = "${zero}" ]]; then
    range="${local_sha}"
    # new branch: scan all commits reachable from local tip not on main default — fall back to full tree
    scripts/redaction-scan.sh || exit 1
  else
    scripts/redaction-scan.sh --range "${remote_sha}..${local_sha}" || exit 1
  fi
done
# Always also scan the full tree at tip (catches un-changed but still-tracked leaks)
scripts/redaction-scan.sh
HOOK
chmod +x .git/hooks/pre-push
```

Optional shared hook path (team machines):

```bash
git config core.hooksPath .githooks   # if you later commit a .githooks/pre-push
```

## Manual audit before first public push

```bash
scripts/redaction-scan.sh -v
# History rewrite (filter-repo/BFG) is separate — this scanner only sees the tip tree / chosen range.
```

## Allowlisting

Only after confirming the hit is intentional synthetic content:

```
# scripts/redaction-allowlist.txt
tests/fixtures/demo.env:12
PREFIX:/Users/dev/
```

Never allowlist a real secret; rotate it and remove it from history instead.
