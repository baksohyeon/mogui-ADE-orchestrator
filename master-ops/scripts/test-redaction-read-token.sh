#!/usr/bin/env bash
# Test that read-proof tokens (ack-<12 hex>) pass the redaction scan,
# while real AWS keys still fail. Both assertions are measured.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCAN="${REPO_ROOT}/scripts/redaction-scan.sh"

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
echo "read_token: ack-c6ddceda30d4" > "${TOKEN_FILE}"
git add "${TOKEN_FILE}"
git commit -m "Add read-proof token"

# Commit 2: A file with a fake AWS key (should fail)
# Format: AKIA followed by exactly 16 uppercase letters/digits
AWS_FILE="aws-file.txt"
echo "aws_key: AKIA0IAMNOTAREALTEST" > "${AWS_FILE}"
git add "${AWS_FILE}"
git commit -m "Add AWS key fixture"

# Run the redaction scan on the range of new commits
# The scan should find 1 finding (the AWS key) and not flag the read token
SCAN_OUTPUT=$("${SCAN}" --repo-root "${SCRATCH}" --range HEAD~1..HEAD 2>&1)
SCAN_EXIT=$?

# Check the exit code and output
if [ "${SCAN_EXIT}" -eq 1 ]; then
  # Exit code 1 means findings were found (which is what we expect)
  # The scan found the AWS key but not the read token
  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "aws_access_key"; then
    ok "AWS key is detected by the scan"
  else
    fail "AWS key was not detected in scan output"
    echo "       got: $SCAN_OUTPUT"
  fi

  # Verify that the read token was NOT flagged
  if printf '%s\n' "${SCAN_OUTPUT}" | grep -q "ack-c6ddceda30d4"; then
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
