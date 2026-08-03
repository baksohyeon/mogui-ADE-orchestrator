"""Pytest hooks for this suite.

Puts this directory on sys.path so test modules can share helpers (for example
`windows_exec_surface`) without turning `tests/` into an import package — a
package would break existing top-level sibling imports such as
`from test_redaction_scan_commit_messages import _repo_with_commits`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
