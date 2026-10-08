#!/bin/bash
# Regression checks for the unavailable_runtimes refusal path in dispatch:
# dispatchable_runtimes() excludes an operator-declared-unavailable runtime
# from both the default-runtime pick and the alternatives list, and the
# RUNTIME-is-final refusal prints the reason and the remaining alternatives
# before any gate work happens. A new file because test-dispatch-runtime.sh
# is past the 1,000-line rule (CONTRIBUTING.md "When a file is full").
#
# dispatch carries {{RUNTIME_ROOT}} and {{OPS_REPO}} template placeholders,
# which bash leaves as literal strings it never dereferences before the gate
# call this suite stops short of, so the refusal case below runs the whole
# script under a scratch PATH and HOME, with a fake dispatch-gate planted at
# the literal GATE path so a marker it writes on invocation proves the gate
# was never reached, instead of inferring that from a non-zero exit alone.
# The default/alternatives cases
# extract installed_runtimes, unavailable_runtime_names, dispatchable_runtimes,
# and choose_default_runtime by exact-line awk range and run them in an
# isolated subshell, the extraction convention test-dispatch-runtime.sh
# already uses throughout.
set -eu

dispatch=$(cd "$(dirname "$0")" && pwd)/dispatch
dispatch=${1:-$dispatch}

extract_fn() {  # fn-name
  awk -v fn="$1() {" '$0==fn{f=1} f{print} f&&$0=="}"{exit}' "$dispatch"
}

# --- Case: --check-only refuses an unavailable runtime, with reason and alternatives ---
check_only_refusal_test() (
  set +e
  local work contract out status marker gate_dir

  work="${TMPDIR:-/tmp}/mogui-dispatch-unavail-refusal.$$"
  mkdir -p "$work/bin"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/bin/grok" <<'BIN'
#!/bin/bash
exit 0
BIN
  cat > "$work/bin/codex" <<'BIN'
#!/bin/bash
exit 0
BIN
  chmod +x "$work/bin/grok" "$work/bin/codex"
  cat > "$work/instance-runtime.json" <<'JSON'
{"master_host_runtime": "claude", "unavailable_runtimes": {"grok": {"since": "2026-08-07", "why": "free usage limit hit; no paid plan on this account"}}}
JSON
  contract="$work/contract.md"
  echo "scratch contract" > "$contract"

  # dispatch's GATE is the unexpanded template literal {{RUNTIME_ROOT}}/scripts/dispatch-gate
  # (a relative path, since the placeholder is never filled in this template
  # clone), so planting a fake gate there and running with $work as cwd puts a
  # real executable where dispatch would invoke it, if it got that far. The
  # fake gate touches a marker on invocation; its absence after the refusal is
  # the proof the gate was never reached. A non-zero exit alone would not
  # distinguish "refused before the gate" from "the gate ran and refused."
  marker="$work/gate-invoked"
  gate_dir="$work/{{RUNTIME_ROOT}}/scripts"
  mkdir -p "$gate_dir"
  cat > "$gate_dir/dispatch-gate" <<BIN
#!/bin/bash
touch "$marker"
printf '{"allow": true, "contract_sha": "abcdef0123456789"}\n'
BIN
  chmod +x "$gate_dir/dispatch-gate"

  out=$(cd "$work" && PATH="$work/bin:/usr/bin:/bin" HOME="$work/home" \
        MOGUI_INSTANCE_RUNTIME_CONFIG="$work/instance-runtime.json" \
        bash "$dispatch" --contract "$contract" --runtime grok --check-only 2>&1)
  status=$?

  if [ "$status" -eq 0 ]; then
    echo "FAIL: --check-only on an unavailable runtime should exit non-zero" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  case "$out" in
    *"✗ runtime grok unavailable on this install since 2026-08-07: free usage limit hit; no paid plan on this account · alternatives: codex"*) ;;
    *) echo "FAIL: refusal line missing reason or alternatives" >&2; printf '%s\n' "$out" >&2; return 1;;
  esac
  if [ -e "$marker" ]; then
    echo "FAIL: dispatch-gate marker is present; the refusal did not happen before the gate" >&2
    return 1
  fi
  echo "ok   : --check-only refuses an unavailable runtime, naming the reason and the remaining alternatives, before the gate is ever invoked · rc=$status"
)
check_only_refusal_test || exit 1

