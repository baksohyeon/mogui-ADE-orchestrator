"""Shared skip for tests that need the Unix script execution surface.

Windows CI fails a single diagnosed class: tests that invoke repository scripts
as subprocesses (extensionless shebang scripts → WinError 193; bash/WSL paths
missing; Unix executable-bit discovery; shell-only probes). That is an
environment surface, not independent product bugs.

Tracked backlog: make scripts runnable on native Windows (or document a
supported Windows runner path). Until then, skip the measured class with an
auditable reason so the windows leg stays green on the compatible subset.
See .github/workflows/gates.yml (windows measurement note) and the
2026-08-04-windows-ci-green contract.
"""

from __future__ import annotations

import sys

import pytest

WINDOWS_EXEC_SURFACE_REASON = (
    "Windows execution surface: extensionless/shebang scripts and bash/WSL "
    "paths are not runnable on win32 (WinError 193 / missing WSL / no Unix "
    "exec bit). Tracked backlog — see .github/workflows/gates.yml windows "
    "measurement note and contract 2026-08-04-windows-ci-green."
)

skip_windows_exec_surface = pytest.mark.skipif(
    sys.platform == "win32",
    reason=WINDOWS_EXEC_SURFACE_REASON,
)
