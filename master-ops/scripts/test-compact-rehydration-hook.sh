#!/usr/bin/env bash
# Contract proof for scripts/hooks/compact-rehydration-hook.sh.
set -u

S="$(cd "$(dirname "$0")" && pwd)"
HOOK="$S/hooks/compact-rehydration-hook.sh"
PROBE="$S/compaction-probe.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

OPS="$T/ops"
STATE="$T/state"
LOG="$T/context-quality.jsonl"
BIN="$T/bin"
TRACKS="$T/tracks.json"
DECISIONS="$T/decisions.json"
PANES="$T/panes.json"
CONFIG="$T/instance-runtime.json"
F=0

ok() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; F=1; }

mkdir -p "$OPS/docs/runbooks" "$STATE" "$BIN"
cat > "$OPS/docs/runbooks/role-state.md" <<'EOF'
Current Role: worker
Role Lock: ENABLED
EOF
cat > "$TRACKS" <<'EOF'
[{"id":"track-recent","title":"recent active track","updated_at":"2099-01-01T00:00:00+00:00"}]
EOF
printf '%s\n' '[]' > "$DECISIONS"
printf '%s\n' '{"result":{"terminals":[{"terminalHandle":"term-worker","name":"worker","status":"running"}]}}' > "$PANES"
cat > "$CONFIG" <<EOF
{"work_layer_extra_lines":[{"label":"seat extra","value":"declared"}]}
EOF
cat > "$BIN/bd" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"--type=decision"* ]]; then
  cat "${DECISIONS_FILE:?}"
else
  cat "${TRACKS_FILE:?}"
fi
EOF
cat > "$BIN/orca" <<'EOF'
#!/usr/bin/env bash
cat "${PANES_FILE:?}"
EOF
chmod +x "$BIN/bd" "$BIN/orca"

run_probe() {
  local session="$1"
  if [ -x "$PROBE" ]; then
    MOGUI_STATE_DIR="$STATE" CONTEXT_QUALITY_LOG="$LOG" \
      bash "$PROBE" <<EOF >/dev/null
{"source":"compact","session_id":"$session"}
EOF
    return
  fi
  # Rendered installs keep compaction-probe instance-owned. Recreate its
  # marker contract here so the hook proof still runs against the rendered
  # template copy.
  python3 - "$STATE" "$LOG" "$session" <<'PY'
import datetime as dt
import json
import os
import sys
from pathlib import Path

state, log, session = map(Path, sys.argv[1:])
pending = state / "compact-pending"
pending.mkdir(parents=True, exist_ok=True)
marker = {
    "compact_time": dt.datetime.now(dt.timezone.utc).isoformat(),
    "log_path": str(log.resolve()),
    "log_offset": log.stat().st_size if log.is_file() else 0,
    "session_id": str(session),
    "post_tool_uses": 0,
}
(pending / session).write_text(json.dumps(marker) + "\n", encoding="utf-8")
PY
}

run_hook() {
  local hook="$1" event="$2" session="$3"
  run_hook_payload "$hook" "$event" "$(printf '{"session_id":"%s","hook_event_name":"%s"}\n' "$session" "$event")"
}

run_hook_payload() {
  local hook="$1" event="$2" payload="$3"
  printf '%s' "$payload" |
    MOGUI_STATE_DIR="$STATE" MOGUI_OPS_REPO="$OPS" \
    MOGUI_INSTANCE_RUNTIME_CONFIG="$CONFIG" \
    CONTEXT_QUALITY_LOG_WRITER="$S/context-quality-log.sh" \
    TRACKS_FILE="$TRACKS" DECISIONS_FILE="$DECISIONS" PANES_FILE="$PANES" \
    PATH="$BIN:$PATH" bash "$hook" "$event"
}

append_record() {
  local session="$1" event="${2:-compact}"
  printf '{"ts":"2099-01-01T00:00:00+00:00","session":"%s","event":"%s"}\n' "$session" "$event" >> "$LOG"
}

marker_exists() { [ -f "$STATE/compact-pending/$1" ]; }

# No marker: silent and exits successfully.
out="$(run_hook "$HOOK" PostToolUse no-marker)"
[ -z "$out" ] && ok "no marker stays silent" || fail "no marker printed: $out"

fast_ms="$(python3 - "$HOOK" "$STATE" "$OPS" "$CONFIG" "$TRACKS" "$DECISIONS" "$PANES" "$BIN" <<'PY'
import json
import os
import subprocess
import sys
import time

