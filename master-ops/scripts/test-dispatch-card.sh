#!/usr/bin/env bash
# Focused shell coverage for dispatch tracker-card resolution.
set -u

S="$(cd "$(dirname "$0")" && pwd)"
DISPATCH="$S/dispatch"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
F=0

ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*" >&2; F=1; }
extract_function() {
  name="$1"
  awk -v start="$name() {" '$0 == start {found=1} found {print; if ($0 == "}" && NR > 1) exit}' "$DISPATCH"
}
make_harness() {
  mode="$1"
  {
    printf 'set -u\n'
    printf 'CONTRACT="%s"\n' "$T/contract.md"
    printf 'CARD="" CARD_REASON="" CARD_CLAIMED=0 CARD_ARG_SET=0 NO_CARD_REASON="" NO_CARD_ARG_SET=0\n'
    printf 'CARD_LOG="%s"; export CARD_LOG\n' "$T/bd.log"
    printf 'PATH="%s:$PATH"\n' "$T/bin"
    extract_function contract_h1_title
    extract_function tracker_card_id
    extract_function tracker_card_display
    extract_function resolve_tracker_card
    extract_function release_tracker_claim
    extract_function fail_after_tracker_claim
    extract_function ledger_locked_command
    extract_function record_claim_failure_reason
    case "$mode" in
      card)
        printf 'CARD="existing-1"; CARD_ARG_SET=1\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      no-card)
        printf 'NO_CARD_REASON="owner-approved-gap"; NO_CARD_ARG_SET=1\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      auto)
        printf 'resolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      auto-trim)
        printf 'BD_ID_MODE=whitespace; export BD_ID_MODE\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      auto-invalid)
        printf 'BD_ID_MODE=invalid; export BD_ID_MODE\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      claim-fail)
        printf 'BD_CLAIM_MODE=fail; export BD_CLAIM_MODE\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      release)
        printf 'CARD="tk-auto1"; CARD_CLAIMED=1\nfail_after_tracker_claim "task-create failed" 3\n';;
      record-reason)
        printf 'LEDGER="%s" LEDGER_LOCK="%s" DISP=disp-test CARD_REASON="claim failed"\n' "$T/reason-ledger.jsonl" "$T/reason-ledger.lock"
        printf 'record_claim_failure_reason\ncat "$LEDGER"\n';;
      register-stdin)
        printf 'LEDGER="%s" LEDGER_LOCK="%s" REGISTER_GATE="%s"\nledger_locked_command "$REGISTER_GATE" register --ledger "$LEDGER"\n' "$T/register-ledger.jsonl" "$T/register-ledger.lock" "$T/register-gate";;
      check-only)
        printf 'CHECK_ONLY=1\n';;
    esac
  } > "$T/harness-$mode.sh"
  chmod +x "$T/harness-$mode.sh"
}

cat > "$T/contract.md" <<'EOF'
# feat: card-backed dispatch

Body.
EOF
mkdir -p "$T/bin"
cat > "$T/bin/bd" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CARD_LOG"
case "$1" in
  where) exit 0;;
  create)
    if [ "${BD_ID_MODE:-}" = invalid ]; then
      printf '{"id":"not a card"}\n'
    elif [ "${BD_ID_MODE:-}" = whitespace ]; then
      printf '{"id":"  tk-auto1  "}\n'
    else
      printf '{"id":"tk-auto1"}\n'
    fi
    exit 0;;
  unclaim) exit 0;;
  update)
    if [ "$3" = "--claim" ] && [ "${BD_CLAIM_MODE:-}" = fail ]; then
      exit 1
    fi
    exit 0;;
esac
exit 1
EOF
chmod +x "$T/bin/bd"

make_harness card
out=$(bash "$T/harness-card.sh")
[ "$out" = "CARD=existing-1 REASON=" ] && [ ! -s "$T/bd.log" ] \
  && ok "--card uses the supplied id without tracker calls" \
  || fail "--card case: $out"

