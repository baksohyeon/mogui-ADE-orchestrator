#!/usr/bin/env bash
# WRITES: this script appends to the ledger itself. It is the only writer.
# (Contrast: compaction-probe.sh only instructs an agent; context-quality-sampler.sh only prints.)
#
# Append and summarize E12 context-quality recall records.
#
# CONTEXT_QUALITY_LOG is REQUIRED and has no default. A default seat path would let a
# seat that forgot to set it write silently into another seat's ledger — that failure
# actually happened (2026-08-10, three-seat measurement round). Failing is better.
set +e

if [ -z "${CONTEXT_QUALITY_LOG:-}" ]; then
  printf 'CONTEXT_QUALITY_LOG is required and has no default.\n' >&2
  printf 'set it to this seat ledger, e.g. CONTEXT_QUALITY_LOG=$HOME/.local/state/<seat>/context-quality.jsonl\n' >&2
  exit 3
fi
LEDGER_PATH="$CONTEXT_QUALITY_LOG"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'python3 unavailable\n' >&2
  exit 1
fi

if [ "${1:-}" = "--summary" ]; then
  LEDGER_PATH="$LEDGER_PATH" python3 <<'PY'
import collections
import datetime as dt
import json
import os

ledger_path = os.environ["LEDGER_PATH"]
now = dt.datetime.now(dt.timezone.utc)
cutoff = now - dt.timedelta(days=7)


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


records = []
if os.path.exists(ledger_path):
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_time(record.get("ts"))
            if ts is not None and ts >= cutoff:
                records.append(record)

events = collections.Counter(str(record.get("event", "<missing>")) for record in records)
models = collections.Counter(str(record.get("model", "<missing>")) for record in records)
recall_values = collections.defaultdict(collections.Counter)
loss_records = 0
proposed_respawn = 0

for record in records:
    recall = record.get("recall")
    if isinstance(recall, dict):
        for key, value in recall.items():
            recall_values[key][json.dumps(value, ensure_ascii=False, sort_keys=True)] += 1
    loss_notes = record.get("loss_notes")
    if isinstance(loss_notes, list) and loss_notes:
        loss_records += 1
    if record.get("proposed_respawn") is True:
        proposed_respawn += 1

print("# Context Quality Summary")
print(f"window: last 7 days")
print(f"ledger: {ledger_path}")
print(f"records: {len(records)}")
print("events: " + (", ".join(f"{key}={value}" for key, value in sorted(events.items())) or "none"))
print("models: " + (", ".join(f"{key}={value}" for key, value in sorted(models.items())) or "none"))
print(f"records_with_loss_notes: {loss_records}")
print(f"proposed_respawn_true: {proposed_respawn}")
print("recall:")
if not recall_values:
    print("- none")
else:
    for key in sorted(recall_values):
        values = ", ".join(
            f"{value}={count}" for value, count in sorted(recall_values[key].items())
        )
        print(f"- {key}: {values}")
PY
  exit $?
fi

if [ "$#" -ne 1 ]; then
  printf 'usage: %s --summary | %s '\''<recall-json>'\''\n' "$0" "$0" >&2
  exit 2
fi

RECORD_JSON="$1" LEDGER_PATH="$LEDGER_PATH" python3 <<'PY'
import datetime as dt
import json
import os
import sys

ledger_path = os.environ["LEDGER_PATH"]
raw = os.environ["RECORD_JSON"]


def fail(message):
    print(f"schema validation failed: {message}", file=sys.stderr)
    sys.exit(2)


try:
    record = json.loads(raw)
except json.JSONDecodeError as exc:
    fail(f"invalid JSON: {exc.msg}")

if not isinstance(record, dict):
    fail("top-level value must be an object")

required = ["ts", "session", "event", "model", "recall", "loss_notes", "proposed_respawn"]
missing = [key for key in required if key not in record]
if missing:
    fail("missing fields: " + ", ".join(missing))

for key in ["ts", "session", "event", "model"]:
    if not isinstance(record.get(key), str) or not record[key]:
        fail(f"{key} must be a non-empty string")

try:
    dt.datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
except ValueError:
    fail("ts must be ISO-8601 parseable")

if record["event"] not in ("compact", "respawn"):
    fail("event must be compact or respawn")

if not isinstance(record.get("recall"), dict):
    fail("recall must be an object")

if not isinstance(record.get("loss_notes"), list):
    fail("loss_notes must be an array")

if not all(isinstance(item, str) for item in record["loss_notes"]):
    fail("loss_notes entries must be strings")

if not isinstance(record.get("proposed_respawn"), bool):
    fail("proposed_respawn must be boolean")

directory = os.path.dirname(ledger_path)
if directory:
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        print(f"ledger directory unavailable: {directory}: {exc}", file=sys.stderr)
        sys.exit(4)
if directory and not os.path.isdir(directory):
    print(f"ledger directory missing after create: {directory}", file=sys.stderr)
    sys.exit(4)

try:
    fh = open(ledger_path, "a", encoding="utf-8")
except OSError as exc:
    print(f"ledger not writable: {ledger_path}: {exc}", file=sys.stderr)
    sys.exit(4)
with fh:
    fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    fh.write("\n")

print(f"appended: {ledger_path}")
PY