# --- Case: a malformed unavailable_runtimes entry fails closed, even with an ---
# --- explicit --runtime, instead of reading as "nothing declared".          ---
malformed_entry_refusal_test() (
  set +e
  local work contract out status marker gate_dir

  work="${TMPDIR:-/tmp}/mogui-dispatch-unavail-malformed.$$"
  mkdir -p "$work/bin"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/bin/grok" <<'BIN'
#!/bin/bash
exit 0
BIN
  cat > "$work/bin/codex" <<'BIN'
#!/bin/bash
exit 0
BIN
  chmod +x "$work/bin/grok" "$work/bin/codex"
  # grok is named under unavailable_runtimes, but the entry has no "why":
  # malformed, not absent. The old behaviour read this the same as no entry
  # at all and let an explicit --runtime grok through.
  cat > "$work/instance-runtime.json" <<'JSON'
{"master_host_runtime": "claude", "unavailable_runtimes": {"grok": {"since": "2026-08-07"}}}
JSON
  contract="$work/contract.md"
  echo "scratch contract" > "$contract"

  marker="$work/gate-invoked"
  gate_dir="$work/{{RUNTIME_ROOT}}/scripts"
  mkdir -p "$gate_dir"
  cat > "$gate_dir/dispatch-gate" <<BIN
#!/bin/bash
touch "$marker"
printf '{"allow": true, "contract_sha": "abcdef0123456789"}\n'
BIN
  chmod +x "$gate_dir/dispatch-gate"

  out=$(cd "$work" && PATH="$work/bin:/usr/bin:/bin" HOME="$work/home" \
        MOGUI_INSTANCE_RUNTIME_CONFIG="$work/instance-runtime.json" \
        bash "$dispatch" --contract "$contract" --runtime grok --check-only 2>&1)
  status=$?

  if [ "$status" -eq 0 ]; then
    echo "FAIL: --check-only with an explicit --runtime naming a malformed entry should exit non-zero" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  case "$out" in
    *"✗ invalid unavailable_runtimes in "*"instance-runtime.json: unavailable_runtimes['grok'].why must be a non-empty single-line string"*) ;;
    *) echo "FAIL: refusal line missing the invalid-config message" >&2; printf '%s\n' "$out" >&2; return 1;;
  esac
  if [ -e "$marker" ]; then
    echo "FAIL: dispatch-gate marker is present; the malformed-entry refusal did not happen before the gate" >&2
    return 1
  fi
  echo "ok   : a malformed unavailable_runtimes entry refuses an explicit --runtime, before the gate is ever invoked · rc=$status"
)
malformed_entry_refusal_test || exit 1

# --- Case: a crafted --runtime value carrying a quote and a Python expression ---
# --- is refused as not installed or not listed, never executed.                ---
injection_refusal_test() (
  set +e
  local work contract out status marker gate_dir payload_marker runtime_payload

  work="${TMPDIR:-/tmp}/mogui-dispatch-unavail-injection.$$"
  mkdir -p "$work/bin"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/bin/codex" <<'BIN'
#!/bin/bash
exit 0
BIN
  chmod +x "$work/bin/codex"
  # unavailable_runtimes present (as an object) and non-empty so the malformed-
  # config short circuit in dispatch's own `if not isinstance(unavail, dict) or
  # ...` line (the vulnerable shape before this round) does not exit before
  # reaching the vulnerable interpolation; this is what makes the case
  # failable against that shape instead of passing by accident.
  cat > "$work/instance-runtime.json" <<'JSON'
{"master_host_runtime": "claude", "unavailable_runtimes": {}}
JSON
  contract="$work/contract.md"
  echo "scratch contract" > "$contract"

  marker="$work/gate-invoked"
  gate_dir="$work/{{RUNTIME_ROOT}}/scripts"
  mkdir -p "$gate_dir"
  cat > "$gate_dir/dispatch-gate" <<BIN
#!/bin/bash
touch "$marker"
printf '{"allow": true, "contract_sha": "abcdef0123456789"}\n'
BIN
  chmod +x "$gate_dir/dispatch-gate"

  # A quote closes the Python string literal the old code embedded this value
  # into; the rest is a Python expression that, left unguarded, calls out to
  # the shell. Passed through sys.argv it is never anything but a string.
  payload_marker="$work/injected"
  runtime_payload="' or __import__('os').system('touch $payload_marker') or '"

  out=$(cd "$work" && PATH="$work/bin:/usr/bin:/bin" HOME="$work/home" \
        MOGUI_INSTANCE_RUNTIME_CONFIG="$work/instance-runtime.json" \
        bash "$dispatch" --contract "$contract" --runtime "$runtime_payload" --check-only 2>&1)
  status=$?

  if [ "$status" -eq 0 ]; then
    echo "FAIL: --check-only with a crafted --runtime should exit non-zero" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  if [ -e "$payload_marker" ]; then
    echo "FAIL: the injected expression ran; its marker file exists" >&2
    return 1
  fi
  if [ -e "$marker" ]; then
    echo "FAIL: dispatch-gate marker is present; the crafted runtime reached the gate" >&2
    return 1
  fi
  echo "ok   : a crafted --runtime value is refused as not installed or not listed, never executed · rc=$status"
)
injection_refusal_test || exit 1

