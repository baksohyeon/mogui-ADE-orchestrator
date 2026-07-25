# Redaction scan (public-release guard)

Prevents secrets and internal identifiers from leaving the machine on `git push`.

## Script

```bash
# Full tracked tree (CI / manual audit)
scripts/redaction-scan.sh

# Staged index only
scripts/redaction-scan.sh --staged

# Commits about to be pushed (pre-push)
scripts/redaction-scan.sh --range "$remote_sha..$local_sha"
```

- **Fail-closed:** any unallowlisted match → exit 1.
- **Tools:** `bash`, `git`, and `rg` (preferred, PCRE2) or `grep -E`.
- **Allowlist:** `scripts/redaction-allowlist.txt` (override with `REDACTION_ALLOWLIST=`).

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