: > "$T/bd.log"
make_harness no-card
out=$(bash "$T/harness-no-card.sh")
[ "$out" = "CARD= REASON=owner-approved-gap" ] && [ ! -s "$T/bd.log" ] \
  && ok "--no-card records the supplied reason without tracker calls" \
  || fail "--no-card case: $out"

: > "$T/bd.log"
make_harness auto
out=$(CARD_LOG="$T/bd.log" bash "$T/harness-auto.sh")
if [ "$out" = "CARD=tk-auto1 REASON=" ] \
    && grep -Fxq 'where' "$T/bd.log" \
    && grep -Fxq 'create feat: card-backed dispatch -t task -p 2 --json' "$T/bd.log" \
    && grep -Fxq 'update tk-auto1 --claim' "$T/bd.log"; then
  ok "default path creates and claims a card from the contract H1"
else
  fail "auto-create case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"
fi

: > "$T/bd.log"
make_harness auto-trim
out=$(CARD_LOG="$T/bd.log" bash "$T/harness-auto-trim.sh")
[ "$out" = "CARD=tk-auto1 REASON=" ] \
  && grep -Fxq 'update tk-auto1 --claim' "$T/bd.log" \
  && ok "auto-create trims a valid tracker id before claiming" \
  || fail "trimmed-id case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"

: > "$T/bd.log"
make_harness auto-invalid
out=$(CARD_LOG="$T/bd.log" bash "$T/harness-auto-invalid.sh")
[ "$out" = "CARD= REASON=tracker create returned no id" ] \
  && ! grep -Fq ' --claim' "$T/bd.log" \
  && ok "auto-create rejects an unusable tracker id before claiming" \
  || fail "invalid-id case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"

: > "$T/bd.log"
make_harness claim-fail
out=$(BD_CALL_LOG="$T/bd.log" bash "$T/harness-claim-fail.sh")
[ "$out" = "CARD=tk-auto1 REASON=claim failed" ] \
  && grep -Fxq 'update tk-auto1 --claim' "$T/bd.log" \
  && ok "claim failure keeps the created id and records the failure" \
  || fail "claim-fail case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"

: > "$T/reason-ledger.jsonl"
printf '{"decision":"ALLOW","job_id":"disp-test","card":"tk-auto1"}\n' > "$T/reason-ledger.jsonl"
make_harness record-reason
out=$(bash "$T/harness-record-reason.sh")
printf '%s' "$out" | grep -q '"card":"tk-auto1"' \
  && printf '%s' "$out" | grep -q '"card_reason":"claim failed"' \
  && ok "claim failure keeps the card id and adds the separate reason to the register row" \
  || fail "record-reason case: $out"

