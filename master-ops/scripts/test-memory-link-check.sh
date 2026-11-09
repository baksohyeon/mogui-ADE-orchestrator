#!/usr/bin/env bash
# scripts/memory-link-check: sorts missing [[name]] memory links into typo,
# tracker-key, not-yet-written, and invalid. macOS bash 3.2 safe: no
# associative arrays, no mapfile, no brace ranges with leading zeros.
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

# Case 9: a [[name]] inside a single- or double-backtick inline code span
# (such as a TOML `[[table]]` name) is not collected; the same name written
# in plain prose, with no backticks, still is.
mem="$(mktemp -d)"
printf 'A TOML array-of-tables name as a code span: `[[allowlists]]`.\n' >"$mem/a.md"
printf 'Double backticks too: ``[[allowlists]]``.\n' >>"$mem/a.md"
printf 'In prose, not a code span: [[future-topic]].\n' >>"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 0 "$rc" "inline-code-span name does not become a typo or any group" "$out"
expect_contains "$out" "not-yet-written (1)" "only the prose link is collected"
expect_contains "$out" "future-topic" "the prose link's name is reported"
if contains "$out" "allowlists"; then
  echo "  FAIL: an inline-code-span link must not be collected: $out"
  F=1
else
  echo "  ok:   inline-code-span link ignored (single and double backtick)"
fi
rm -rf "$mem"

# Case 10: a memory file that is not valid UTF-8 exits 2 and names the
# unreadable file, rather than crashing with a raw traceback or silently
# skipping it.
mem="$(mktemp -d)"
printf '\xff\xfe bad utf8\n' >"$mem/bad.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 2 "$rc" "non-UTF-8 memory file exits 2" "$out"
expect_contains "$out" "bad.md" "the unreadable file is named in the error" "$out"
rm -rf "$mem"

# Case 11: a --bd-keys file that is not valid UTF-8 also exits 2 and names
# the file.
mem="$(mktemp -d)"
printf '[[a]]\n' >"$mem/x.md"
printf '\xff\xfe bad utf8\n' >"$mem/keys.txt"
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" 2>&1); rc=$?
expect 2 "$rc" "non-UTF-8 --bd-keys file exits 2" "$out"
expect_contains "$out" "keys.txt" "the unreadable keys file is named in the error" "$out"
rm -rf "$mem"

# Case 12: two existing file stems tied at the same closest distance are
# both reported, in sorted order, and marked as a tie, not just the first
# one found.
mem="$(mktemp -d)"
printf 'x\n' >"$mem/widgex.md"
printf 'x\n' >"$mem/widgey.md"
printf '[[widget]]\n' >"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 1 "$rc" "a tied typo still exits 1" "$out"
expect_contains "$out" "widget -> widgex or widgey" "both tied stems are reported, sorted" "$out"
expect_contains "$out" "tie" "the tie is marked" "$out"
rm -rf "$mem"

# Case 13: a name in --bd-keys that is also a close typo match to an
# existing file is classified tracker-key, not typo: the explicit key
# list outranks a guessed near-miss.
mem="$(mktemp -d)"
printf 'x\n' >"$mem/real-file.md"
printf '[[real-fiel]]\n' >"$mem/a.md"
printf 'real-fiel\n' >"$mem/keys.txt"
out=$("$SCRIPT" --memory-dir "$mem" --bd-keys "$mem/keys.txt" 2>&1); rc=$?
expect 0 "$rc" "bd-keys precedence over a typo match exits 0" "$out"
expect_contains "$out" "typo (0)" "the typo group stays empty" "$out"
expect_contains "$out" "tracker-key (1)" "the name is classified tracker-key instead" "$out"
rm -rf "$mem"

# Case 14: a fence opened with backticks is not closed by a tilde line or
# by a shorter run of backticks; everything up to a matching close stays
# dropped, and a link after the real close is still collected.
mem="$(mktemp -d)"
printf '%s\n' \
  '```' \
  '[[ignored-inside-fence]]' \
  '~~~' \
  'still-inside-the-backtick-fence [[also-ignored]]' \
  '``' \
  'still-inside-too-short-to-close [[also-ignored-2]]' \
  '```' \
  '[[real-after-fence]]' \
  >"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 0 "$rc" "fence with a non-matching inner delimiter still closes correctly" "$out"
expect_contains "$out" "not-yet-written (1)" "only the link after the real close is collected" "$out"
expect_contains "$out" "real-after-fence" "the post-fence link is reported" "$out"
if contains "$out" "ignored-inside-fence" || contains "$out" "also-ignored"; then
  echo "  FAIL: a link inside the still-open fence must not be collected: $out"
  F=1
else
  echo "  ok:   links inside the still-open fence stay ignored"
fi
rm -rf "$mem"

# Case 15: a link name containing a path separator is rejected as invalid
# without ever touching anything outside --memory-dir, instead of being
# silently treated as not-yet-written.
mem="$(mktemp -d)"
printf '[[../escape]]\n' >"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 1 "$rc" "a path separator in a link name exits 1" "$out"
expect_contains "$out" "invalid (1)" "one invalid entry reported" "$out"
expect_contains "$out" "path separator" "the reason names the path separator" "$out"
rm -rf "$mem"

# Case 16: a link whose target exists but is a directory, not a regular
# file, is reported invalid rather than treated as a correct link or
# crashing the scan.
mem="$(mktemp -d)"
mkdir -p "$mem/weird.md"
printf '[[weird]]\n' >"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 1 "$rc" "a non-regular-file target exits 1" "$out"
expect_contains "$out" "invalid (1)" "one invalid entry reported" "$out"
expect_contains "$out" "not a regular file" "the reason names the non-regular-file target" "$out"
rm -rf "$mem"

# Case 17: a double-backtick code span may itself contain a single
# backtick; the span still closes only on the next double backtick, so a
# [[name]] inside it is still ignored rather than leaking out early at
# the inner single backtick.
mem="$(mktemp -d)"
printf 'Text with ``a ` backtick inside and [[allowlists]]`` done.\n' >"$mem/a.md"
printf '[[future-topic]]\n' >>"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 0 "$rc" "inner single backtick does not end the double-backtick span" "$out"
expect_contains "$out" "not-yet-written (1)" "only the link outside the span is collected" "$out"
expect_contains "$out" "future-topic" "the link outside the span is reported" "$out"
if contains "$out" "allowlists"; then
  echo "  FAIL: a link inside a double-backtick span with an inner backtick must not be collected: $out"
  F=1
else
  echo "  ok:   link inside the double-backtick span (with an inner backtick) stays ignored"
fi
rm -rf "$mem"

# Case 18: a code span that opens on one line and closes on a later one is
# stripped as a single span across the newline, not missed by a per-line
# split.
mem="$(mktemp -d)"
printf 'Some text with a code span that spans ``more than\none line with [[allowlists]]`` and keeps going.\n' >"$mem/a.md"
printf '[[future-topic]]\n' >>"$mem/a.md"
out=$("$SCRIPT" --memory-dir "$mem" 2>&1); rc=$?
expect 0 "$rc" "a code span crossing a newline is still stripped" "$out"
expect_contains "$out" "not-yet-written (1)" "only the link outside the span is collected" "$out"
expect_contains "$out" "future-topic" "the link outside the span is reported" "$out"
if contains "$out" "allowlists"; then
  echo "  FAIL: a link inside a span that crosses a newline must not be collected: $out"
  F=1
else
  echo "  ok:   link inside a code span that crosses a newline stays ignored"
fi
rm -rf "$mem"

[ "$F" -eq 0 ] && exit 0 || exit 1
