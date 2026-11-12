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
    printf 'CARD="" CARD_REASON="" CARD_ARG_SET=0 NO_CARD_REASON="" NO_CARD_ARG_SET=0\n'
    printf 'CARD_LOG="%s"; export CARD_LOG\n' "$T/bd.log"
    extract_function contract_h1_title
    extract_function tracker_card_id
    extract_function resolve_tracker_card
    case "$mode" in
      card)
        printf 'CARD="existing-1"; CARD_ARG_SET=1\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      no-card)
        printf 'NO_CARD_REASON="owner-approved-gap"; NO_CARD_ARG_SET=1\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n';;
      auto)
        printf 'PATH="%s:$PATH"\nresolve_tracker_card\nprintf "CARD=%%s REASON=%%s\\n" "$CARD" "$CARD_REASON"\n' "$T/bin";;
      check-only)
        printf 'CHECK_ONLY=1\nif [ "$CHECK_ONLY" = 1 ]; then exit 0; fi\nresolve_tracker_card\n';;
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
  create) printf 'Created issue: mgm-auto1\n'; exit 0;;
  update) exit 0;;
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
if [ "$out" = "CARD=mgm-auto1 REASON=" ] \
    && grep -Fxq 'where' "$T/bd.log" \
    && grep -Fxq 'create feat: card-backed dispatch -t task -p 2' "$T/bd.log" \
    && grep -Fxq 'update mgm-auto1 --claim' "$T/bd.log"; then
  ok "default path creates and claims a card from the contract H1"
else
  fail "auto-create case: $out; calls=$(tr '\n' ';' < "$T/bd.log")"
fi

: > "$T/bd.log"
make_harness check-only
bash "$T/harness-check-only.sh"
[ ! -s "$T/bd.log" ] && ok "--check-only does not create or claim a card" \
  || fail "--check-only called bd: $(tr '\n' ';' < "$T/bd.log")"

[ "$F" -eq 0 ] && echo "test-dispatch-card: OK" || { echo "test-dispatch-card: FAILED" >&2; exit 1; }
