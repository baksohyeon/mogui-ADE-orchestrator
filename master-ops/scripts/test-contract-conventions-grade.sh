#!/bin/bash
# Keep the contract-conventions grade distribution equal to its tagged clauses.
set -u

cd "$(dirname "$0")/.."

CONVENTIONS_PATH="${CONVENTIONS_PATH:-docs/runbooks/contract-conventions.md}"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

check_distribution() {
  local path="$1" grade expected actual
  for grade in machine-enforced measured prose; do
    expected=$(awk -v grade="$grade" '$1 == "-" && $2 == grade ":" { print $3; exit }' "$path")
    actual=$(grep -Ec "^## [0-9]+\\..*\\[$grade\\]$" "$path")
    if [ -z "$expected" ] || [ "$actual" -ne "$expected" ]; then
      echo "FAIL: $path has $actual [$grade] tags but declares $expected"
      return 1
    fi
  done
  echo "ok   - grade distribution matches tagged clauses"
}

check_distribution "$CONVENTIONS_PATH" || exit 1

MUTANT_PATH="$TMP_DIR/contract-conventions-mutant.md"
sed '/^## 17\./s/ \[prose\]$//' "$CONVENTIONS_PATH" > "$MUTANT_PATH"
if check_distribution "$MUTANT_PATH" >/dev/null 2>&1; then
  echo "FAIL - failability: removing the new grade tag still passed"
  exit 1
fi
echo "ok   - failability: removing the new grade tag fails the count check"
