# feat: restore tracker work after compact recall

The compact probe records its session, log offset, and state marker. A paired
PostToolUse and UserPromptSubmit hook waits for the matching recall record,
restores the Role State, tracker work, decisions, live panes, repository status,
and configured seat lines once, and records a bounded recall skip when the
continuation does not append the record. The probe now prints a runnable
`CONTEXT_QUALITY_LOG=... context-quality-log.sh ...` command.
