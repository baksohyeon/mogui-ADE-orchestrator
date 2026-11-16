- `scripts/worker-pane-sweep` reads a mid-turn Claude Code worker's current status line (a verb,
  an ellipsis, then a parenthesized elapsed time with a middle-dot separator, e.g. "Sauteing...
  (1h 15m 48s, then a middle dot, then 182.4k tokens)") as `working`, even when an
  always-rendered, often-empty input line sits right below it. The shape is matched a few lines
  above the pane's last prompt line rather than across the whole captured frame, so a copy of
  the same shape further back in scrollback, above a genuinely idle prompt, still reads `idle`.
  Fixes #321.
