# Error and logging boundaries

The hook-fire log and event log remain separate. Existing hooks keep writing
`~/.mogui/hook-fire-log.jsonl` with its stable fields (`ts`, `hook`, `event`,
`cwd`, `runtime_hint`, `session_kind`) so `scripts/hook-coverage-report` remains
compatible. New decision emitters write `~/.mogui/event-log.jsonl` instead.

## Standard event schema

Each event is one JSON line with fixed, value-free metadata: `ts`, `level`,
`event`, `component`, `session_kind`, `runtime_hint`, `outcome`, `evidence`,
`reason`, `command_class`, `target_scope`, and `tool_kind`. `event` is a logical event name, not a hook lifecycle label. Raw
commands, absolute paths, credentials, and other values are forbidden; emit
command names and target classifications only.

## Bash hook emitter

`mg_emit` is fail-open: directory creation and append failures must never change
the guard decision.

```bash
mg_emit() {
  local level="$1" event="$2" outcome="$3" reason="$4"
  local command_class="${5:-}" target_scope="${6:-}"
  # Serialize all fields with json.dumps; append failure is always || true.
  python3 ... "$level" "$event" "$outcome" "$reason" "$command_class" "$target_scope" \
    >> "$HOME/.mogui/event-log.jsonl" 2>/dev/null || true
}
```

The product-path guard uses the logical event name `product_path_guard` and
records only classes such as `guarded_target`, `read_only_command`, and
`unresolved_target`.
