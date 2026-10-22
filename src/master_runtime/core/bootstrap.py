"""Bootstrap loader for master runtime L0/L1 context."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union


DEFAULT_BUDGET_CHARS = 24_000
TRUNCATION_MARKER = "\n[TRUNCATED:BOOTSTRAP_BUDGET_EXCEEDED]"
L1_TRUNCATION_MARKER = "\n[TRUNCATED:L1_BUDGET_EXCEEDED]"
VALID_ROLES = frozenset(
    (
        "Architecture",
        "Research",
        "Reference Implementation",
        "Feature Implementation",
        "Release / Operations",
        "Incident Response",
        "Maintenance",
    )
)


class BootstrapError(RuntimeError):
    """Raised when bootstrap cannot safely construct runtime context."""


@dataclass(frozen=True)
class BootstrapConfig:
    """Inputs used to load the master bootstrap context."""

    charter_path: Union[str, Path]
    handoff_path: Optional[Union[str, Path]] = None
    budget_chars: int = DEFAULT_BUDGET_CHARS
    session_id: Optional[str] = None
    strict_lease: bool = False
    seat_root: Optional[Path] = None


@dataclass(frozen=True)
class RoleState:
    """Role state inherited from the thin handoff."""

    role: str
    lock_enabled: bool
    frozen: str
    unlock: str


@dataclass(frozen=True)
class BootstrapResult:
    """Budgeted L0/L1 context plus parsed role state."""

    role_state: Optional[RoleState]
    l0_text: str
    l1_text: str
    budget_used: int
    warnings: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


ProcessProbe = Callable[[], str]
CwdProbe = Callable[[int], Optional[str]]
AncestorProbe = Callable[[], Optional[int]]


def bootstrap(
    config: BootstrapConfig,
    process_probe: Optional[ProcessProbe] = None,
    cwd_probe: Optional[CwdProbe] = None,
    ancestor_probe: Optional[AncestorProbe] = None,
) -> BootstrapResult:
    """Load charter and optional handoff, then run non-owning lease detection."""

    warnings: List[str] = []
    budget = _validate_budget(config.budget_chars)
    charter_text = _read_required(config.charter_path, "Charter")
    handoff_text = ""
    role_state = None

    if config.handoff_path is not None:
        handoff = Path(config.handoff_path)
        if handoff.exists():
            handoff_text = handoff.read_text(encoding="utf-8")
            role_state = _parse_role_state(handoff_text)
            if role_state is None:
                warnings.append("ROLE_STATE_MISSING")
        else:
            warnings.append("HANDOFF_MISSING")

    l0_text, remaining, l0_truncated = _fit_text(
        charter_text,
        budget,
        TRUNCATION_MARKER,
    )
    if l0_truncated:
        warnings.append("BUDGET_TRUNCATED:L0")

    l1_text = ""
    if handoff_text and remaining > 0:
        l1_text, remaining, l1_truncated = _fit_text(
            handoff_text,
            remaining,
            L1_TRUNCATION_MARKER,
        )
        if l1_truncated:
            warnings.append("BUDGET_TRUNCATED:L1")

    warnings.extend(
        _detect_dual_instances(
            config.session_id,
            process_probe,
            seat_root=config.seat_root,
            cwd_probe=cwd_probe,
            ancestor_probe=ancestor_probe,
        )
    )
    if config.strict_lease:
        dual_warnings = [
            warning
            for warning in warnings
            if warning.startswith(("DUAL_INSTANCE:", "SEAT_PEER:"))
        ]
        if dual_warnings:
            raise BootstrapError(dual_warnings[0])

    return BootstrapResult(
        role_state=role_state,
        l0_text=l0_text,
        l1_text=l1_text,
        budget_used=len(l0_text) + len(l1_text),
        warnings=warnings,
    )


def _validate_budget(value: int) -> int:
    budget = int(value)
    if budget < 0:
        raise BootstrapError("Budget must be non-negative")
    return budget


def _read_required(path_value: Union[str, Path], label: str) -> str:
    path = Path(path_value)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BootstrapError(label + " missing: " + str(path)) from exc


def _fit_text(text: str, budget: int, marker: str) -> Tuple[str, int, bool]:
    if len(text) <= budget:
        return text, budget - len(text), False
    if budget <= 0:
        return "", 0, True
    if len(marker) >= budget:
        return marker[-budget:], 0, True
    return text[: budget - len(marker)] + marker, 0, True


def _parse_role_state(text: str) -> Optional[RoleState]:
    block = _role_state_block(text)
    if block is None:
        return None

    fields = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()

    required = ("current role", "role lock", "frozen", "unlock")
    missing = [key for key in required if key not in fields]
    if missing:
        raise BootstrapError("Role State missing fields: " + ", ".join(missing))

    role = fields["current role"]
    if role not in VALID_ROLES:
        raise BootstrapError("Unknown role: " + role)

    return RoleState(
        role=role,
        lock_enabled=_parse_lock(fields["role lock"]),
        frozen=fields["frozen"],
        unlock=fields["unlock"],
    )


def _role_state_block(text: str) -> Optional[str]:
    heading = re.search(r"(?im)^##+\s+Role State\b.*$", text)
    search_start = heading.end() if heading else 0
    fenced = re.search(r"(?ms)```(?:[^\n`]*)\n(.*?)\n```", text[search_start:])
    if fenced and "Current Role:" in fenced.group(1):
        return fenced.group(1)

    fallback = re.search(
        r"(?ms)^Current Role:.*?(?:\nUnlock:.*?)(?:\n\n|\Z)",
        text[search_start:],
    )
    if fallback:
        return fallback.group(0).strip()
    return None


def _parse_lock(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized == "ENABLED":
        return True
    if normalized == "DISABLED":
        return False
    raise BootstrapError("Unknown role lock: " + value)


def _detect_dual_instances(
    session_id: Optional[str],
    process_probe: Optional[ProcessProbe],
    seat_root: Optional[Union[str, Path]] = None,
    cwd_probe: Optional[CwdProbe] = None,
    ancestor_probe: Optional[AncestorProbe] = None,
) -> List[str]:
    probe = process_probe or _default_process_probe
    try:
        output = probe()
    except OSError as exc:
        return ["PROCESS_PROBE_FAILED:" + exc.__class__.__name__]

    own_pid = os.getpid()
    find_ancestor = ancestor_probe or _default_ancestor_probe
    try:
        ancestor_pid = find_ancestor()
    except OSError:
        ancestor_pid = None
    excluded_pids = {own_pid}
    if ancestor_pid is not None:
        excluded_pids.add(ancestor_pid)

    resolve_cwd = cwd_probe or _default_cwd_probe
    seat_root_real = os.path.realpath(
        str(seat_root) if seat_root is not None else os.getcwd()
    )

    warnings: List[str] = []
    for line in output.splitlines():
        parsed = _parse_process_line(line)
        if parsed is None:
            continue
        pid, command = parsed
        if pid == own_pid:
            continue
        if not _is_claude_command(command):
            continue
        if session_id and session_id in command and pid not in excluded_pids:
            warnings.append("DUAL_INSTANCE:" + str(pid))
            continue
        if pid in excluded_pids:
            continue
        try:
            cwd = resolve_cwd(pid)
        except OSError:
            continue
        if cwd is None:
            continue
        if os.path.realpath(cwd) == seat_root_real:
            warnings.append("SEAT_PEER:" + str(pid))
    return warnings


def _default_process_probe() -> str:
    result = subprocess.run(
        ("ps", "-axo", "pid=,command="),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _default_cwd_probe(pid: int) -> Optional[str]:
    result = subprocess.run(
        ("lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"),
        check=False,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def _default_ancestor_probe() -> Optional[int]:
    own_pid = os.getpid()
    pid = own_pid
    for _ in range(64):
        result = subprocess.run(
            ("ps", "-o", "ppid=,command=", "-p", str(pid)),
            check=False,
            capture_output=True,
            text=True,
        )
        line = result.stdout.strip()
        if not line:
            return None
        parts = line.split(None, 1)
        if not parts or not parts[0].isdigit():
            return None
        ppid = int(parts[0])
        command = parts[1] if len(parts) > 1 else ""
        if pid != own_pid and _is_claude_command(command):
            return pid
        if ppid <= 1:
            return None
        pid = ppid
    return None


def _parse_process_line(line: str) -> Optional[Tuple[int, str]]:
    parts = line.strip().split()
    if not parts:
        return None
    if parts[0].upper() == "USER" or parts[0].upper() == "PID":
        return None

    if parts[0].isdigit():
        return int(parts[0]), " ".join(parts[1:])
    if len(parts) >= 2 and parts[1].isdigit():
        if len(parts) >= 11:
            return int(parts[1]), " ".join(parts[10:])
        return int(parts[1]), " ".join(parts[2:])
    return None


def _is_claude_command(command: str) -> bool:
    parts = command.strip().split()
    if not parts:
        return False
    executable = parts[0].split("/")[-1]
    return executable == "claude"