# --- Case: an unreadable (malformed JSON) config refuses the default pick, ---
# --- with no --runtime given at all.                                       ---
unreadable_config_default_pick_test() (
  set +e
  local work contract out status marker gate_dir

  work="${TMPDIR:-/tmp}/mogui-dispatch-unavail-unreadable.$$"
  mkdir -p "$work/bin"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/bin/codex" <<'BIN'
#!/bin/bash
exit 0
BIN
  chmod +x "$work/bin/codex"
  printf 'not valid json at all' > "$work/instance-runtime.json"
  contract="$work/contract.md"
  echo "scratch contract" > "$contract"

  marker="$work/gate-invoked"
  gate_dir="$work/{{RUNTIME_ROOT}}/scripts"
  mkdir -p "$gate_dir"
  cat > "$gate_dir/dispatch-gate" <<BIN
#!/bin/bash
touch "$marker"
printf '{"allow": true, "contract_sha": "abcdef0123456789"}\n'
BIN
  chmod +x "$gate_dir/dispatch-gate"

  out=$(cd "$work" && PATH="$work/bin:/usr/bin:/bin" HOME="$work/home" \
        MOGUI_INSTANCE_RUNTIME_CONFIG="$work/instance-runtime.json" \
        bash "$dispatch" --contract "$contract" --check-only 2>&1)
  status=$?

  if [ "$status" -eq 0 ]; then
    echo "FAIL: --check-only with an unreadable config should exit non-zero" >&2
    printf '%s\n' "$out" >&2
    return 1
  fi
  case "$out" in
    *"✗ invalid unavailable_runtimes in "*"instance-runtime.json: not valid JSON"*) ;;
    *) echo "FAIL: refusal line missing the invalid-config message" >&2; printf '%s\n' "$out" >&2; return 1;;
  esac
  if [ -e "$marker" ]; then
    echo "FAIL: dispatch-gate marker is present; the unreadable-config refusal did not happen before the gate" >&2
    return 1
  fi
  echo "ok   : an unreadable config refuses the default pick, before the gate is ever invoked · rc=$status"
)
unreadable_config_default_pick_test || exit 1

