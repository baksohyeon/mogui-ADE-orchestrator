#!/usr/bin/env bash
# Orca CLI surface fingerprint check: detects drift in measured commands since baseline.
# Measures appVersion, schemaVersion, commandCount, and per-command digests for watched surfaces.
# Exit: 0 unchanged, 1 drift, 2 unmeasurable.

BASELINE_FILE="${BASELINE_FILE:-${1:-.}/scripts/orca-surface-baseline.json}"
QUIET="${QUIET:-0}"

if [[ ! -f "$BASELINE_FILE" ]]; then
  echo "[orca-surface] WARNING: could not measure the Orca surface (baseline file not found)." >&2
  exit 2
fi

# Measure current Orca surface.
if ! orca status --json > /tmp/orca-status.json 2>/dev/null; then
  echo "[orca-surface] WARNING: could not measure the Orca surface (orca status failed)." >&2
  exit 2
fi

if ! orca agent-context --json > /tmp/orca-context.json 2>/dev/null; then
  echo "[orca-surface] WARNING: could not measure the Orca surface (orca agent-context failed)." >&2
  exit 2
fi

# Run comparison in python.
python3 -c "
import json, hashlib, sys

try:
    with open('/tmp/orca-status.json') as f:
        status = json.load(f)
    with open('/tmp/orca-context.json') as f:
        context = json.load(f)
    with open('$BASELINE_FILE') as f:
        baseline = json.load(f)

    app_version = status['result']['runtime']['appVersion']
    schema_version = context['schemaVersion']
    command_count = context['commandCount']

    baseline_app = baseline['appVersion']
    baseline_count = baseline['commandCount']
    baseline_digests = baseline['commandDigests']
    watched_cmds = baseline['watchedCommands']

    commands = {cmd['command']: cmd for cmd in context.get('commands', [])}
    current_digests = {}

    for watch_cmd in watched_cmds:
        if watch_cmd in commands:
            cmd = commands[watch_cmd]
            digest_input = json.dumps({
                'command': cmd['command'],
                'flags': sorted(cmd.get('flags', [])),
                'usage': cmd.get('usage', '')
            }, sort_keys=True, separators=(',', ':'))
            digest = hashlib.sha256(digest_input.encode()).hexdigest()[:16]
            current_digests[watch_cmd] = digest

    drift = False
    drift_reasons = []

    if app_version != baseline_app:
        drift = True
        drift_reasons.append('appVersion %s -> %s' % (baseline_app, app_version))

    if command_count != baseline_count:
        drift = True
        drift_reasons.append('commandCount %d -> %d' % (baseline_count, command_count))

    drifted_cmds = [cmd for cmd in watched_cmds if baseline_digests.get(cmd) != current_digests.get(cmd)]
    if drifted_cmds:
        drift = True
        drift_reasons.append('watched-command digest changed for: ' + ', '.join(drifted_cmds))

    quiet = int('$QUIET') == 1
    if not drift:
        if not quiet:
            print('[orca-surface] %s · schema v%d · %d watched commands verified' % (app_version, schema_version, len(watched_cmds)))
        sys.exit(0)
    else:
        print('[orca-surface] DRIFT: %s. Re-verify these before relying on remembered flags.' % ', '.join(drift_reasons), file=sys.stderr)
        sys.exit(1)

except Exception as e:
    print('[orca-surface] WARNING: could not measure the Orca surface (%s).' % str(e), file=sys.stderr)
    sys.exit(2)
"
