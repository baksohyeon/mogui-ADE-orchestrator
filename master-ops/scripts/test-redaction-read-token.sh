#!/usr/bin/env bash
# Test that read-proof tokens (ack-<12 hex>) pass the redaction scan,
# while real AWS keys still fail. Both assertions are measured.
#
# scripts/redaction-scan.sh lives at the host repository's root, outside
# master-ops/, so a template-rendered copy never receives it: only the
# authoring checkout, two levels above this script's own location, has it.
# redaction-scan.sh also refuses to run without gitleaks on PATH (exit 2), so
# a runner that lacks it has nothing to measure either. This file SKIPs for
# both, the same convention test-contributing-shell-loop.sh and
# test-dispatch-timeline.sh use for a missing prerequisite.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCAN="${REPO_ROOT}/scripts/redaction-scan.sh"

if [ ! -f "${SCAN}" ]; then
  echo "SKIP: ${SCAN} not found; this test did not run (not the authoring checkout)"
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

# Commit 1: A file with a read-proof token (should pass)
git commit --allow-empty -m "Initial commit"
TOKEN_FILE="token-file.txt"
echo "read_token: ack-0123456789ab" > "${TOKEN_FILE}"
git add "${TOKEN_FILE}"
git commit -m "Add read-proof token"

# Commit 2: A file with a fake AWS key (should fail)
# Format: AKIA followed by exactly 16 uppercase letters/digits. Built from two
# parts at run time so this committed source never holds the full literal;
# only the scratch repository's commit does, and that repository is discarded
# on exit.
AWS_KEY_PREFIX="AKIA"
AWS_KEY_SUFFIX="0IAMNOTAREALTEST"
AWS_KEY="${AWS_KEY_PREFIX}${AWS_KEY_SUFFIX}"
AWS_FILE="aws-file.txt"
echo "aws_key: ${AWS_KEY}" > "${AWS_FILE}"
git add "${AWS_FILE}"
git commit -m "Add AWS key fixture"

# Commit 3: a token and an AWS key on the same line. A line-scoped allowlist
# for the token would clear this whole line, so this fixture is the
# regression guard for that mistake: the key must still be found.
COMBO_FILE="combo-file.txt"
echo "combo: ack-0123456789ab ${AWS_KEY}" > "${COMBO_FILE}"
git add "${COMBO_FILE}"
git commit -m "Add token and AWS key on the same line"

# Run the redaction scan on the range of new commits
# The scan should find findings for both AWS key fixtures and not flag the read token
SCAN_OUTPUT=$("${SCAN}" --repo-root "${SCRATCH}" --range HEAD~3..HEAD 2>&1)
SCAN_EXIT=$?

# Check the exit code and output
if [ "${SCAN_EXIT}" -eq 1 ]; then
  # Exit code 1 means findings were found (which is what we expect)
  # The scan found both AWS key fixtures but not the read token
  AWS_FINDING_COUNT="$(printf '%s\n' "${SCAN_OUTPUT}" | grep -c "aws_access_key")"
  if [ "${AWS_FINDING_COUNT}" -eq 2 ]; then
    ok "both AWS key fixtures are detected by the scan"
  else
    fail "expected 2 aws_access_key findings, got ${AWS_FINDING_COUNT}"
    echo "       got: $SCAN_OUTPUT"
  fi

  # The same-line fixture is the regression guard: a line-scoped token
  # allowlist would have cleared this finding along with the token.
  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "${COMBO_FILE}"; then
    ok "AWS key sharing a line with a read-proof token is still detected"
  else
    fail "AWS key sharing a line with a read-proof token was not detected"
    echo "       got: $SCAN_OUTPUT"
  fi

  # Verify that the read token was NOT flagged
  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "ack-0123456789ab"; then
    fail "read-proof token was flagged when it should be allowlisted"
    echo "       got: $SCAN_OUTPUT"
  else
    ok "read-proof token is allowlisted and not flagged"
  fi
else
  fail "scan exit code was ${SCAN_EXIT}, expected 1 (findings detected)"
  echo "       output: $SCAN_OUTPUT"
fi

echo "----"
[ "$F" -eq 0 ] && echo "pass" || echo "fail"
exit "$F"
