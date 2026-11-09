#!/usr/bin/env bash
# scripts/memory-link-check: sorts missing [[name]] memory links into typo,
# tracker-key, and not-yet-written. macOS bash 3.2 safe: no associative
# arrays, no mapfile, no brace ranges with leading zeros.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/memory-link-check"
F=0

expect() {
  want="$1" got="$2" label="$3" out="$4"
  [ "$got" = "$want" ] && echo "  ok:   $label" || { echo "  FAIL: $label want=$want got=$got: $out"; F=1; }
}

contains() {
  case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac
}

expect_contains() {
  haystack="$1" needle="$2" label="$3"
  if contains "$haystack" "$needle"; then
    echo "  ok:   $label"
  else
    echo "  FAIL: $label: missing '$needle' in: $haystack"
    F=1
  fi
}

mk_memory() {
  d="$(mktemp -d)"
  printf 'content\n' >"$d/real-file.md"
  printf 'Links [[real-fiel]] [[some-bd-key]] [[future-topic]] [[real-file]].\n\n```\nfenced [[ignored-link]]\n```\n' >"$d/a.md"
  printf 'Also [[future-topic]] and [[some-bd-key]].\n' >"$d/b.md"
  printf 'some-bd-key\n' >"$d/keys.txt"
  printf '%s\n' "$d"
}

# Case 1: default run sorts one typo, one tracker-key, one not-yet-written,
# ignores the fenced link, and exits 1 on the typo.
mem="$(mk_memory)"
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" 2>&1); rc=$?
expect 1 "$rc" "typo present exits 1" "$out"
expect_contains "$out" "typo (1)" "one typo reported"
expect_contains "$out" "real-fiel -> real-file" "typo names the close file"
expect_contains "$out" "tracker-key (1)" "one tracker-key reported"
expect_contains "$out" "some-bd-key" "tracker-key name present"
expect_contains "$out" "not-yet-written (1)" "one not-yet-written reported"
expect_contains "$out" "future-topic" "not-yet-written name present"
if contains "$out" "ignored-link"; then
  echo "  FAIL: fenced link must not be collected: $out"
  F=1
else
  echo "  ok:   fenced link ignored"
fi
rm -rf "$mem"

# Case 2: the correct link [[real-file]] is never reported as its own
# group entry (it may still appear as a typo's suggested target).
mem="$(mk_memory)"
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" 2>&1)
if printf '%s\n' "$out" | grep -E '^ +real-file +\[' >/dev/null 2>&1; then
  echo "  FAIL: a correct link must not appear as its own group entry: $out"
  F=1
else
  echo "  ok:   correct link not reported as a group entry"
fi
rm -rf "$mem"

# Case 3: without --bd-keys, the tracker-key name falls through to
# not-yet-written instead (no key list means no group two).
mem="$(mk_memory)"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 1 "$rc" "no bd-keys file still exits 1 on the typo" "$out"
expect_contains "$out" "tracker-key (0)" "no key list means an empty tracker-key group"
expect_contains "$out" "not-yet-written (2)" "tracker key name falls into not-yet-written"
rm -rf "$mem"

# Case 4: no typo, no --strict-tracker-keys: exits 0 even with a
# tracker-key and a not-yet-written name outstanding.
mem="$(mktemp -d)"
printf 'content\n' >"$mem/real-file.md"
printf '[[some-bd-key]] [[future-topic]] [[real-file]]\n' >"$mem/a.md"
printf 'some-bd-key\n' >"$mem/keys.txt"
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" 2>&1); rc=$?
expect 0 "$rc" "no typo exits 0" "$out"

# Case 5: same tree, --strict-tracker-keys turns the tracker-key group into
# a failure.
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" --strict-tracker-keys 2>&1); rc=$?
expect 1 "$rc" "--strict-tracker-keys fails on a tracker-key group" "$out"
rm -rf "$mem"

# Case 6: --bd-keys - reads the key list from stdin.
mem="$(mktemp -d)"
printf '[[some-bd-key]]\n' >"$mem/a.md"
out=$(printf 'some-bd-key\n' | "$SCRIPT" --memory-dir "$mem" --bd-keys - 2>&1); rc=$?
expect 0 "$rc" "--bd-keys - reads stdin, no typo so exit 0" "$out"
expect_contains "$out" "tracker-key (1)" "stdin key list sorts the name as tracker-key"
rm -rf "$mem"

# Case 7: a non-directory --memory-dir is a usage error (exit 2), not a
# silent empty report.
out=$("$SCRIPT" --memory-dir "/nonexistent-$$-dir" 2>&1); rc=$?
expect 2 "$rc" "missing memory dir exits 2" "$out"

# Case 8: an alias after | is stripped to the bare link name.
mem="$(mktemp -d)"
printf '[[future-topic|Future Topic]]\n' >"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 0 "$rc" "aliased link with no typo exits 0" "$out"
expect_contains "$out" "future-topic" "alias stripped to the bare name"
if contains "$out" "Future Topic"; then
  echo "  FAIL: alias text must not leak into the name: $out"
  F=1
else
  echo "  ok:   alias text dropped"
fi
rm -rf "$mem"

[ "$F" -eq 0 ] && exit 0 || exit 1
