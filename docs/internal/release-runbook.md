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
bash master-ops/scripts/test-tool-naming.sh
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
- Roll the root changelog's `## [Unreleased]` section into `## [${version}]`:
  `./scripts/changelog-release --roll-root CHANGELOG.md --version "${version}"`.
  The first roll after this change gathers everything recorded since
  `0.4.1` under one version heading, which is the honest record of what
  shipped between those two tags.

## 5) Tagging is owner-approved and manual

Use the command below only after explicit owner approval:

```console
[ -n "${version:-}" ] || exit 1
git tag "v${version}"
```

Never automate tag creation or tag push. Do not push tags unless the owner asks
for that release cut action.

After the owner approves `git push origin "v${version}"`, create the Release from
the pushed tag:

```console
awk -v ver="${version}" 'BEGIN{p=0} $0=="## v"ver{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' master-ops/CHANGELOG.md > "${TMPDIR:-/tmp}/release-notes-v${version}.md" && \
awk -v ver="${version}" 'BEGIN{p=0} $0 ~ "^## \\[" ver "\\] - "{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' CHANGELOG.md >> "${TMPDIR:-/tmp}/release-notes-v${version}.md" && \
gh release create "v${version}" --title "v${version}" --notes-file "${TMPDIR:-/tmp}/release-notes-v${version}.md" --verify-tag --generate-notes
```

A missing `## v${version}` or `## [${version}] - ` section makes its awk line
exit non-zero, and the `&&` stops the step before any Release exists.

The awk line writes `master-ops/CHANGELOG.md`'s `## v${version}` section, where
`scripts/changelog-release` folds each cut's notes, to a temp file for
`--notes-file`. `--verify-tag` refuses the command when the tag is not already
on the remote, so a mistyped or unpushed tag cannot become a Release cut from
the default branch. `--generate-notes` appends the pull request list, grouped
by `.github/release.yml`, under the handwritten notes.

The four tags without a Release (`v0.5.249`, `v0.5.254`, `v0.5.258`,
`v0.5.265`) are back-filled once, oldest first, by the owner, with the
version typed into each command below and `--notes-start-tag` naming the tag
directly before it. A normal cut names no `--notes-start-tag` because its
previous Release is already the latest one.

```console
awk -v ver="0.5.249" 'BEGIN{p=0} $0=="## v"ver{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' master-ops/CHANGELOG.md > "${TMPDIR:-/tmp}/release-notes-v0.5.249.md" && \
gh release create "v0.5.249" --title "v0.5.249" --notes-file "${TMPDIR:-/tmp}/release-notes-v0.5.249.md" --verify-tag --generate-notes --notes-start-tag "v0.5.239"
awk -v ver="0.5.254" 'BEGIN{p=0} $0=="## v"ver{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' master-ops/CHANGELOG.md > "${TMPDIR:-/tmp}/release-notes-v0.5.254.md" && \
gh release create "v0.5.254" --title "v0.5.254" --notes-file "${TMPDIR:-/tmp}/release-notes-v0.5.254.md" --verify-tag --generate-notes --notes-start-tag "v0.5.249"
awk -v ver="0.5.258" 'BEGIN{p=0} $0=="## v"ver{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' master-ops/CHANGELOG.md > "${TMPDIR:-/tmp}/release-notes-v0.5.258.md" && \
gh release create "v0.5.258" --title "v0.5.258" --notes-file "${TMPDIR:-/tmp}/release-notes-v0.5.258.md" --verify-tag --generate-notes --notes-start-tag "v0.5.254"
awk -v ver="0.5.265" 'BEGIN{p=0} $0=="## v"ver{p=1; print; next} p && /^## /{exit} p; END{if (!p) exit 1}' master-ops/CHANGELOG.md > "${TMPDIR:-/tmp}/release-notes-v0.5.265.md" && \
gh release create "v0.5.265" --title "v0.5.265" --notes-file "${TMPDIR:-/tmp}/release-notes-v0.5.265.md" --verify-tag --generate-notes --notes-start-tag "v0.5.258"
```

This step inherits the rule above: tagging and the
Release stay manual and owner-approved.
