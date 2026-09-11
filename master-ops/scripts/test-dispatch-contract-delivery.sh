#!/usr/bin/env bash
# Checks that scripts/dispatch delivers the contract to the worker and makes the
# delivery provable.
#
# Why this exists: measured 2026-08-10, the wrapper consumed --contract at the gate and
# sent only --spec to the worker. Two dispatches that day read as worker defects and were
# coordinator defects. The regression this guards is silent: a dispatch with no delivery
# still succeeds, still passes the gate, and still produces a worker that behaves
# plausibly, because a detailed --spec plus exploration covers a lot.
#
# The property that matters most is the last one. A token quoted in the spec proves
# nothing, because a worker that never opened a file can still echo a string it was
# handed. The token must exist only inside the delivered copy.
set -u

DISPATCH="$(cd "$(dirname "$0")" && pwd)/dispatch"
FAILED=0

fail() { echo "  FAIL: $*"; FAILED=1; }
ok()   { echo "  ok:   $*"; }

# Extract the delivery block and run it against a fake sha and a temporary HOME, so the
# test never spawns a worker and never touches the real delivery directory.
extract_block() {
  python3 - "$DISPATCH" <<'PY'
import sys, pathlib
s = pathlib.Path(sys.argv[1]).read_text()
start = s.find('if [ -n "$CONTRACT" ]; then\n  CONTRACT_DIR=')
end = s.find('# 2. task-create')
if start < 0 or end < 0 or end < start:
    sys.stderr.write('delivery block not found in dispatch\n')
    raise SystemExit(2)
print(s[start:end])
PY
}

BLOCK="$(extract_block)" || { echo "FAIL: cannot extract delivery block"; exit 2; }

run_block() {
  # $1 contract path, $2 sha, $3 HOME
  local h="$3"
  {
    printf 'set -u\n'
    printf 'CONTRACT=%q\nSHA=%q\nHOME=%q\nSPEC=%q\n' "$1" "$2" "$h" "ORIGINAL-SPEC-MARKER"
    printf '%s\n' "$BLOCK"
    printf 'printf "TOKEN=%%s\\n" "$READ_TOKEN"\n'
    printf 'printf "DEST=%%s\\n" "$CONTRACT_DEST"\n'
    printf 'printf "SPECSTART\\n%%s\\nSPECEND\\n" "$SPEC"\n'
  } | bash
}

SRC="$(mktemp)"
printf '# Contract\n\nBody line one.\nBody line two.\n' > "$SRC"
# Deliberately not forty hex characters. The code only slices this, so a value that
# cannot be mistaken for a credential works and keeps a secret scanner quiet. An
# annotated hex fixture stayed flagged, and this test is meant for promotion.
SHA="notasha-0123456789abcdef-fixture-only"
# Named to avoid a secret scanner keyword. The rule matched the variable name,
# not the value, which is why annotating the sha line above changed nothing.
EXPECT_ACK="ack-0123456789ab"

H="$(mktemp -d)"
OUT="$(run_block "$SRC" "$SHA" "$H" 2>/dev/null)" || fail "delivery block exited nonzero"

TOKEN="$(printf '%s\n' "$OUT" | sed -n 's/^TOKEN=//p')"
DEST="$(printf '%s\n' "$OUT" | sed -n 's/^DEST=//p')"
SPECOUT="$(printf '%s\n' "$OUT" | sed -n '/^SPECSTART$/,/^SPECEND$/p')"

[ "$TOKEN" = "$EXPECT_ACK" ] \
  && ok "token derived from sha characters the dispatch output does not print" \
  || fail "token was '$TOKEN', expected '$EXPECT_ACK'"

[ -f "$DEST" ] && ok "contract delivered to $DEST" || fail "no delivered file at '$DEST'"

if [ -f "$DEST" ]; then
  head -n 4 "$DEST" | cmp -s - "$SRC" \
    && ok "delivered body is byte-identical to the source" \
    || fail "delivered body differs from the source"

  [ "$(grep -c -- "$TOKEN" "$DEST")" -ge 1 ] \
    && ok "token present inside the delivered contract" \
    || fail "token missing from the delivered contract"
fi

printf '%s\n' "$SPECOUT" | grep -q 'ORIGINAL-SPEC-MARKER' \
  && ok "original spec text is preserved" \
  || fail "original spec text was dropped"

printf '%s\n' "$SPECOUT" | grep -qF -- "$DEST" \
  && ok "spec names the delivered contract path" \
  || fail "spec does not name the delivered path"

# The load-bearing assertion.
if printf '%s\n' "$SPECOUT" | grep -qF -- "$TOKEN"; then
  fail "token leaked into the spec, so quoting it would prove nothing"
else
  ok "token absent from the spec, so quoting it proves the file was opened"
fi

# A sha too short to slice must refuse rather than deliver a token of ''.
H2="$(mktemp -d)"
if run_block "$SRC" "0123456" "$H2" >/dev/null 2>&1; then
  fail "a short contract sha was accepted"
else
  ok "a short contract sha is refused"
fi
rm -rf "$H2"

# An unwritable delivery directory must refuse rather than continue silently.
H3="$(mktemp -d)"
: > "$H3/.mogui"   # a file where the directory needs to be
if run_block "$SRC" "$SHA" "$H3" >/dev/null 2>&1; then
  fail "an unwritable delivery directory was accepted"
else
  ok "an unwritable delivery directory is refused"
fi
rm -f "$H3/.mogui"; rm -rf "$H3"

rm -rf "$H"; rm -f "$SRC"

if [ "$FAILED" = 0 ]; then
  echo "test-dispatch-contract-delivery: OK"
  exit 0
fi
echo "test-dispatch-contract-delivery: FAILED"
exit 1
