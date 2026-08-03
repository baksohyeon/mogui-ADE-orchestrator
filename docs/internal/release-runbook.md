# Release runbook

This runbook describes one orchestrator release cut under `MAJOR.MINOR.BUILD`.
MAJOR and MINOR are owner-managed milestones; automation must never bump them.

## 1) Sync and derive the build number

If the repository is shallow, unshallow first:

```console
if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
  git fetch --unshallow origin main --tags || exit $?
fi
```

Sync origin main and derive the version:

```console
set -e
git fetch origin main --tags
version="$(./scripts/next-version)"
printf '%s\n' "$version"
```

## 2) Stage new files before redaction checks

```console
git add -A
```

The scanners read tracked content, so an unstaged new file is invisible.

## 3) Run release gates

```console
set -e
PYTHONPATH=src uv run pytest tests -q
./scripts/redaction-scan.sh
rc=0
./scripts/redaction-inventory || rc=$?
if [ "$rc" -ne 0 ]; then [ "$rc" -eq 1 ] || exit "$rc"; fi
```

`redaction-inventory` exit 1 is the normal triage state. Exit 2 means cannot
decide and should block a release cut until resolved.

## 4) Finalize release metadata

- Ensure `CHANGELOG.md` has the release notes for `v${version}`.
- Verify links and release date text.

## 5) Tagging is owner-approved and manual

Use the command below only after explicit owner approval:

```console
git tag "v${version}"
```

Never automate tag creation or tag push. Do not push tags unless the owner asks
for that release cut action.
