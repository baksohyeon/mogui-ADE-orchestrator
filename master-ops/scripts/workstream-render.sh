#!/bin/bash
# Render the dispatch ledger into a human-readable workstream (owner feedback
# 2026-08-03: gate/worker activity was a black box). Reads only; the ledger
# stays the machine record. Usage: workstream-render.sh [YYYY-MM-DD]
LEDGER=~/.mogui/dispatch-ledger.jsonl
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
