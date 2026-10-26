#!/usr/bin/env bash
# Pins the documented shell-test loop ("Running it" in the repository's CONTRIBUTING.md): every
# scripts/test-*.sh must contribute to the overall exit status, not just the last one bash happens
# to run. Extracts the loop's exact text at runtime and replays it against a failing-then-passing
# fixture pair, so a future edit back to the single-exit-status form (`for t in ...; do bash "$t";
# done; echo $?`) fails here instead of only in CI.
#
# Only runs inside the authoring checkout, two levels above this script's own location: an
# installed copy never receives CONTRIBUTING.md, so it SKIPs there instead of failing.
set -u

two_up="$(cd "$(dirname "$0")/../.." && pwd)"
contributing="$two_up/CONTRIBUTING.md"
if [ ! -f "$contributing" ]; then
  echo "SKIP: CONTRIBUTING.md not found two levels up ($two_up); not the authoring checkout"
  exit 0
fi

FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

loop_line=$(grep -E '^\$ failed=0; for t in ' "$contributing" | head -1 | sed 's/^\$ //')
if [ -z "$loop_line" ]; then
  echo "FAIL: could not find the documented shell-test loop in CONTRIBUTING.md" >&2
  exit 1
fi
glob=$(printf '%s\n' "$loop_line" | sed -E 's/.*for t in ([^;]+);.*/\1/')
if [ -z "$glob" ] || [ "$glob" = "$loop_line" ]; then
  echo "FAIL: could not extract the test glob from the documented loop" >&2
  exit 1
fi
if ! bash -n -c "$loop_line" 2>/dev/null; then
  echo "FAIL: the extracted loop line does not parse as valid shell: $loop_line" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
glob_dir=$(dirname "$glob")
mkdir -p "$work/$glob_dir"
cat > "$work/$glob_dir/test-z-passes.sh" <<'FIXTURE'
#!/usr/bin/env bash
exit 0
FIXTURE
chmod +x "$work/$glob_dir"/test-*.sh

# Positive control: two passing fixtures (the failing one is added only below) must report exactly
# 0, so a loop sabotaged to always fail (an unconditional failed=1, say) has somewhere to show it.
cp "$work/$glob_dir/test-z-passes.sh" "$work/$glob_dir/test-y-also-passes.sh"
(cd "$work" && eval "$loop_line")
rc=$?
if [ "$rc" -eq 0 ]; then
  ok "documented loop reports success with two passing fixtures (exit $rc)"
else
  fail "documented loop reported failure with no failing fixture present (exit $rc)"
fi
rm -f "$work/$glob_dir/test-y-also-passes.sh"

cat > "$work/$glob_dir/test-a-fails.sh" <<'FIXTURE'
#!/usr/bin/env bash
exit 1
FIXTURE
chmod +x "$work/$glob_dir/test-a-fails.sh"

(cd "$work" && eval "$loop_line")
rc=$?
if [ "$rc" -eq 1 ]; then
  ok "documented loop reports failure with one failing fixture among two (exit $rc)"
else
  fail "documented loop reported exit $rc, expected exactly 1, with a failing fixture present"
fi

# failability: the pre-fix form only ever reported the last file's own exit status; reverting to
# it must flip this case on the same fixtures.
mutant_line="for t in $glob; do bash \"\$t\"; done; echo \$?"
mutant_out=$(cd "$work" && eval "$mutant_line" 2>&1 | tail -1)
if [ "$mutant_out" = "0" ]; then
  ok "failability: the single-exit-status form reports 0 with the same failing fixture present"
else
  fail "failability: expected the single-exit-status form to report 0, got '$mutant_out'"
fi

[ "$FAILED" -eq 0 ] && echo "test-contributing-shell-loop: OK" || { echo "test-contributing-shell-loop: FAILED"; exit 1; }
