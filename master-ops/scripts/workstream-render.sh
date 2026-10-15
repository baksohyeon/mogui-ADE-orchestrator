#!/bin/bash
# Render the dispatch ledger into a human-readable workstream (owner feedback
# 2026-08-03: gate/worker activity was a black box). Reads only; the ledger
# stays the machine record. Usage: workstream-render.sh [YYYY-MM-DD]
# Testability seam (docs/runbooks/host-harness-inventory.md): MOGUI_STATE_DIR
# redirects this dispatch's mutable state off ~/.mogui without touching $HOME.
# Unset or empty keeps today's default.
if [ -n "${MOGUI_STATE_DIR:-}" ]; then
  case "$MOGUI_STATE_DIR" in
    /*) [ -d "$MOGUI_STATE_DIR" ] && STATE_DIR_OK=1 || STATE_DIR_OK=0 ;;
    *) STATE_DIR_OK=0 ;;
  esac
  if [ "$STATE_DIR_OK" != 1 ]; then
    echo "✗ MOGUI_STATE_DIR must be an absolute path to an existing directory: $MOGUI_STATE_DIR" >&2
    exit 1
  fi
  STATE_DIR="$MOGUI_STATE_DIR"
else
  STATE_DIR=~/.mogui
fi
LEDGER="$STATE_DIR/dispatch-ledger.jsonl"
DAY="${1:-$(date +%F)}"
python3 - "$LEDGER" "$DAY" <<'EOF'
import json, sys, datetime
ledger, day = sys.argv[1], sys.argv[2]
rows = []
for line in open(ledger):
    try: e = json.loads(line)
    except Exception: continue
    ts = e.get("ts")
    if not ts: continue
    d = datetime.datetime.fromtimestamp(ts)
    if d.strftime("%F") != day: continue
    rows.append((d, e))
print(f"# Dispatch workstream — {day}\n")
print("| time | kind | decision | runtime | model (tier) | agents | cost proxy | job/task | note |")
print("|---|---|---|---|---|---|---|---|---|")
for d, e in rows:
    kind = "register" if e.get("job_id") else "check"
    model = e.get("model") or e.get("model_declared") or "?"
    tier = e.get("tier", "?")
    job = e.get("job_id") or ""
    task = e.get("orchestration_task") or ""
    note_bits = []
    if e.get("model_measured"): note_bits.append(f"measured={e['model_measured']}")
    if e.get("warnings"): note_bits.append("warn=" + ",".join(e["warnings"]))
    if e.get("reason") not in (None, "OK"): note_bits.append(e["reason"])
    if e.get("tier_override_reason"): note_bits.append(f"override: {e['tier_override_reason']}")
    print(f"| {d.strftime('%H:%M')} | {kind} | {e.get('decision','?')} | {e.get('runtime','?')} "
          f"| {model} ({tier}) | {e.get('n_agents','')} | {e.get('cost_proxy','')} "
          f"| {job or task} | {'; '.join(note_bits)} |")
print(f"\n{len(rows)} ledger entries. Contracts live in the ops repository under contracts/; "
      "probe commands are recorded per register entry in the ledger.")
EOF
