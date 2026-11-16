#!/usr/bin/env bash
# Cross test (#313): worker-pane-sweep's approval row is followed by a re-read hint (#286).
# worker-wait's _pane_sweep() parses the sweep's stdout and skips only blank lines and lines
# starting with "sweep:"; a hint on stdout splits into a bogus entry in the verdict map (its
# third field becomes a fake "handle"). This feeds the sweep's actual stdout through _pane_sweep()
# itself for an approval pane and asserts the verdict map holds only pane entries.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REAL_WAIT="$ROOT/scripts/worker-wait"
REAL_SWEEP="$ROOT/scripts/worker-pane-sweep"
MARKERS="$ROOT/scripts/approval-prompt-markers.txt"
FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }
ok() { echo "  ok:   $*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Fake orca: one pane, frame fed through $SWEEP_FRAME (same convention as test-worker-pane-sweep.sh).
mkdir -p "$work/bin"
cat > "$work/bin/orca" <<'FAKE'
#!/usr/bin/env bash
case "$1 $2" in
  "terminal list") echo "term_00000000-0000-0000-0000-000000000001  fake worker pane";;
  "terminal read") printf '%s\n' "$SWEEP_FRAME";;
esac
FAKE
chmod +x "$work/bin/orca"

# $1: a directory holding a worker-wait with a sibling worker-pane-sweep; imports that worker-wait
# by path (its module-level guard is `if __name__ == "__main__"`, so importing never runs main())
# and calls _pane_sweep() against the sibling sweep, printing the resulting dict as JSON.
cat > "$work/call_pane_sweep.py" <<'PY'
import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader

module_dir = sys.argv[1]
path = f"{module_dir}/worker-wait"
loader = SourceFileLoader("worker_wait_under_test", path)
spec = importlib.util.spec_from_file_location("worker_wait_under_test", path, loader=loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
print(json.dumps(module._pane_sweep()))
PY

run_pane_sweep() {  # $1: directory with worker-wait + worker-pane-sweep siblings
  env -u ORCA_TERMINAL_HANDLE PATH="$work/bin:$PATH" SWEEP_FRAME='Do you want to proceed?' \
    python3 "$work/call_pane_sweep.py" "$1"
}

# worker-wait resolves lib/orca_json.py relative to its own file location at import time
# (docs/runbooks/orca-json.md), so every copy below needs that sibling staged alongside it.
stage_orca_json() {  # $1: directory a worker-wait copy will live in
  mkdir -p "$1/lib"
  cp "$ROOT/scripts/lib/orca_json.py" "$1/lib/orca_json.py"
}

# --- Fixed pair: the real worker-wait + the real (patched) worker-pane-sweep -----------------
mkdir -p "$work/fixed"
cp "$REAL_WAIT" "$work/fixed/worker-wait"
cp "$REAL_SWEEP" "$work/fixed/worker-pane-sweep"
cp "$MARKERS" "$work/fixed/approval-prompt-markers.txt"
chmod +x "$work/fixed/worker-pane-sweep"
stage_orca_json "$work/fixed"

fixed_out=$(run_pane_sweep "$work/fixed")
fixed_expect='{"term_00000000-0000": "approval"}'
if [ "$fixed_out" = "$fixed_expect" ]; then
  ok "fixed: verdict map holds only the pane entry: $fixed_out"
else
  fail "fixed: expected $fixed_expect, got: $fixed_out"
fi

# --- Failability: a copy of worker-pane-sweep reverted to the cf28142 shape, where the hint ---
# still goes to stdout. Proves the assertion above is meaningful: it must fail on this pair, the
# same way it would have failed on cf28142 itself.
mkdir -p "$work/mutant"
cp "$REAL_WAIT" "$work/mutant/worker-wait"
cp "$MARKERS" "$work/mutant/approval-prompt-markers.txt"
stage_orca_json "$work/mutant"
MUTANT_SWEEP="$work/mutant/worker-pane-sweep"
python3 - "$REAL_SWEEP" > "$MUTANT_SWEEP" <<'PY'
import sys
s = open(sys.argv[1]).read()
old = ('[ "$verdict" = approval ] && echo "       after answering, re-read with orca terminal '
       'read --terminal $h --screen before treating this as cleared (worker-wait.md)" >&2')
new = old.replace(" >&2", "")
assert old in s, "fixed hint-to-stderr line not found; worker-pane-sweep's shape changed"
assert new != old
s = s.replace(old, new, 1)
sys.stdout.write(s)
PY
if [ ! -s "$MUTANT_SWEEP" ] || cmp -s "$REAL_SWEEP" "$MUTANT_SWEEP"; then
  fail "failability: mutant not generated"
else
  chmod +x "$MUTANT_SWEEP"
  mutant_out=$(run_pane_sweep "$work/mutant")
  if [ "$mutant_out" = "$fixed_expect" ]; then
    fail "failability: cf28142-shaped sweep should have polluted the verdict map, got: $mutant_out"
  else
    ok "failability: cf28142-shaped sweep pollutes the verdict map: $mutant_out"
  fi
fi

[ "$FAILED" -eq 0 ] && { echo "worker-wait-pane-sweep-cross: all checks passed"; exit 0; }
echo "worker-wait-pane-sweep-cross: FAILED"
exit 1
