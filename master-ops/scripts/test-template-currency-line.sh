#!/bin/bash
# Regression test for format_template_currency_line() in harness-selfcheck.sh
# (the "Template:" boot line). Contract: 2026-09-26-template-manifest-retirements.
#
# The manifest cannot express partial adoption on its own: an install that
# retired a required path on purpose, or that simply accumulated its own
# files, used to read "run Upgrade mode" forever. These cases prove the line
# stops failing on files the install added or retired, while a genuinely
# absent required path or a broken retirements file still fails.
set -u

cd "$(dirname "$0")/.."

SELFCHECK_BIN="${SELFCHECK_BIN:-./scripts/harness-selfcheck.sh}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

# Exercised directly, like template_adoption_probe and twins_probe in
# test-seat-check.sh, instead of running the whole self-check end to end.
eval "$(sed -n '/^format_template_currency_line()/,/^}/p' "$SELFCHECK_BIN")"

check() {
  # $1 = case name, $2 = TEMPLATE_JSON, $3 = TEMPLATE_RC, $4 = expected
  # substring, $5 = expected exit code.
  local name="$1" json="$2" rc_in="$3" expect="$4" expect_rc="$5" line rc
  line=$(TEMPLATE_JSON="$json" TEMPLATE_RC="$rc_in" format_template_currency_line)
  rc=$?
  if printf '%s' "$line" | grep -qF "$expect" && [ "$rc" -eq "$expect_rc" ]; then
    echo "ok   — $name"
    pass=$((pass + 1))
  else
    echo "FAIL — $name"
    echo "       expected substring: $expect (exit $expect_rc)"
    echo "       actual line:        $line (exit $rc)"
    fail=$((fail + 1))
  fi
}

# Generated-mutant guard: a no-op sed must not pass this failability check
# silently (same discipline as template_mutant_check in test-seat-check.sh).
mutant_check() {
  # $1 = case label, $2 = sed pattern to break the verdict, $3 = TEMPLATE_JSON,
  # $4 = TEMPLATE_RC, $5 = the untouched verdict substring the mutant must lose.
  local label="$1" pattern="$2" json="$3" rc_in="$4" original="$5"
  local mut="$TMP/harness-selfcheck.mutant.$$.sh" mline
  sed "$pattern" "$SELFCHECK_BIN" > "$mut"
  if [ ! -f "$mut" ] || cmp -s "$SELFCHECK_BIN" "$mut"; then
    echo "FAIL: mutant not generated" >&2
    rm -f "$mut"
    exit 1
  fi
  mline=$(
    eval "$(sed -n '/^format_template_currency_line()/,/^}/p' "$mut")"
    TEMPLATE_JSON="$json" TEMPLATE_RC="$rc_in" format_template_currency_line
  )
  rm -f "$mut"
  case "$mline" in
    *"$original"*)
      echo "FAIL — failability: $label mutant still reported the original verdict"
      fail=$((fail + 1))
      ;;
    *)
      echo "ok   — failability: $label mutant verdict differs, so the case would fail"
      pass=$((pass + 1))
      ;;
  esac
}

json_matches_with_retired='{"installed_version":"v1","manifest_status":"ok","absent_required":[],"retired":["a.md"],"unknown_present":[],"report_set":"template-compare","template_version":"v1","retirements_status":"ok"}'
json_install_manifest_with_retired='{"installed_version":"v1","manifest_status":"ok","absent_required":[],"retired":["a.md"],"unknown_present":[],"report_set":"install-manifest","template_version":null,"retirements_status":"ok"}'
json_matches_with_unknown_retirement='{"installed_version":"v1","manifest_status":"ok","absent_required":[],"retired":[],"retirements_unknown":["z.md"],"unknown_present":[],"report_set":"template-compare","template_version":"v1","retirements_status":"ok"}'
json_unknown_alone='{"installed_version":"v1","manifest_status":"ok","absent_required":[],"retired":[],"unknown_present":["x.txt","y.txt"],"report_set":"install-manifest","template_version":null,"retirements_status":"ok"}'
json_genuinely_absent='{"installed_version":"v1","manifest_status":"ok","absent_required":["missing.md"],"retired":[],"unknown_present":[],"report_set":"install-manifest","template_version":null,"retirements_status":"ok"}'
json_malformed_retirements='{"installed_version":"v1","manifest_status":"ok","absent_required":[],"retired":[],"unknown_present":[],"report_set":"install-manifest","template_version":null,"retirements_status":"malformed"}'
json_manifest_absent='{"installed_version":null,"manifest_status":"absent","absent_required":[],"retired":[],"unknown_present":[],"report_set":"template-compare","template_version":"v1","retirements_status":"absent"}'

# 1. A retired path is not absent: reported in the passing line's retired count.
check "retired path passes with a retired count" \
  "$json_matches_with_retired" 0 \
  "Template: v1 (matches template v1, 1 retired)" 0
mutant_check "retired-count" \
  's/suffix = f", {retired} retired" if retired else ""/suffix = ""/' \
  "$json_matches_with_retired" 0 \
  "matches template v1, 1 retired"

# 1b. A retired count is reported even without a template to compare against
#     (CodeRabbit finding on this contract's own PR: the install-manifest
#     success branch used to drop the retired count on the floor).
check "retired count shows without a template comparison" \
  "$json_install_manifest_with_retired" 0 \
  "Template: v1 (installed-manifest shape ok; no template path for currency compare, 1 retired)" 0
mutant_check "install-manifest-retired-count" \
  's/suffix = f", {retired} retired" if retired else ""/suffix = ""/' \
  "$json_install_manifest_with_retired" 0 \
  "no template path for currency compare, 1 retired"

# 2. A retirement not in the manifest is reported (retirements_unknown) and
#    does not fail: the passing line is unaffected by it.
check "retirement not in manifest does not fail the line" \
  "$json_matches_with_unknown_retirement" 0 \
  "Template: v1 (matches template v1)" 0

# 3. Unknown files alone give exit 0.
check "unknown files alone pass" \
  "$json_unknown_alone" 0 \
  "Template: v1 (installed-manifest shape ok; no template path for currency compare)" 0
mutant_check "unknown-alone" \
  's/if rc == 0 and status == "ok" and absent == 0:/if False:/' \
  "$json_unknown_alone" 0 \
  "installed-manifest shape ok"

# 4. A genuinely absent path (no retirement declared) still gives exit 1.
check "genuinely absent path still fails" \
  "$json_genuinely_absent" 1 \
  "Template: v1 (manifest=ok, absent=1, retired=0, unknown=0) — run Upgrade mode" 1
mutant_check "genuinely-absent" \
  's/absent={absent}, retired={retired}, unknown={unknown}/absent=MUTANT, retired={retired}, unknown={unknown}/' \
  "$json_genuinely_absent" 1 \
  "absent=1, retired=0, unknown=0"

# 5. A malformed retirements file gives manifest=ok plus a retirements=malformed
#    marker and exit 1.
check "malformed retirements file is reported and fails" \
  "$json_malformed_retirements" 1 \
  "Template: v1 (manifest=ok, retirements=malformed) — run Upgrade mode" 1
mutant_check "retirements-malformed" \
  's/retirements_status == "malformed":/retirements_status == "never-matches":/' \
  "$json_malformed_retirements" 1 \
  "retirements=malformed"

# 6. Unrelated regression: a pre-manifest install is still reported and fails,
#    unaffected by the retirements/unknown changes above.
check "manifest absent still fails" \
  "$json_manifest_absent" 1 \
  "Template: no MANIFEST.json (run Upgrade mode; pre-manifest install)" 1

echo "----"
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