# --- Case: default runtime and alternatives omit an unavailable runtime; ---
# --- removing the key changes neither.                                   ---
default_and_alternatives_test() (
  set +e
  set -u
  local installed_fn names_fn dispatchable_fn choose_fn join_fn payload_fn guard_fn work script_file
  local with_key without_key out_with out_without status

  installed_fn=$(extract_fn installed_runtimes)
  payload_fn=$(extract_fn unavailable_runtimes_payload)
  guard_fn=$(extract_fn unavailable_runtimes_guard)
  names_fn=$(extract_fn unavailable_runtime_names)
  dispatchable_fn=$(extract_fn dispatchable_runtimes)
  choose_fn=$(extract_fn choose_default_runtime)
  join_fn=$(extract_fn join_csv)

  [ -n "$installed_fn" ] || { echo "FAIL: could not extract installed_runtimes" >&2; return 1; }
  [ -n "$payload_fn" ] || { echo "FAIL: could not extract unavailable_runtimes_payload" >&2; return 1; }
  [ -n "$guard_fn" ] || { echo "FAIL: could not extract unavailable_runtimes_guard" >&2; return 1; }
  [ -n "$names_fn" ] || { echo "FAIL: could not extract unavailable_runtime_names" >&2; return 1; }
  [ -n "$dispatchable_fn" ] || { echo "FAIL: could not extract dispatchable_runtimes" >&2; return 1; }
  [ -n "$choose_fn" ] || { echo "FAIL: could not extract choose_default_runtime" >&2; return 1; }
  [ -n "$join_fn" ] || { echo "FAIL: could not extract join_csv" >&2; return 1; }

  work="${TMPDIR:-/tmp}/mogui-dispatch-unavail-alts.$$"
  mkdir -p "$work/bin"
  trap 'rm -rf "$work"' EXIT
  cat > "$work/bin/grok" <<'BIN'
#!/bin/bash
exit 0
BIN
  cat > "$work/bin/codex" <<'BIN'
#!/bin/bash
exit 0
BIN
  chmod +x "$work/bin/grok" "$work/bin/codex"

  with_key="$work/with-key.json"
  without_key="$work/without-key.json"
  cat > "$with_key" <<'JSON'
{"master_host_runtime": "claude", "unavailable_runtimes": {"grok": {"since": "2026-08-07", "why": "x"}}}
JSON
  cat > "$without_key" <<'JSON'
{"master_host_runtime": "claude"}
JSON

  write_script() {  # outfile  config-path
    local outfile="$1" config="$2"
    {
      echo 'set -u'
      echo "RUNTIME_CANDIDATES=\"claude codex cursor grok gemini opencode\""
      echo "INSTANCE_RUNTIME_CONFIG=\"$config\""
      echo 'MASTER_HOST_RUNTIME=claude'
      echo 'UNAVAILABLE_RUNTIMES_JSON=""'
      printf '%s\n' "$installed_fn"
      printf '%s\n' "$payload_fn"
      printf '%s\n' "$guard_fn"
      printf '%s\n' "$names_fn"
      printf '%s\n' "$dispatchable_fn"
      printf '%s\n' "$choose_fn"
      printf '%s\n' "$join_fn"
      echo 'unavailable_runtimes_guard'
      echo 'echo "default=$(choose_default_runtime)"'
      echo 'echo "alternatives=$(dispatchable_runtimes | grep -vx "$MASTER_HOST_RUNTIME" | join_csv)"'
    } > "$outfile"
  }

  script_file="$work/run.sh"
  write_script "$script_file" "$with_key"
  out_with=$(PATH="$work/bin:/usr/bin:/bin" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ "$out_with" != 'default=codex
alternatives=codex' ]; then
    echo "FAIL: with grok unavailable, default and alternatives should be codex only" >&2
    printf '%s\n' "$out_with" >&2
    return 1
  fi
  echo "ok   : an unavailable runtime is dropped from both the default pick and the alternatives list"

  write_script "$script_file" "$without_key"
  out_without=$(PATH="$work/bin:/usr/bin:/bin" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ "$out_without" != 'default=codex
alternatives=codex, grok' ]; then
    echo "FAIL: removing the unavailable_runtimes key should restore grok to the default pick and alternatives" >&2
    printf '%s\n' "$out_without" >&2
    return 1
  fi
  echo "ok   : removing the unavailable_runtimes key changes nothing beyond restoring the dropped runtime"

  # Failability: a dispatchable_runtimes that never matches the unavailable
  # set is installed_runtimes in substance, and would offer grok as an
  # alternative even with the key present.
  local needle='grep -Fxq "$runtime"' replacement='grep -Fxq "zz-never-matches-zz"'
  mutant_dispatchable=${dispatchable_fn/$needle/$replacement}
  if [ "$mutant_dispatchable" = "$dispatchable_fn" ]; then
    echo "FAIL: dispatchable_runtimes mutant did not change the source" >&2
    return 1
  fi
  {
    echo 'set -u'
    echo "RUNTIME_CANDIDATES=\"claude codex cursor grok gemini opencode\""
    echo "INSTANCE_RUNTIME_CONFIG=\"$with_key\""
    echo 'MASTER_HOST_RUNTIME=claude'
    echo 'UNAVAILABLE_RUNTIMES_JSON=""'
    printf '%s\n' "$installed_fn"
    printf '%s\n' "$payload_fn"
    printf '%s\n' "$guard_fn"
    printf '%s\n' "$names_fn"
    printf '%s\n' "$mutant_dispatchable"
    printf '%s\n' "$choose_fn"
    printf '%s\n' "$join_fn"
    echo 'unavailable_runtimes_guard'
    echo 'echo "alternatives=$(dispatchable_runtimes | grep -vx "$MASTER_HOST_RUNTIME" | join_csv)"'
  } > "$script_file"
  out_with=$(PATH="$work/bin:/usr/bin:/bin" bash "$script_file" 2>&1)
  status=$?
  if [ "$status" -ne 0 ] || [ "$out_with" = 'alternatives=codex' ]; then
    echo "FAIL: failability: blanking dispatchable_runtimes to installed_runtimes should put grok back in alternatives" >&2
    printf '%s\n' "$out_with" >&2
    return 1
  fi
  echo "ok   : failability: blanking dispatchable_runtimes() to installed_runtimes() makes the alternatives case fail ($out_with)"
)
default_and_alternatives_test || exit 1

echo "dispatch unavailable-runtime regression tests passed"
