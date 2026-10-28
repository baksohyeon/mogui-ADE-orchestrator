CI pins all three gates runners to CPython 3.13.17 instead of floating `"3.12"`, which let each
runner's preinstalled patch diverge (3.12.15 on ubuntu, 3.12.10 on macOS and Windows) and run "the
same tests" on different interpreters. A `Print interpreter` step after each `actions/setup-python`
call puts `python -VV` in every job log. `.python-version` at the repository root carries the same
pin for local use. README's prerequisites sentence keeps the 3.11 floor for contributors and points
to `.python-version` for the CI patch.
