#!/usr/bin/env bash
# scripts/changelog-fragment-check: a change under the ops skeleton, outside
# changelog.d/, needs an added, well-named fragment; a changelog.d/-only or
# CHANGELOG.md-only change is exempt.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/changelog-fragment-check"
TREE="master-ops"
F=0

mk_repo() {
  d="$(mktemp -d)"
  git -C "$d" init -q
  git -C "$d" config user.email t@example.com
  git -C "$d" config user.name test
  mkdir -p "$d/$TREE/changelog.d"
  printf 'placeholder\n' >"$d/$TREE/CHANGELOG.md"
  printf 'placeholder\n' >"$d/$TREE/other.md"
  git -C "$d" add -A
  git -C "$d" commit -q -m base
  printf '%s\n' "$d"
}

commit_all() {
  git -C "$1" add -A
  git -C "$1" commit -q -m change
}

expect() {
  want="$1" got="$2" label="$3" out="$4"
  [ "$got" = "$want" ] && echo "  ok:   $label" || { echo "  FAIL: $label want=$want got=$got: $out"; F=1; }
}

# Case 1: an ops-tree change with no fragment fails.
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'changed\n' >"$repo/$TREE/other.md"
commit_all "$repo"
out=$(cd "$repo" && "$SCRIPT" "$base" 2>&1); rc=$?
expect 1 "$rc" "ops-tree change with no fragment fails" "$out"
rm -rf "$repo"

# Case 2: an ops-tree change with a fragment passes.
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'changed\n' >"$repo/$TREE/other.md"
printf 'A thing (2026-01-01):\n\n- did it\n' >"$repo/$TREE/changelog.d/2026-01-01-a-thing.md"
commit_all "$repo"
out=$(cd "$repo" && "$SCRIPT" "$base" 2>&1); rc=$?
expect 0 "$rc" "ops-tree change with a fragment passes" "$out"
rm -rf "$repo"

# Case 3: a changelog.d-only change passes.
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'A thing (2026-01-01):\n\n- did it\n' >"$repo/$TREE/changelog.d/2026-01-01-a-thing.md"
commit_all "$repo"
out=$(cd "$repo" && "$SCRIPT" "$base" 2>&1); rc=$?
expect 0 "$rc" "changelog.d-only change passes" "$out"
rm -rf "$repo"

# Case 4: bad fragment name fails, even though the ops tree also changed.
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'changed\n' >"$repo/$TREE/other.md"
printf 'bad\n' >"$repo/$TREE/changelog.d/BadName.md"
commit_all "$repo"
out=$(cd "$repo" && "$SCRIPT" "$base" 2>&1); rc=$?
expect 1 "$rc" "bad fragment name fails" "$out"
rm -rf "$repo"

# Case 5: a CHANGELOG.md-only change passes (the release-fold commit itself).
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'placeholder updated\n' >"$repo/$TREE/CHANGELOG.md"
commit_all "$repo"
out=$(cd "$repo" && "$SCRIPT" "$base" 2>&1); rc=$?
expect 0 "$rc" "CHANGELOG.md-only change passes" "$out"
rm -rf "$repo"

# Failability: without the CHANGELOG.md exemption, case 5 must fail.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
python3 - "$SCRIPT" >"$T/mut.py" <<'PY'
import sys
s = open(sys.argv[1]).read()
mutant = s.replace(" and p != CHANGELOG_FILE", "")
if mutant == s:
    sys.exit("mutant text not found")
sys.stdout.write(mutant)
PY
repo="$(mk_repo)"; base="$(git -C "$repo" rev-parse HEAD)"
printf 'placeholder updated\n' >"$repo/$TREE/CHANGELOG.md"
commit_all "$repo"
out=$(cd "$repo" && python3 "$T/mut.py" "$base" 2>&1); rc=$?
expect 1 "$rc" "failability: dropping the CHANGELOG.md exemption fails case 5" "$out"
rm -rf "$repo"

[ "$F" -eq 0 ] && exit 0 || exit 1
