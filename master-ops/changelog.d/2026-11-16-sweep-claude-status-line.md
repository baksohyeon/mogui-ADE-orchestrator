- `scripts/worker-pane-sweep` reads a mid-turn Claude Code worker's current status line (a verb,
  an ellipsis, then a parenthesized elapsed time with a middle-dot separator, e.g. "Sauteing…
  (1h 15m 48s · ↓ 182.4k tokens)") as `working`, even when an always-rendered, often-empty input
  line sits right below it. Only the single line directly above that input line counts (skipping
  at most one box-drawing separator line), not a wider scrollback window: a finished turn
  overwrites the same screen row with a past-tense, ellipsis-free summary, so a copy of the
  status-line shape quoted elsewhere in the pane, above a genuinely idle prompt, still reads
  `idle`. Fixes #321.
