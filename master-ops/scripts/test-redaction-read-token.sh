#!/usr/bin/env bash
# Test the redaction scan against the read-proof token's allowlist entry,
# measuring the four cases that distinguish a safe allowlist from one that
# clears real secrets:
#   1. a file with only the token: must NOT be flagged.
#   2. a real secret that merely contains the token's shape as a substring:
#      must still be flagged (an unanchored match-target regex clears this
#      whole secret, which is the bug this allowlist entry must not have).
#   3. the token and a fake AWS key on the same line: the key must still be
#      flagged, specifically by the aws_access_key rule (a line-scoped
#      allowlist, or a check that accepts any finding at all, would miss
#      a regression where the AWS key itself stops being caught).
#   4. the token written as a quoted key assignment (access_token = "ack-...")
#      must still be flagged: the assignment rule's secret is the whole
#      assignment, not the bare token, so the allowlist's anchored regex
#      does not clear it. This is intended: a token belongs only in the
#      worker's completion message, never in a committed file.
#
# scripts/redaction-scan.sh sits next to its config/gitleaks.toml at the root
# of whatever checkout owns the scan: the authoring template root (two levels
# above this script's own directory, which ships from a nested scripts/
# directory there) or an install root (one level above this script, which
# there ships from a top-level scripts/ directly). Neither depth is fixed, so
# this walks up from this script's own directory, at each level checking for
# a sibling scripts/redaction-scan.sh, and SKIPs only once every level up to
# the filesystem root has been tried. redaction-scan.sh also refuses to run
# without gitleaks on PATH (exit 2), so a runner that lacks it has nothing to
# measure either. The same SKIP convention is used by
# test-contributing-shell-loop.sh and test-dispatch-timeline.sh for a missing
# prerequisite.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCAN=""
TRIED=()
dir="${SCRIPT_DIR}"
while :; do
  candidate="${dir}/scripts/redaction-scan.sh"
  TRIED+=("${candidate}")
  if [ -f "${candidate}" ]; then
    SCAN="${candidate}"
    break
  fi
  parent="$(dirname "${dir}")"
  [ "${parent}" = "${dir}" ] && break
  dir="${parent}"
done

if [ -z "${SCAN}" ]; then
  echo "SKIP: no scripts/redaction-scan.sh found walking up from ${SCRIPT_DIR}; this test did not run (not the authoring checkout or an install root)"
  printf '  tried: %s\n' "${TRIED[@]}"
  exit 0
fi

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "SKIP: gitleaks not on PATH; this test did not run (install it with brew install gitleaks, or see https://gitleaks.io)"
  exit 0
fi

F=0
ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }

# Create a temporary scratch repository for testing
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

SCRATCH="${WORK_DIR}/scratch-repo"
mkdir -p "${SCRATCH}"
cd "${SCRATCH}"

# Initialize a git repository
git init
git config user.email "test@example.com"
git config user.name "Test User"
git commit --allow-empty -m "Initial commit"

# Row 1: a file with only the read-proof token. Must not be flagged.
TOKEN_FILE="token-file.txt"
echo "read_token: ack-0123456789ab" > "${TOKEN_FILE}"
git add "${TOKEN_FILE}"
git commit -m "Add read-proof token"

# Row 2: a real secret that merely contains the token's shape as a
# substring. Must still be flagged: an unanchored match-target allowlist
# regex clears the whole matched secret whenever the token shape appears
# anywhere inside it, which is the bug this fixture guards against.
# Built from separate parts at run time so this committed source never
# holds a literal key="value" secret assignment of its own; only the
# scratch repository's commit does, and that repository is discarded on
# exit.
ASSIGN_KEY="ACCESS_TOKEN"
ASSIGN_VALUE="ack-0123456789ab-reallysecretvalue"
PREFIXED_FILE="prefixed-secret-file.txt"
printf '%s="%s"\n' "${ASSIGN_KEY}" "${ASSIGN_VALUE}" > "${PREFIXED_FILE}"
git add "${PREFIXED_FILE}"
git commit -m "Add a real secret containing the token shape as a substring"

# Row 3: the token and a fake AWS key on the same line. The key must still
# be found. Format: AKIA followed by exactly 16 uppercase letters/digits.
# Built from two parts at run time so this committed source never holds the
# full literal; only the scratch repository's commit does, and that
# repository is discarded on exit.
AWS_KEY_PREFIX="AKIA"
AWS_KEY_SUFFIX="0IAMNOTAREALTEST"
AWS_KEY="${AWS_KEY_PREFIX}${AWS_KEY_SUFFIX}"
COMBO_FILE="combo-file.txt"
echo "combo: ack-0123456789ab ${AWS_KEY}" > "${COMBO_FILE}"
git add "${COMBO_FILE}"
git commit -m "Add token and AWS key on the same line"

# Row 4: the token written as a quoted key assignment. Must still be
# flagged: config/gitleaks.toml's assignment_secret rule has no capture
# group, so the matched secret is the whole assignment, and the read-token
# allowlist's anchored regex only clears a secret that IS the bare token.
# Built from separate parts at run time for the same reason as row 2: this
# committed source must never hold a literal key="value" secret assignment
# of its own.
ASSIGN2_KEY="access_token"
ASSIGN2_VALUE="ack-0123456789ab"
ASSIGNMENT_FILE="quoted-assignment-file.txt"
printf '%s = "%s"\n' "${ASSIGN2_KEY}" "${ASSIGN2_VALUE}" > "${ASSIGNMENT_FILE}"
git add "${ASSIGNMENT_FILE}"
git commit -m "Add the token as a quoted key assignment"

# Run the redaction scan on the range of the four fixture commits.
SCAN_OUTPUT=$("${SCAN}" --repo-root "${SCRATCH}" --range HEAD~4..HEAD 2>&1)
SCAN_EXIT=$?

if [ "${SCAN_EXIT}" -eq 1 ]; then
  # Exit code 1 means findings were found, which is what we expect.

  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "${TOKEN_FILE}"; then
    fail "read-proof token alone was flagged when it should be allowlisted"
    echo "       got: $SCAN_OUTPUT"
  else
    ok "read-proof token alone is allowlisted and not flagged"
  fi

  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "${PREFIXED_FILE}"; then
    ok "a real secret containing the token shape as a substring is still detected"
  else
    fail "a real secret containing the token shape as a substring was not detected"
    echo "       got: $SCAN_OUTPUT"
  fi

  if printf '%s\n' "${SCAN_OUTPUT}" | grep -F "${COMBO_FILE}" | grep -q '\[aws_access_key\]'; then
    ok "an AWS key sharing a line with the read-proof token is still detected by rule aws_access_key"
  else
    fail "an AWS key sharing a line with the read-proof token was not detected by rule aws_access_key specifically"
    echo "       got: $SCAN_OUTPUT"
  fi

  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "${ASSIGNMENT_FILE}"; then
    ok "the token written as a quoted key assignment is still detected"
  else
    fail "the token written as a quoted key assignment was not detected"
    echo "       got: $SCAN_OUTPUT"
  fi
else
  fail "scan exit code was ${SCAN_EXIT}, expected 1 (findings detected)"
  echo "       output: $SCAN_OUTPUT"
fi

echo "----"
[ "$F" -eq 0 ] && echo "pass" || echo "fail"
exit "$F"