hook, state, ops, config, tracks, decisions, panes, bin_dir = sys.argv[1:]
payload = json.dumps({"session_id": "no-marker", "hook_event_name": "PostToolUse"})
environment = {
    **os.environ,
    "MOGUI_STATE_DIR": state,
    "MOGUI_OPS_REPO": ops,
    "MOGUI_INSTANCE_RUNTIME_CONFIG": config,
    "TRACKS_FILE": tracks,
    "DECISIONS_FILE": decisions,
    "PANES_FILE": panes,
    "PATH": f"{bin_dir}:{os.environ['PATH']}",
}
started = time.perf_counter()
for _ in range(20):
    result = subprocess.run(
        ["bash", hook, "PostToolUse"], input=payload, text=True,
        capture_output=True, env=environment, check=False,
    )
    if result.returncode != 0 or result.stdout:
        raise SystemExit("no-marker fast path produced output or failed")
elapsed_ms = (time.perf_counter() - started) * 1000 / 20
if elapsed_ms >= 100:
    raise SystemExit(f"no-marker fast path measured {elapsed_ms:.3f} ms per call")
print(f"{elapsed_ms:.3f}")
PY
)"
[ -n "$fast_ms" ] && ok "no-marker fast path measures ${fast_ms} ms per call" || fail "no-marker fast path timing failed"

# The probe's printed append command must execute unchanged in the temp seat.
if [ -x "$PROBE" ]; then
  COMMAND_DIR="$T/space seat"
  COMMAND_LOG="$COMMAND_DIR/context quality.jsonl"
  mkdir -p "$COMMAND_DIR"
  command_output="$(MOGUI_STATE_DIR="$STATE" CONTEXT_QUALITY_LOG="$COMMAND_LOG" \
    bash "$PROBE" <<'EOF'
{"source":"compact","session_id":"command-session"}
EOF
)"
  recall_command="$(PROBE_OUTPUT="$command_output" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["PROBE_OUTPUT"])
text = payload["hookSpecificOutput"]["additionalContext"]
for line in text.splitlines():
    if line.startswith("CONTEXT_QUALITY_LOG="):
        print(line)
        break
PY
)"
  if [ -n "$recall_command" ] && (cd "$T" && bash -c "$recall_command") >/dev/null 2>&1 \
    && python3 - "$COMMAND_LOG" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    found = any(
        row.get("session") == "command-session" and row.get("event") == "compact"
        for row in map(json.loads, handle)
        if isinstance(row, dict)
    )
raise SystemExit(0 if found else 1)
PY
  then
    ok "printed recall command runs as written"
  else
    fail "printed recall command did not append a compact record: $recall_command"
  fi
else
  echo "SKIP: printed recall command requires the instance-owned probe in this rendered copy"
fi

# A missing record stays silent for two PostToolUse calls and rehydrates on the third.
run_probe third-post
first="$(run_hook "$HOOK" PostToolUse third-post)"
second="$(run_hook "$HOOK" PostToolUse third-post)"
third="$(run_hook "$HOOK" PostToolUse third-post)"
[ -z "$first" ] && ok "first PostToolUse without recall stays silent" || fail "first PostToolUse printed: $first"
[ -z "$second" ] && ok "second PostToolUse without recall stays silent" || fail "second PostToolUse printed: $second"
printf '%s' "$third" | grep -q 'measurement is contaminated' \
  && ok "third PostToolUse injects skipped recall work layer" \
  || fail "third PostToolUse missed skipped recall message: $third"
grep -q '"event":"recall_skipped"' "$LOG" \
  && ok "skipped recall appends one ledger event" \
  || fail "skipped recall ledger event missing"
skip_count="$(grep -c '"event":"recall_skipped"' "$LOG")"
[ "$skip_count" -eq 1 ] \
  && ok "hook writes one recall_skipped record through the ledger writer" \
  || fail "hook wrote $skip_count recall_skipped records for one skip"
[ ! -f "$STATE/compact-pending/third-post" ] \
  && ok "third PostToolUse consumes marker" \
  || fail "third PostToolUse left marker"

# A manual UserPromptSubmit before any PostToolUse leaves the marker and says the
# recall check is owed; the bounded skip path begins after a PostToolUse count.
run_probe first-prompt
prompt="$(run_hook "$HOOK" UserPromptSubmit first-prompt)"
printf '%s' "$prompt" | grep -q 'Recall check is owed' \
  && ok "first UserPromptSubmit reports owed recall" \
  || fail "first UserPromptSubmit missed owed-recall message: $prompt"
