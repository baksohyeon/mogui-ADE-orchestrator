"""Single adapter dispatch entrypoint."""

import hashlib
import importlib
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

from master_runtime.core.adapter.doctor import RunResult
from master_runtime.core.adapter.isolation import IsolationDecision, IsolationMode, needs_worktree
from master_runtime.core.adapter.profile import CodexCompanionProfile, ProfileError, ToolProfile


@dataclass(frozen=True)
class GateCheckResult:
    allowed: bool
    code: str = "ok"
    reason: str = ""


@dataclass(frozen=True)
class GateRegistrationResult:
    accepted: bool
    code: str = "registered"
    reason: str = ""


@dataclass(frozen=True)
class DispatchRequest:
    contract_path: str
    repo_path: str
    isolation: str = "auto"
    runtime: str = "codex"
    agents: int = 1
    est_chars: int = 0
    ledger_path: str = "~/.mogui/dispatch-ledger.jsonl"
    dry_run: bool = False
    branch_anchor: Optional[str] = None
    tree_contention: bool = False
    branch_switch: bool = False


@dataclass(frozen=True)
class DispatchOutcome:
    ok: bool
    error_code: Optional[str]
    message: str
    job_id: Optional[str]
    worktree_path: Optional[str]
    ledger_reflected: bool
    isolation: IsolationDecision
    worker_cmd: Optional[Tuple[str, ...]]
    probe_cmd: Optional[Tuple[str, ...]]
    worktree_cmd: Optional[Tuple[str, ...]]


Runner = Callable[[Sequence[str], Optional[str]], RunResult]


class DispatchGate:
    def check(self, request: DispatchRequest) -> GateCheckResult:
        raise NotImplementedError

    def register_probe(
        self,
        request: DispatchRequest,
        job_id: str,
        probe_cmd: Sequence[str],
        probe_result: RunResult,
    ) -> GateRegistrationResult:
        raise NotImplementedError


class MissingDispatchGate(DispatchGate):
    def __init__(self, module_name: str, detail: str):
        self.module_name = module_name
        self.detail = detail

    def check(self, request: DispatchRequest) -> GateCheckResult:
        return GateCheckResult(
            allowed=False,
            code="gate-unavailable",
            reason="%s: %s" % (self.module_name, self.detail),
        )

    def register_probe(
        self,
        request: DispatchRequest,
        job_id: str,
        probe_cmd: Sequence[str],
        probe_result: RunResult,
    ) -> GateRegistrationResult:
        return GateRegistrationResult(
            accepted=False,
            code="gate-unavailable",
            reason="%s: %s" % (self.module_name, self.detail),
        )


class ModuleDispatchGate(DispatchGate):
    """Thin dynamic wrapper for the U5 dispatch_gate module."""

    def __init__(self, module: Any, ledger_path: str = "~/.mogui/dispatch-ledger.jsonl"):
        self.module = module
        self.ledger_path = os.path.expanduser(ledger_path)

    def check(self, request: DispatchRequest) -> GateCheckResult:
        gate = self._build_gate()
        raw = gate.check(self._build_request(request))
        return _coerce_gate_check(raw)

    def register_probe(
        self,
        request: DispatchRequest,
        job_id: str,
        probe_cmd: Sequence[str],
        probe_result: RunResult,
    ) -> GateRegistrationResult:
        gate = self._build_gate()
        register = getattr(gate, "register_job", None)
        if register is None:
            return GateRegistrationResult(False, "gate-register-missing", "U5 gate has no register_job method")

        def probe_fn(registered_job_id: str) -> bool:
            return registered_job_id == job_id and probe_result.exit_code == 0

        raw = register(
            job_id,
            probe_fn,
            contract_sha=_contract_sha(request.contract_path),
            runtime=request.runtime,
        )
        return _coerce_gate_registration(raw)

    def _build_gate(self) -> Any:
        config_cls = getattr(self.module, "DispatchGateConfig", None)
        gate_cls = getattr(self.module, "DispatchGate", None)
        if config_cls is None or gate_cls is None:
            raise RuntimeError("U5 dispatch_gate module lacks DispatchGateConfig or DispatchGate")
        return gate_cls(config_cls(ledger_path=self.ledger_path))

    def _build_request(self, request: DispatchRequest) -> Any:
        request_cls = getattr(self.module, "DispatchRequest", None)
        if request_cls is None:
            raise RuntimeError("U5 dispatch_gate module lacks DispatchRequest")
        return request_cls(
            runtime=request.runtime,
            contract_path=request.contract_path,
            est_input_chars=request.est_chars,
            n_agents=request.agents,
            purpose="adapter-dispatch",
        )


