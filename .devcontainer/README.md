# Development container

This directory defines a Python 3.12 development container for the repository's two blocking gates: the pytest suite and the tracked-content redaction scan. Build it with:

```console
docker build -t mogui-ade-orchestrator-devcontainer -f .devcontainer/Dockerfile .
```

The container cannot launch a master seat because Orca is a macOS application, not a service available inside this Linux container. The container redaction gate runs only the committed rules, so `org-rules=0` is the expected reading in this environment. Because `org-rules=0` currently exits successfully, a green container scan is not evidence that organization-specific patterns were checked.

Run the gates from the repository root after starting the container:

```console
export PATH=/opt/gitleaks/bin:$PATH
PYTHONPATH=src python -m pytest tests -q
./scripts/redaction-scan.sh
```

The redaction scan prints a warning when `REDACTION_EXTRA_PATTERNS` is unset, followed by its tracked-only result. Full organization-rule coverage requires running the scan on a host where that file is available.