[ -f "$STATE/compact-pending/first-prompt" ] \
  && ok "first UserPromptSubmit preserves marker" \
  || fail "first UserPromptSubmit consumed marker"

run_probe prompt-after-post
run_hook "$HOOK" PostToolUse prompt-after-post >/dev/null
prompt="$(run_hook "$HOOK" UserPromptSubmit prompt-after-post)"
printf '%s' "$prompt" | grep -q 'measurement is contaminated' \
  && ok "UserPromptSubmit after PostToolUse injects skipped recall work layer" \
  || fail "UserPromptSubmit after PostToolUse missed skipped recall message: $prompt"
[ ! -f "$STATE/compact-pending/prompt-after-post" ] \
  && ok "UserPromptSubmit after PostToolUse consumes marker" \
  || fail "UserPromptSubmit after PostToolUse left marker"

# An append for another session is ignored.
run_probe other-session
append_record another-session
other="$(run_hook "$HOOK" PostToolUse other-session)"
[ -z "$other" ] && ok "another session's compact record is ignored" || fail "another session's record triggered output: $other"
marker_exists other-session && ok "another session's marker remains pending" || fail "other session marker was consumed"

# This session's complete record injects once, then becomes silent.
run_probe recorded-session
append_record recorded-session
recorded="$(run_hook "$HOOK" PostToolUse recorded-session)"
again="$(run_hook "$HOOK" PostToolUse recorded-session)"
printf '%s' "$recorded" | grep -q 'recent active track' \
  && ok "recorded recall injects the work layer" \
  || fail "recorded recall missed active track: $recorded"
[ -z "$again" ] && ok "recorded recall injects once" || fail "recorded recall repeated output: $again"

run_probe .dot-session
append_record .dot-session
dot_session="$(run_hook "$HOOK" PostToolUse .dot-session)"
printf '%s' "$dot_session" | grep -q 'recent active track' \
  && ok "dot-prefixed session marker is processed" \
  || fail "dot-prefixed session marker was skipped: $dot_session"
[ ! -f "$STATE/compact-pending/.dot-session" ] \
  && ok "dot-prefixed session marker is consumed" \
  || fail "dot-prefixed session marker remains pending"

# A marker older than six hours is deleted silently.
mkdir -p "$STATE/compact-pending"
cat > "$STATE/compact-pending/stale-session" <<EOF
{"compact_time":"2000-01-01T00:00:00+00:00","log_path":"$LOG","log_offset":0,"session_id":"stale-session","post_tool_uses":0}
EOF
stale="$(run_hook "$HOOK" UserPromptSubmit stale-session)"
[ -z "$stale" ] && ok "stale marker stays silent" || fail "stale marker printed: $stale"
[ ! -f "$STATE/compact-pending/stale-session" ] && ok "stale marker is deleted" || fail "stale marker remains"

cat > "$STATE/compact-pending/missing-time" <<EOF
{"log_path":"$LOG","log_offset":0,"session_id":"missing-time","post_tool_uses":0}
EOF
missing_time="$(run_hook "$HOOK" PostToolUse missing-time)"
[ -z "$missing_time" ] && ok "marker without compact time stays silent" || fail "marker without compact time printed: $missing_time"
[ ! -f "$STATE/compact-pending/missing-time" ] && ok "marker without compact time is deleted" || fail "marker without compact time remains"

# An old marker with a fresh claimed copy belongs to an active consumer. The
# claim timeout must use the claim file's mtime, so this case fails before the
# claim stamp is added.
python3 - "$STATE/compact-pending/fresh-claim" "$LOG" <<'PY'
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

marker_path, log_path = map(Path, sys.argv[1:])
marker_path.write_text(json.dumps({
    "compact_time": dt.datetime.now(dt.timezone.utc).isoformat(),
    "log_path": str(log_path.resolve()),
    "log_offset": 0,
    "session_id": "fresh-claim",
    "post_tool_uses": 2,
}) + "\n", encoding="utf-8")
claimed_path = marker_path.with_name(marker_path.name + ".claimed")
shutil.copy2(marker_path, claimed_path)
old = dt.datetime.now(dt.timezone.utc).timestamp() - 600
os.utime(marker_path, (old, old))
os.utime(claimed_path, None)
PY
fresh_claim="$(run_hook "$HOOK" PostToolUse fresh-claim)"
[ -z "$fresh_claim" ] && ok "fresh claim blocks a duplicate injection" || fail "fresh claim was treated as stale: $fresh_claim"
[ -f "$STATE/compact-pending/fresh-claim" ] && ok "fresh claim preserves the marker" || fail "fresh claim lost the marker"
[ -f "$STATE/compact-pending/fresh-claim.claimed" ] && ok "fresh claim remains owned" || fail "fresh claim ownership was lost"

