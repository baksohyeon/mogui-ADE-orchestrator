# master-ops template changelog

The version in `TEMPLATE-VERSION` is the version of this template. Onboarding
copies it into the operations repository it generates, so an installation can
say which version it came from.

A generated operations repository is a copy. It does not update when this
template does. To bring an existing installation forward, read the entries
between its version and the current one and apply what applies. Local edits win
where they conflict; that is the point of a copy.

Check what an installation is on:

```console
$ grep 'Template version' docs/MASTER-OPERATIONS.md
```

## 1

First versioned template. Everything before this shipped unversioned, so an
installation created earlier will not carry a version line. Add one by hand
after applying whatever entries look relevant, and treat its starting point as
unknown.

Notable content at this version:

- Section 1 states that a coordinated repository's agent instruction file does
  not declare the master's role. Added after a first-generation master read a
  product repository's instruction file and reported itself as that
  repository's paired developer.
- Section 3 says a boot measurement is a snapshot and names the points to
  re-measure at, with the whole-transcript audit for changes a recent-turn
  probe cannot see.
- Step 5 of onboarding wires the issue tracker to the workspace root, where the
  master actually runs, and verifies from there.
- Step 7.5 offers the skill layer and prints install commands without running
  them.
