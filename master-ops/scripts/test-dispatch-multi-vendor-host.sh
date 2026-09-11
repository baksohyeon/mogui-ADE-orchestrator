#!/usr/bin/env bash
# A host that runs several vendors' models must be validated against its own list.
#
# Measured 2026-08-24: --runtime cursor was unreachable. model_vendor() mapped id
# prefixes to claude, codex, grok, gemini, and the check required vendor == runtime, so
# no id could ever satisfy a cursor dispatch while the refusal text advertised cursor as
# installed. Vendor-level matching does not fix it either: the efficient tier opens with
# gpt-5.6-luna and cursor does not offer that id, so a vendor match would declare a model
# the worker can never emit, which is the harm the check exists to prevent.
#
# Skips when the host CLI is absent, because the assertions are about a real list.
set -u
D="$(cd "$(dirname "$0")" && pwd)/dispatch"
OPS="$(cd "$(dirname "$0")/.." && pwd)"
C="$OPS/contracts/2026-08-04-skill-composition-doc.md"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok()   { echo "  ok:   $*"; }

command -v cursor-agent >/dev/null 2>&1 || { echo "test-dispatch-multi-vendor-host: SKIP (cursor-agent absent)"; exit 0; }
[ -f "$C" ] || { echo "test-dispatch-multi-vendor-host: SKIP (sample contract absent)"; exit 0; }

WT=$(git -C "$OPS" rev-parse --show-toplevel)

run() { "$D" --contract "$C" --spec probe --worktree "path:$WT" --check-only "$@" 2>&1; }

OUT=$(run --runtime cursor)
printf '%s\n' "$OUT" | grep -q 'intersecting the tier policy with its own list' \
  && ok "cursor derives a model from its own list" \
  || fail "cursor did not derive from its own list: $(printf '%s' "$OUT" | tail -2)"

DERIVED=$(printf '%s\n' "$OUT" | sed -n 's/.*its own list: //p')
cursor-agent models 2>/dev/null | sed -n 's/^\([A-Za-z0-9._-][A-Za-z0-9._-]*\) - .*$/\1/p' | grep -qx -- "$DERIVED" \
  && ok "the derived id '$DERIVED' is one the host actually offers" \
  || fail "derived '$DERIVED' is absent from the host list"

# The load-bearing assertion: a tier-allowed id the host does not sell must be refused.
OUT=$(run --runtime cursor --model gpt-5.6-luna)
printf '%s\n' "$OUT" | grep -q 'does not offer model=gpt-5.6-luna' \
  && ok "a tier-allowed id the host does not offer is refused" \
  || fail "gpt-5.6-luna was accepted on cursor"

printf '%s\n' "$OUT" | grep -q 'Ids it offers that the tier policy also allows' \
  && ok "the refusal names what the host does offer" \
  || fail "refusal gave no alternatives"

# Single-vendor hosts keep the prefix check.
OUT=$(run --runtime codex)
printf '%s\n' "$OUT" | grep -q 'model derived for runtime codex from tier policy' \
  && ok "codex derivation unchanged" \
  || fail "codex derivation regressed"

OUT=$(run --runtime claude --model gpt-5.6-luna)
printf '%s\n' "$OUT" | grep -q 'model/runtime mismatch' \
  && ok "a cross-vendor id on a single-vendor host is still refused" \
  || fail "claude accepted a codex id"

[ "$FAILED" = 0 ] && { echo "test-dispatch-multi-vendor-host: OK"; exit 0; }
echo "test-dispatch-multi-vendor-host: FAILED"; exit 1
