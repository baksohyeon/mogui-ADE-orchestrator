#!/usr/bin/env bash
# worker-pane-sweep must read the shared approval markers and classify a pane sitting on the codex
# hook-trust modal as `approval`# with exit 1, and must leave an idle pane at `idle` with exit 0. The sweep reads panes through
# bare `orca`, so a fake orca on PATH feeds it one pane whose frame is $SWEEP_FRAME.
set -u
SWEEP="$(cd "$(dirname "$0")" && pwd)/worker-pane-sweep"; FAILED=0
fail() { echo "  FAIL: $*"; FAILED=1; }; ok() { echo "  ok:   $*"; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cat > "$T/orca" <<'FAKE'
#!/usr/bin/env bash
case "$1 $2" in
  "terminal list") echo "term_00000000-0000-0000-0000-000000000001  fake worker pane";;
  "terminal read") printf '%s\n' "$SWEEP_FRAME";;
esac
FAKE
chmod +x "$T/orca"

grep -Fq 'approval-prompt-markers.txt' "$SWEEP" && ok "sweep reads the shared marker file" || fail "sweep does not reference approval-prompt-markers.txt"
# No marker from the file may appear in the sweep's own text, in any quoting: that is an inline copy.
MARKERS="$(dirname "$SWEEP")/approval-prompt-markers.txt"
inline=0; while IFS= read -r m; do grep -qiE -- "$m" "$SWEEP" && { fail "sweep carries marker inline: $m"; inline=1; }; done < <(grep -vE '^[[:space:]]*(#|$)' "$MARKERS")
[ "$inline" -eq 0 ] && ok "sweep carries no inline marker list"

run() { env -u ORCA_TERMINAL_HANDLE SWEEP_FRAME="$1" PATH="$T:$PATH" "$SWEEP" 2>&1; }
expect() { # label frame verdict exit
  out=$(run "$2"); rc=$?
  line=$(printf '%s\n' "$out" | grep -E "^[A-Za-z]+ +$3 " || true)
  [ -n "$line" ] && [ "$rc" -eq "$4" ] && ok "$1: verdict $3, exit $rc" || fail "$1: expected $3/exit $4, got exit $rc: $(printf '%s' "$out" | head -3 | tr '\n' '|')"
}

# Verbatim pane preview of the codex 0.154.0 modal, 2026-09-15.
MODAL='Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.
1. Review hooks
2. Trust all and continue
3. Continue without trusting
Press enter to confirm or esc to go back'
expect "codex hook-trust modal" "$MODAL" approval 1
expect "proceed question" 'Do you want to proceed?' approval 1
# Each new marker alone, so removing any one of them fails here and not only in the modal sample.
expect "marker alone: hooks need review" 'Hooks need review' approval 1
expect "marker alone: trust all and continue" 'Trust all and continue' approval 1
expect "marker alone: press enter to confirm" 'Press enter to confirm' approval 1
# The sweep lowercases the pane; the pattern must still match if a marker is written with capitals.
cp "$MARKERS" "$T/markers.bak"
printf 'Capitalised Test Marker\n' >> "$MARKERS"
expect "capitalised marker in the file" 'capitalised test marker' approval 1
cp "$T/markers.bak" "$MARKERS"
# Stale scrollback: the modal text is still visible above the fold, but the pane has already
# moved on to a bare shell prompt. The foreground is the prompt, not the resolved modal above it.
expect "stale modal above an idle prompt" "$MODAL
❯ " idle 0
# The shell/idle fallback must also classify from the foreground, not the whole chunk: a
# shell-prompt-shaped line in scrollback (here, between the resolved modal and the live prompt)
# must not make an idle pane read as a shell pane that lost its agent.
expect "stale modal, then a shell-prompt-shaped scrollback line, then an idle prompt" "$MODAL
➜ old-worktree (main)
❯ " idle 0
expect "idle prompt" '❯ ' idle 0
expect "idle prompt under a status line that says always-approve bypass permissions" 'always-approve bypass permissions
❯ ' idle 0

# Failability: a copy that classifies from the whole captured chunk again, instead of the
# foreground past the last prompt line, must flip the stale-scrollback case back to approval.
MUTANT="$T/worker-pane-sweep-mutant"
python3 - "$SWEEP" > "$MUTANT" <<'PY'
import sys
s = open(sys.argv[1]).read()
s = s.replace('printf \'%s\' "$foreground" | tr', 'printf \'%s\' "$frame" | tr', 1)
sys.stdout.write(s)
PY
chmod +x "$MUTANT"
cp "$MARKERS" "$T/approval-prompt-markers.txt"
if [ ! -f "$MUTANT" ] || cmp -s "$SWEEP" "$MUTANT"; then
  fail "failability: mutant not generated"
else
  SWEEP="$MUTANT" expect "failability: whole-chunk grep on stale scrollback" "$MODAL
❯ " approval 1
fi

# Failability: the shell/idle fallback must also read from the foreground. A copy that reverts
# only the fallback back to the whole chunk must misread the scrollback shell-prompt-shaped line
# as the pane's own state and report shell instead of idle.
FALLBACK_MUTANT="$T/worker-pane-sweep-fallback-mutant"
python3 - "$SWEEP" > "$FALLBACK_MUTANT" <<'PY'
import sys
s = open(sys.argv[1]).read()
old = '''  if [ "$verdict" = unknown ]; then
    if printf '%s' "$foreground" | grep -qE '^[[:space:]]*➜|\\$ $'; then verdict=shell
    elif printf '%s' "$foreground" | grep -qE '❯[[:space:]]*$'; then verdict=idle
    fi
  fi'''
new = old.replace('"$foreground"', '"$frame"')
assert old in s, "fallback block not found"
assert new != old
s = s.replace(old, new, 1)
sys.stdout.write(s)
PY
chmod +x "$FALLBACK_MUTANT"
if [ ! -f "$FALLBACK_MUTANT" ] || cmp -s "$SWEEP" "$FALLBACK_MUTANT"; then
  fail "failability: fallback mutant not generated"
else
  SWEEP="$FALLBACK_MUTANT" expect "failability: whole-chunk fallback on scrollback shell-prompt line" "$MODAL
➜ old-worktree (main)
❯ " shell 0
fi

[ "$FAILED" -eq 0 ] && echo "worker-pane-sweep: all checks passed" || { echo "worker-pane-sweep: FAILED"; exit 1; }
