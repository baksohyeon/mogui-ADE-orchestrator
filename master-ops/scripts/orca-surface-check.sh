#!/usr/bin/env bash
# Orca CLI surface fingerprint check: detects drift in measured commands since baseline.
# Measures appVersion, schemaVersion, commandCount, and per-command digests for watched surfaces.
# Exit: 0 unchanged, 1 drift or below minimum, 2 unknown or unmeasurable.

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
import json, hashlib, re, sys

ORCA_VERSION_REGEX = re.compile(r'(?<![0-9.])([0-9]+)\.([0-9]+)\.([0-9]+)(-([0-9A-Za-z][0-9A-Za-z.-]*))?(?![0-9A-Za-z.-])')

def parse_version(value):
    version_line = str(value).splitlines()[0] if str(value).splitlines() else ''
    match = ORCA_VERSION_REGEX.search(version_line)
    if match is None:
        return None
    return (
        tuple(int(part, 10) for part in match.groups()[0:3]),
        bool(match.group(5)),
    )

def version_at_least(current, minimum):
    if current[0] != minimum[0]:
        return current[0] > minimum[0]
    if current[1] and not minimum[1]:
        return False
    return True

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
    if 'minimumAppVersion' not in baseline:
        raise ValueError('baseline missing minimumAppVersion; restamp the baseline before running this check')
    minimum_app = baseline['minimumAppVersion']
    baseline_count = baseline['commandCount']
    baseline_digests = baseline['commandDigests']
    watched_cmds = baseline['watchedCommands']

    current_version = parse_version(app_version)
    minimum_version = parse_version(minimum_app)
    if minimum_version is None:
        raise ValueError('baseline minimumAppVersion is unparsable: %s' % minimum_app)

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

    below_minimum = current_version is not None and not version_at_least(current_version, minimum_version)
    unknown = current_version is None
    drift = False
    drift_reasons = []

    if current_version is not None and app_version != baseline_app:
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
    if unknown:
        print('[orca-surface] UNKNOWN: installed appVersion could not be parsed from the first version line: %s' % app_version, file=sys.stderr)
    if below_minimum:
        print('[orca-surface] BELOW-MINIMUM: appVersion %s is below minimumAppVersion %s.' % (app_version, minimum_app), file=sys.stderr)
    if drift:
        print('[orca-surface] DRIFT: %s. Re-verify these before relying on remembered flags.' % ', '.join(drift_reasons), file=sys.stderr)
    if drift:
        sys.exit(1)
    if unknown:
        sys.exit(2)
    if not below_minimum:
        if not quiet:
            print('[orca-surface] %s · schema v%d · %d watched commands verified' % (app_version, schema_version, len(watched_cmds)))
        sys.exit(0)
    sys.exit(1)

except Exception as e:
    print('[orca-surface] WARNING: could not measure the Orca surface (%s).' % str(e), file=sys.stderr)
    sys.exit(2)
"
