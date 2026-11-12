# Tracker card gap hook (`scripts/hooks/bd-gap-warn.sh`)

Append the new hook to the existing `UserPromptSubmit` array in the workspace
`.claude/settings.json`. Keep one merged settings object and one array key:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{{OPS_REPO}}/scripts/hooks/orch-inbox-warn.sh\"",
            "statusMessage": "Checking orchestration inbox"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{{OPS_REPO}}/scripts/hooks/bd-gap-warn.sh\"",
            "statusMessage": "Checking dispatch tracker cards"
          }
        ]
      }
    ]
  }
}
```

On each prompt, the hook reads today's register rows from the dispatch ledger
using KST calendar boundaries. If one or more rows have no `card`, it prints
`[bd-gap] today: N dispatches without a card · M in_progress`; otherwise it is
silent. `M` is the current count returned by `bd list --status=in_progress
--json`, and unavailable tracker state fails open as zero. Older ledger rows
without card fields are included in the gap count when they fall on today.
