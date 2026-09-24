# PR Body Narrative Section Check

`scripts/pr-body-check` validates the four required narrative sections in a pull request body:

- `Problem`
- `Why this approach`
- `What this changes`
- `Expected effect`

For each heading, the script reports one verdict:

- `missing heading`
- `present but empty`
- `present but unmodified template guidance`
- `filled`

## Usage

```bash
scripts/pr-body-check <pr-number>
```

In repositories without a configured `origin`, pass an explicit repo:

```bash
scripts/pr-body-check <pr-number> --repo owner/repo
```

## Exit Codes

- `0`: all four sections are `filled`.
- `1`: one or more sections are missing, empty, or still template guidance.
- `2`: runtime or usage error (for example, cannot fetch PR body or template).

## Honest Limit

This check measures whether each section was written, not whether the content is correct. A section can pass as `filled` while still being inaccurate, so reviewers still need to judge truth and evidence.
