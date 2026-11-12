# Tracker card gap hook (`scripts/hooks/bd-gap-warn.sh`)

Add this block to workspace `.claude/settings.json` under `hooks`, alongside
the `orch-inbox-warn.sh` UserPromptSubmit block:

```json
{
  "UserPromptSubmit": [
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
```

On each prompt, the hook reads today's register rows from the dispatch ledger
using KST calendar boundaries. If one or more rows have no `card`, it prints
`[bd-gap] today: N dispatches without a card · M in_progress`; otherwise it is
silent. `M` is the current count returned by `bd list --status=in_progress
--json`, and unavailable tracker state fails open as zero. Older ledger rows
without card fields are included in the gap count when they fall on today.
