# Release runbook

This runbook describes one orchestrator release cut under `MAJOR.MINOR.BUILD`.
MAJOR and MINOR are owner-managed milestones; automation must never bump them.

## 1) Sync and derive the build number

```console
git fetch origin main --tags
build="$(git rev-list --count origin/main)"
version="0.5.${build}"
printf '%s\n' "$version"
```

If the repository is shallow, unshallow first:

```console
git fetch --unshallow origin main --tags
```

## 2) Stage new files before redaction checks

```console
git add -A
```

The scanners read tracked content, so an unstaged new file is invisible.

## 3) Run release gates

```console
PYTHONPATH=src uv run pytest tests -q
./scripts/redaction-scan.sh
if ! ./scripts/redaction-inventory; then rc=$?; [ "$rc" -eq 1 ] || exit "$rc"; fi
```

`redaction-inventory` exit 1 is the normal triage state. Exit 2 means cannot
decide and should block a release cut until resolved.

## 4) Finalize release metadata

- Ensure `CHANGELOG.md` has the release notes for `v0.5.<build>`.
- Verify links and release date text.

## 5) Tagging is owner-approved and manual

Use the command below only after explicit owner approval:

```console
git tag "v0.5.${build}"
```

Never automate tag creation or tag push. Do not push tags unless the owner asks
for that release cut action.