cat > "$T/register-gate" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${REGISTER_LOG:?}"
printf '{"allow":true}\n'
EOF
chmod +x "$T/register-gate"
: > "$T/register-ledger.jsonl"
make_harness register-stdin
register_out=$(REGISTER_LOG="$T/register.log" python3 - "$T/harness-register-stdin.sh" <<'PY'
import subprocess
import sys

proc = subprocess.Popen(
    ["bash", sys.argv[1]],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
try:
    output = proc.communicate(timeout=3)[0]
except subprocess.TimeoutExpired:
    proc.kill()
    output = proc.communicate()[0]
    print(output, end="")
    raise SystemExit("register path blocked on inherited stdin")
print(output, end="")
if proc.returncode != 0:
    raise SystemExit(proc.returncode)
PY
)
printf '%s' "$register_out" | grep -q '"allow":true' \
  && grep -Fxq "register --ledger $T/register-ledger.jsonl" "$T/register.log" \
  && ok "register path returns while terminal-like stdin remains open" \
  || fail "register stdin case: $register_out"

: > "$T/bd.log"
make_harness release
out=$(BD_CALL_LOG="$T/bd.log" bash "$T/harness-release.sh" 2>&1 || true)
printf '%s' "$out" | grep -q 'task-create failed · tracker claim released · card=tk-auto1' \
  && grep -Fxq 'unclaim tk-auto1' "$T/bd.log" \
  && ok "post-claim failure releases the tracker claim" \
  || fail "release case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"

: > "$T/bd.log"
make_harness check-only
bash "$T/harness-check-only.sh"
[ ! -s "$T/bd.log" ] && ok "helper harness check-only does not create or claim a card" \
  || fail "helper check-only called bd: $(tr '\n' ';' < "$T/bd.log")"

# Exercise the production wrapper's own --check-only branch. This renders the
# template placeholders and replaces only its external gate with a deterministic
# fake; the branch is therefore not reproduced by this test harness.
mkdir -p "$T/ops/scripts" "$T/runtime/scripts" "$T/state" "$T/harness" "$T/config"
printf '{"master_host_runtime":"codex"}\n' > "$T/config/instance-runtime.json"
mkdir -p "$T/harness/lib"
cp "$S/lib/orca_json.py" "$T/harness/lib/orca_json.py"
cp "$S/mogui_log.py" "$T/harness/mogui_log.py"
printf '{"tiers":{"efficient":["claude-haiku-4-5-20251001"],"top":[]}}\n' > "$T/ops/model-tier-policy.json"
printf '# production check-only fixture\n' > "$T/contract-production.md"
cat > "$T/runtime/scripts/dispatch-gate" <<'EOF'
#!/usr/bin/env bash
printf '{"allow":true,"contract_sha":"0123456789abcdef"}\n'
EOF
chmod +x "$T/runtime/scripts/dispatch-gate"
cp "$T/runtime/scripts/dispatch-gate" "$T/ops/scripts/dispatch-gate"
chmod +x "$T/ops/scripts/dispatch-gate"
cat > "$T/bin/claude" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$T/bin/claude"
cp "$S/approval-prompt-markers.txt" "$T/harness/approval-prompt-markers.txt"
sed -e "s|{{OPS_REPO}}|$T/ops|g" -e "s|{{RUNTIME_ROOT}}|$T/runtime|g" \
  "$DISPATCH" > "$T/harness/dispatch-production"
chmod +x "$T/harness/dispatch-production"
: > "$T/bd.log"
out=$(MOGUI_STATE_DIR="$T/state" CARD_LOG="$T/bd.log" \
  DISPATCH_STANDING_RULES="$S/../rules/standing-rules.md" PATH="$T/bin:$PATH" \
  bash "$T/harness/dispatch-production" \
    --contract "$T/contract-production.md" --spec production-check-only \
    --runtime claude --model claude-haiku-4-5-20251001 \
    --tier-policy "$T/ops/model-tier-policy.json" \
    --worktree "path:$T/unused" --check-only 2>&1)
status=$?
if [ "$status" -eq 0 ] \
    && printf '%s\n' "$out" | grep -q 'card=not-created(check-only)' \
    && [ ! -s "$T/bd.log" ]; then
  ok "production --check-only skips tracker-card creation"
else
  fail "production --check-only case: rc=$status out=$out calls=$(tr '\n' ';' < "$T/bd.log")"
fi

production_failure_case() {
  mode="$1"
  work="$T/production-$mode"
  mkdir -p "$work/ops/scripts" "$work/runtime/scripts" "$work/state" "$work/harness" "$work/config"
  printf '{"master_host_runtime":"codex"}\n' > "$work/config/instance-runtime.json"
  printf '{"tiers":{"efficient":["claude-haiku-4-5-20251001"],"top":[]}}\n' > "$work/ops/model-tier-policy.json"
  printf '# production failure fixture\n' > "$work/contract.md"
  cat > "$work/runtime/scripts/dispatch-gate" <<'EOF'
#!/usr/bin/env bash
register=0
for arg in "$@"; do
  [ "$arg" = register ] && register=1
done
if [ "$GATE_MODE" = gate-failure ] && [ "$register" = 1 ]; then
  printf '{"allow":false,"reason":"INVALID_REQUEST"}\n'
else
  printf '{"allow":true,"contract_sha":"0123456789abcdef"}\n'
fi
EOF
  chmod +x "$work/runtime/scripts/dispatch-gate"
  cp "$work/runtime/scripts/dispatch-gate" "$work/ops/scripts/dispatch-gate"
  chmod +x "$work/ops/scripts/dispatch-gate"
  cat > "$work/orca" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = orchestration ] && [ "$2" = task-create ]; then
  if [ "$ORCA_MODE" = task-failure ]; then
    printf '{}\n'
  else
    printf '{"ok":true,"result":{"task":{"id":"task-test"}}}\n'
  fi
  exit 0
fi
if [ "$1" = orchestration ] && [ "$2" = dispatch ]; then
  printf '{"ok":true,"result":{"dispatch":{"id":"disp-test"}}}\n'
  exit 0
fi
if [ "$1" = orchestration ] && [ "$2" = worker-show ]; then
  printf '{"ok":true,"result":{}}\n'
  exit 0
fi
if [ "$1" = orchestration ] && [ "$2" = dispatch-show ]; then
  printf '{"ok":true,"result":{"dispatch":{"id":"disp-test","status":"dispatched"}}}\n'
  exit 0
fi
if [ "$1" = terminal ] && [ "$2" = read ]; then
  count=0
  [ -f "$ORCA_READ_COUNT" ] && count=$(<"$ORCA_READ_COUNT")
  count=$((count + 1))
  printf '%s\n' "$count" > "$ORCA_READ_COUNT"
  if [ "$ORCA_MODE" = delivery-failure ] && [ "$count" -ge 2 ]; then
    printf 'rate limit\n'
  else
    printf 'claude >\n'
  fi
  exit 0
fi
exit 1
EOF
  chmod +x "$work/orca"
  cat > "$work/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$work/sleep"
  cp "$S/approval-prompt-markers.txt" "$work/harness/approval-prompt-markers.txt"
  mkdir -p "$work/harness/lib"
  cp "$S/lib/orca_json.py" "$work/harness/lib/orca_json.py"
  cp "$S/mogui_log.py" "$work/harness/mogui_log.py"
  sed -e "s|{{OPS_REPO}}|$work/ops|g" -e "s|{{RUNTIME_ROOT}}|$work/runtime|g" \
    "$DISPATCH" > "$work/harness/dispatch"
  chmod +x "$work/harness/dispatch"
  : > "$work/bd.log"
  : > "$work/read-count"
  set +e
  out=$(ORCA_MODE="$mode" GATE_MODE="$mode" ORCA_READ_COUNT="$work/read-count" \
    MOGUI_STATE_DIR="$work/state" CARD_LOG="$work/bd.log" \
    DISPATCH_STANDING_RULES="$S/../rules/standing-rules.md" \
    PATH="$T/bin:$work:$PATH" bash "$work/harness/dispatch" \
      --contract "$work/contract.md" --spec "$mode" \
      --runtime claude --model claude-haiku-4-5-20251001 \
      --tier-policy "$work/ops/model-tier-policy.json" \
      --terminal term_test 2>&1)
  status=$?
  set -u
  if [ "$mode" = task-failure ]; then
    expected=3
  elif [ "$mode" = gate-failure ]; then
    expected=4
  else
    expected=5
  fi
  if [ "$status" -eq "$expected" ] \
      && printf '%s\n' "$out" | grep -q 'tracker claim released · card=tk-auto1' \
      && grep -Fxq 'unclaim tk-auto1' "$work/bd.log"; then
    ok "$mode releases the claimed tracker card"
  else
    fail "$mode release case: rc=$status out=$out calls=$(tr '\n' ';' < "$work/bd.log")"
  fi
}

production_failure_case task-failure
production_failure_case gate-failure
production_failure_case delivery-failure

[ "$F" -eq 0 ] && echo "test-dispatch-card: OK" || { echo "test-dispatch-card: FAILED" >&2; exit 1; }