# An aged claim is reclaimable and injects exactly once.
python3 - "$STATE/compact-pending/stale-claim" "$LOG" <<'PY'
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

marker_path, log_path = map(Path, sys.argv[1:])
marker_path.write_text(json.dumps({
    "compact_time": dt.datetime.now(dt.timezone.utc).isoformat(),
    "log_path": str(log_path.resolve()),
    "log_offset": 0,
    "session_id": "stale-claim",
    "post_tool_uses": 2,
}) + "\n", encoding="utf-8")
claimed_path = marker_path.with_name(marker_path.name + ".claimed")
shutil.copy2(marker_path, claimed_path)
old = dt.datetime.now(dt.timezone.utc).timestamp() - 600
os.utime(claimed_path, (old, old))
PY
stale_claim="$(run_hook "$HOOK" PostToolUse stale-claim)"
printf '%s' "$stale_claim" | grep -q 'measurement is contaminated' \
  && ok "stale claim is reclaimed and injects the work layer" \
  || fail "stale claim was not reclaimed: $stale_claim"
[ ! -f "$STATE/compact-pending/stale-claim" ] && ok "stale claim consumes the marker" || fail "stale claim left the marker"
[ ! -f "$STATE/compact-pending/stale-claim.claimed" ] && ok "stale claim releases ownership" || fail "stale claim left ownership"

# Two hundred long fake rows stay within the 9,000-character cap.
python3 - "$TRACKS" <<'PY'
import json
import sys
rows = [
    {"id": f"track-{i:03d}", "title": "x" * 120, "updated_at": "2099-01-01T00:00:00+00:00"}
    for i in range(200)
]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(rows, handle)
PY
run_probe cap-session
append_record cap-session
cap="$(run_hook "$HOOK" PostToolUse cap-session)"
cap_bytes="$(printf '%s' "$cap" | wc -c | tr -d ' ')"
[ "$cap_bytes" -le 9000 ] && ok "200 fake tracker rows stay under 9,000 characters" || fail "cap exceeded: $cap_bytes"
printf '%s' "$cap" | grep -q 'more: run' \
  && ok "cap names a runnable command for omitted rows" \
  || fail "cap omitted-row command missing"

python3 - "$TRACKS" <<'PY'
import json
import sys
rows = [
    {"id": f"short-{i:03d}", "title": "x", "updated_at": "2099-01-01T00:00:00+00:00"}
    for i in range(600)
]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(rows, handle)
PY
run_probe short-cap-session
append_record short-cap-session
short_cap="$(run_hook "$HOOK" PostToolUse short-cap-session)"
short_cap_bytes="$(printf '%s' "$short_cap" | wc -c | tr -d ' ')"
[ "$short_cap_bytes" -le 9000 ] && ok "short tracker rows stay under the serialized cap" || fail "short-row cap exceeded: $short_cap_bytes"

python3 - "$TRACKS" "$DECISIONS" <<'PY'
import json
import sys

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(
        [
            {"id": f"active-{i:03d}", "title": "진행중" * 300, "updated_at": "2099-01-01T00:00:00+00:00"}
            for i in range(25)
        ],
        handle,
        ensure_ascii=False,
    )
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(
        [
            {"id": f"decision-{i:03d}", "title": "결정" * 150, "updated_at": "2099-01-01T00:00:00+00:00"}
            for i in range(150)
        ],
        handle,
        ensure_ascii=False,
    )
PY
run_probe multibyte-cap
append_record multibyte-cap
multibyte_cap="$(run_hook "$HOOK" PostToolUse multibyte-cap)"
MULTIBYTE_OUTPUT="$multibyte_cap" python3 - <<'PY'
import json
import os
import re

