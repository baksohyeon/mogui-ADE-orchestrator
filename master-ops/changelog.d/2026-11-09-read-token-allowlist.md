## Read-proof tokens are now allowlisted

The redaction gate no longer fails when a worker's acknowledgement token (`ack-<12 hex>`) appears in a committed file. The token shape is globally allowlisted in `config/gitleaks.toml` with the regex `\back-[0-9a-f]{12}\b` and is documented as a non-secret because it carries no sensitive data.

The standing rule `ack-token` remains: type the token in the completion message only, never in a commit, pull request body, or review reply. A committed token proves nothing about reading the contract. The test `master-ops/scripts/test-redaction-read-token.sh` measures the gate behavior with two fixtures: one read token (must pass) and one fake AWS key (must fail).

Fixes: redaction gate false-positive on read-proof tokens (measured 2026-11-09).