def default_runner(cmd: Sequence[str], cwd: Optional[str] = None) -> RunResult:
    try:
        completed = subprocess.run(
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return RunResult(exit_code=127, stderr=str(exc))
    return RunResult(completed.returncode, completed.stdout, completed.stderr)


def load_default_gate(
    module_name: str = "master_runtime.core.dispatch_gate",
    ledger_path: str = "~/.mogui/dispatch-ledger.jsonl",
) -> DispatchGate:
    try:
        return ModuleDispatchGate(importlib.import_module(module_name), ledger_path=ledger_path)
    except ModuleNotFoundError as exc:
        return MissingDispatchGate(module_name, str(exc))


def dispatch(
    request: DispatchRequest,
    profile: Optional[ToolProfile] = None,
    gate: Optional[DispatchGate] = None,
    runner: Optional[Runner] = None,
) -> DispatchOutcome:
    selected_profile = profile if profile is not None else CodexCompanionProfile()
    selected_gate = gate if gate is not None else load_default_gate(ledger_path=request.ledger_path)
    run = runner if runner is not None else default_runner

    isolation = _decide_isolation(request)
    empty_outcome = _base_outcome(isolation)

    gate_result = selected_gate.check(request)
    if not gate_result.allowed:
        return empty_outcome(
            ok=False,
            error_code=gate_result.code or "gate-denied",
            message=gate_result.reason or "dispatch gate denied request",
        )

    worktree_path = None
    worktree_cmd = None
    execution_cwd = request.repo_path
    if isolation.mode == IsolationMode.WORKTREE:
        worktree_path, worktree_cmd = build_worktree_plan(request.repo_path, request.contract_path, request.branch_anchor)
        execution_cwd = worktree_path

    worker_cmd = tuple(selected_profile.build_worker_cmd(request.contract_path, execution_cwd))

    if request.dry_run:
        return DispatchOutcome(
            ok=True,
            error_code=None,
            message="dry-run",
            job_id=None,
            worktree_path=worktree_path,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=worker_cmd,
            probe_cmd=None,
            worktree_cmd=worktree_cmd,
        )

    worker_result = run(worker_cmd, execution_cwd)
    if worker_result.exit_code != 0:
        return DispatchOutcome(
            ok=False,
            error_code="worker-failed",
            message=_result_detail(worker_result),
            job_id=None,
            worktree_path=worktree_path,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=worker_cmd,
            probe_cmd=None,
            worktree_cmd=worktree_cmd,
        )

    try:
        job_id = selected_profile.parse_job_id(worker_result.stdout)
    except ProfileError as exc:
        return DispatchOutcome(
            ok=False,
            error_code=str(exc) or "job-id-parse-failed",
            message="worker stdout did not contain a job id",
            job_id=None,
            worktree_path=worktree_path,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=worker_cmd,
            probe_cmd=None,
            worktree_cmd=worktree_cmd,
        )

    probe_cmd = tuple(selected_profile.build_probe_cmd(job_id, execution_cwd))
    probe_result = run(probe_cmd, execution_cwd)
    if probe_result.exit_code != 0:
        return DispatchOutcome(
            ok=False,
            error_code="probe-failed",
            message=_result_detail(probe_result),
            job_id=job_id,
            worktree_path=worktree_path,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=worker_cmd,
            probe_cmd=probe_cmd,
            worktree_cmd=worktree_cmd,
        )

    register_result = selected_gate.register_probe(request, job_id, probe_cmd, probe_result)
    if not register_result.accepted:
        return DispatchOutcome(
            ok=False,
            error_code=register_result.code or "register-denied",
            message=register_result.reason or "gate refused probe registration",
            job_id=job_id,
            worktree_path=worktree_path,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=worker_cmd,
            probe_cmd=probe_cmd,
            worktree_cmd=worktree_cmd,
        )

    return DispatchOutcome(
        ok=True,
        error_code=None,
        message="dispatched",
        job_id=job_id,
        worktree_path=worktree_path,
        ledger_reflected=True,
        isolation=isolation,
        worker_cmd=worker_cmd,
        probe_cmd=probe_cmd,
        worktree_cmd=worktree_cmd,
    )


def build_worktree_plan(repo_path: str, contract_path: str, branch_anchor: Optional[str] = None) -> Tuple[str, Tuple[str, ...]]:
    slug = _slug(os.path.splitext(os.path.basename(contract_path))[0] or "contract")
    worktree_path = os.path.join(repo_path, ".worktrees", "adapter-%s" % slug)
    cmd = ["git", "-C", repo_path, "worktree", "add", worktree_path]
    if branch_anchor:
        cmd.append(branch_anchor)
    return worktree_path, tuple(cmd)


def _decide_isolation(request: DispatchRequest) -> IsolationDecision:
    if request.isolation == "shared":
        return IsolationDecision(mode=IsolationMode.SHARED, reasons=("forced_shared",))
    if request.isolation == "worktree":
        return IsolationDecision(mode=IsolationMode.WORKTREE, reasons=("forced_worktree",))
    if request.isolation != "auto":
        return IsolationDecision(mode=IsolationMode.SHARED, reasons=("invalid_isolation",))
    return needs_worktree(
        parallel_writes=request.agents > 1,
        branch_anchor=request.branch_anchor,
        tree_contention=request.tree_contention,
        branch_switch=request.branch_switch,
    )


def _base_outcome(isolation: IsolationDecision) -> Callable[..., DispatchOutcome]:
    def make(
        ok: bool,
        error_code: Optional[str],
        message: str,
    ) -> DispatchOutcome:
        return DispatchOutcome(
            ok=ok,
            error_code=error_code,
            message=message,
            job_id=None,
            worktree_path=None,
            ledger_reflected=False,
            isolation=isolation,
            worker_cmd=None,
            probe_cmd=None,
            worktree_cmd=None,
        )

    return make


def _first_attr(module: Any, names: Sequence[str]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    return None


def _coerce_gate_check(raw: Any) -> GateCheckResult:
    if isinstance(raw, GateCheckResult):
        return raw
    if isinstance(raw, bool):
        return GateCheckResult(raw, "ok" if raw else "gate-denied", "")
    if isinstance(raw, dict):
        allowed = bool(raw.get("allowed", raw.get("ok", False)))
        return GateCheckResult(
            allowed=allowed,
            code=str(raw.get("code") or ("ok" if allowed else "gate-denied")),
            reason=str(raw.get("reason") or raw.get("message") or ""),
        )
    allowed = bool(getattr(raw, "allow", getattr(raw, "allowed", getattr(raw, "ok", False))))
    return GateCheckResult(
        allowed=allowed,
        code=_reason_code(getattr(raw, "reason", getattr(raw, "code", "ok" if allowed else "gate-denied"))),
        reason=str(getattr(raw, "message", "")),
    )


def _coerce_gate_registration(raw: Any) -> GateRegistrationResult:
    if isinstance(raw, GateRegistrationResult):
        return raw
    if isinstance(raw, bool):
        return GateRegistrationResult(raw, "registered" if raw else "register-denied", "")
    if isinstance(raw, dict):
        accepted = bool(raw.get("accepted", raw.get("ok", False)))
        return GateRegistrationResult(
            accepted=accepted,
            code=str(raw.get("code") or ("registered" if accepted else "register-denied")),
            reason=str(raw.get("reason") or raw.get("message") or ""),
        )
    accepted = bool(getattr(raw, "allow", getattr(raw, "accepted", getattr(raw, "ok", False))))
    return GateRegistrationResult(
        accepted=accepted,
        code=_reason_code(getattr(raw, "reason", getattr(raw, "code", "registered" if accepted else "register-denied"))),
        reason=str(getattr(raw, "message", "")),
    )


def _result_detail(result: RunResult) -> str:
    return result.stderr.strip() or result.stdout.strip() or "command failed with exit %s" % result.exit_code


def _slug(value: str) -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9_.-]+", "-", lowered).strip("-")
    return slug or "contract"


def _reason_code(value: Any) -> str:
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return str(value)


def _contract_sha(contract_path: str) -> str:
    with open(contract_path, "rb") as contract:
        return hashlib.sha256(contract.read()).hexdigest()