payload = json.loads(os.environ["MULTIBYTE_OUTPUT"])
context = payload["hookSpecificOutput"]["additionalContext"]
headings = [
    "## Role State",
    "## In-progress tracker items",
    "## Open decisions",
    "## Live worker panes",
    "## Uncommitted files in the ops repository",
    "## Seat-declared extra lines",
]
assert all(heading in context for heading in headings), context
assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 9000

def section(heading):
    start = context.index(heading) + len(heading)
    remaining = context[start:]
    end = min((remaining.index(candidate) for candidate in headings if candidate in remaining), default=len(remaining))
    return remaining[:end].splitlines()

active = section("## In-progress tracker items")
decisions = section("## Open decisions")
active_more = next(int(match.group(1)) for line in active if (match := re.match(r"(\d+) more: run bd list --status=in_progress", line)))
decision_more = next(int(match.group(1)) for line in decisions if (match := re.match(r"(\d+) more: run bd list --status=open --type=decision", line)))
active_rows = sum(line.startswith("- active-") for line in active)
decision_rows = sum(line.startswith("- decision-") for line in decisions)
assert active_rows + active_more == 25, (active_rows, active_more)
assert decision_rows + decision_more == 150, (decision_rows, decision_more)
PY
ok "multibyte cap keeps every section and reports each omitted-row count"

