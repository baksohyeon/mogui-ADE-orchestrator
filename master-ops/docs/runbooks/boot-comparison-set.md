---
status: active
---

# Boot comparison set

At each succession, compare the current session against the inherited handoff before
appending lineage. Record measured values and the instruments used; an entry without
measured values is incomplete. A successful return code is not the measurement.

## Required comparisons

| Compare | Instrument | Required result |
| --- | --- | --- |
| workspace placement and sole ownership | `harness-selfcheck.sh` | report the verdict and exit status |
| deployed workspace card | `harness-selfcheck.sh` | report match or drift |
| duplicate sessions | `master-succeed check-duplicates` | report the result and scope |
| configured and observed model | `model-drift-audit` | report model, transcript count, and exit status |
| predecessor state | process inspection and pane read | distinguish live, idle, start-screen, limited, and gone |
| runtime configuration | `config/instance-runtime.json` and the launching environment | report measured values or `unconfigured` |
| template promotion | `git diff` against `origin/main` | compare names and content, not counts |

When an instrument answers a different question than the one needed, record that gap and
run the probe that answers the needed question. Resolve document references as real links
and confirm each target exists relative to the containing file.

## Lineage entry minimum

Each entry records the generation, parent and successor session references, inherited role,
open tracks, verification result, measured comparison values, and any context-loss or
repeated-question metrics. Session identifiers and process details are instance history;
they remain in the private operations record and are not copied into this public template.