cat > "$CONFIG" <<'EOF'
{"work_layer_extra_lines":["extra-0 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","extra-1 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","extra-2 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]}
EOF
python3 - "$TRACKS" "$DECISIONS" <<'PY'
import json
import sys

active, decisions = sys.argv[1:]
with open(active, "w", encoding="utf-8") as handle:
    json.dump(
        [{"id": f"trim-active-{i:02d}", "title": "a" * 100, "updated_at": "2099-01-01T00:00:00+00:00"} for i in range(25)],
        handle,
    )
with open(decisions, "w", encoding="utf-8") as handle:
    json.dump(
        [{"id": f"trim-decision-{i:03d}", "title": "d" * 100, "updated_at": "2099-01-01T00:00:00+00:00"} for i in range(150)],
        handle,
    )
PY
run_probe trim-order
append_record trim-order
trim_order_output="$(run_hook "$HOOK" PostToolUse trim-order)"
if TRIM_ORDER_OUTPUT="$trim_order_output" python3 - <<'PY'
import json
import os
import re

payload = json.loads(os.environ["TRIM_ORDER_OUTPUT"])
serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
assert len(serialized) <= 9000, len(serialized)
context = payload["hookSpecificOutput"]["additionalContext"]
headings = [
    "## Role State",
    "## In-progress tracker items",
    "## Open decisions",
    "## Live worker panes",
    "## Uncommitted files in the ops repository",
    "## Seat-declared extra lines",
]
assert all(heading in context for heading in headings), context

def section(heading):
    start = context.index(heading) + len(heading)
    remaining = context[start:]
    end = min((remaining.index(candidate) for candidate in headings if candidate in remaining), default=len(remaining))
    return remaining[:end].splitlines()

active = section("## In-progress tracker items")
decisions = section("## Open decisions")
extras = section("## Seat-declared extra lines")
active_rows = sum(line.startswith("- trim-active-") for line in active)
decision_rows = sum(line.startswith("- trim-decision-") for line in decisions)
extra_rows = sum(line.startswith("extra-") for line in extras)
active_more = sum(line.startswith("more: run bd list --status=in_progress") for line in active)
decision_more = [line for line in decisions if re.match(r"\d+ more: run bd list --status=open --type=decision(?: .*)?$", line)]
extra_more = [line for line in extras if re.match(r"\d+ more: run read the instance runtime extra-lines configuration$", line)]
assert active_rows == 25, active_rows
assert active_more == 0, active
assert decision_rows + int(decision_more[0].split()[0]) == 150, decision_more
assert extra_rows == 0 and extra_more and extra_more[0].startswith("3 more:"), extras
assert "more: run bd list --status=open --type=decision" in context, context
PY
then
  ok "trim order keeps all active rows, trims extras first, and names omitted decisions"
else
  fail "trim order did not preserve active rows or per-section omissions"
fi

run_probe large-payload
run_hook "$HOOK" PostToolUse large-payload >/dev/null
run_hook "$HOOK" PostToolUse large-payload >/dev/null
large_payload="$(python3 - <<'PY'
import json
print(json.dumps({
    "session_id": "large-payload",
    "hook_event_name": "PostToolUse",
    "tool_result": "x" * 1_200_000,
}))
PY
)"
large_output="$(run_hook_payload "$HOOK" PostToolUse "$large_payload")"
[ -n "$large_output" ] && [ ! -f "$STATE/compact-pending/large-payload" ] \
  && ok "payload over 1 MB is processed and consumes the marker" \
  || fail "payload over 1 MB was dropped or left the marker"

make_mutant() {
  local name="$1" old="$2" new="$3"
  if ! python3 - "$HOOK" "$T/$name.sh" "$old" "$new" <<'PY'
import sys
source, target, old, new = sys.argv[1:]
text = open(source, encoding="utf-8").read()
if old not in text:
    raise SystemExit(f"mutant source not found: {old}")
open(target, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY
  then
    fail "mutant $name was not built"
    return
  fi
  cp "$S/hooks/compact-rehydration-constants.inc" "$T/compact-rehydration-constants.inc"
  if ! chmod +x "$T/$name.sh"; then
    fail "mutant $name could not be made executable"
    return
  fi
}

make_mutant mutant-trim-order 'trim_order = ("extras", "decisions", "active", "panes", "uncommitted", "role")' 'trim_order = ("active", "decisions", "extras", "panes", "uncommitted", "role")'
run_probe mutant-trim-order
append_record mutant-trim-order
trim_mutant="$(run_hook "$T/mutant-trim-order.sh" PostToolUse mutant-trim-order)"
if TRIM_ORDER_OUTPUT="$trim_mutant" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["TRIM_ORDER_OUTPUT"])
context = payload["hookSpecificOutput"]["additionalContext"]
active_start = context.index("## In-progress tracker items")
active_end = context.index("## Open decisions")
active = context[active_start:active_end]
extras_start = context.index("## Seat-declared extra lines")
extras = context[extras_start:]
assert active.count("- trim-active-") < 25 or "extra-" in extras, context
PY
then
  ok "mutant-trim-order is caught"
else
  fail "mutant-trim-order survived"
fi

# Each mutant changes one contract rule and must make its focused case fail.
make_mutant mutant-record-gate 'recorded = recorded_recall(marker)' 'recorded = True'
run_probe mutant-record-gate
mutant_out="$(run_hook "$T/mutant-record-gate.sh" PostToolUse mutant-record-gate)"
[ -n "$mutant_out" ] && ok "mutant-record-gate is caught" || fail "mutant-record-gate survived"

make_mutant mutant-session-match 'row.get("session") == marker.get("session_id")' 'True'
run_probe mutant-session-match
append_record another-session
mutant_out="$(run_hook "$T/mutant-session-match.sh" PostToolUse mutant-session-match)"
[ -n "$mutant_out" ] && ok "mutant-session-match is caught" || fail "mutant-session-match survived"

make_mutant mutant-skip-threshold 'POST_TOOL_LIMIT = 2' 'POST_TOOL_LIMIT = 0'
run_probe mutant-skip-threshold
mutant_out="$(run_hook "$T/mutant-skip-threshold.sh" PostToolUse mutant-skip-threshold)"
[ -n "$mutant_out" ] && ok "mutant-skip-threshold is caught" || fail "mutant-skip-threshold survived"

make_mutant mutant-stale-expiry '> STALE_SECONDS' '> 10**99'
mkdir -p "$STATE/compact-pending"
cat > "$STATE/compact-pending/mutant-stale-expiry" <<EOF
{"compact_time":"2000-01-01T00:00:00+00:00","log_path":"$LOG","log_offset":0,"session_id":"mutant-stale-expiry","post_tool_uses":0}
EOF
run_hook "$T/mutant-stale-expiry.sh" PostToolUse mutant-stale-expiry >/dev/null
marker_exists mutant-stale-expiry && ok "mutant-stale-expiry is caught" || fail "mutant-stale-expiry survived"

make_mutant mutant-cap 'CAP = 8_500' 'CAP = 90_000'
run_probe mutant-cap
append_record mutant-cap
mutant_out="$(run_hook "$T/mutant-cap.sh" PostToolUse mutant-cap)"
mutant_bytes="$(printf '%s' "$mutant_out" | wc -c | tr -d ' ')"
[ "$mutant_bytes" -gt 9000 ] && ok "mutant-cap is caught" || fail "mutant-cap survived at $mutant_bytes bytes"

if [ "$F" -eq 0 ]; then
  echo "PASS: compact rehydration hook proof"
else
  echo "FAIL: compact rehydration hook proof" >&2
fi
exit "$F"
