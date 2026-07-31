import hashlib
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.adapter.dispatch import (
    DispatchGate,
    DispatchRequest,
    GateCheckResult,
    GateRegistrationResult,
    ModuleDispatchGate,
    dispatch,
)
from master_runtime.core.adapter.doctor import DEFAULT_CHECKS, ProbeCheck, RunResult, doctor
from master_runtime.core.adapter.isolation import IsolationMode, needs_worktree
from master_runtime.core.adapter.profile import ToolProfile


class FakeProfile(ToolProfile):
    def build_worker_cmd(self, contract_path, cwd):
        return ["worker", contract_path, cwd]

    def build_probe_cmd(self, job_id, cwd):
        return ["probe", job_id, cwd]

    def parse_job_id(self, stdout):
        if "job-1" in stdout:
            return "job-1"
        raise AssertionError("unexpected stdout: %s" % stdout)


class FakeGate(DispatchGate):
    def __init__(self, allowed=True, register_accepted=True):
        self.allowed = allowed
        self.register_accepted = register_accepted
        self.check_calls = []
        self.register_calls = []

    def check(self, request):
        self.check_calls.append(request)
        if self.allowed:
            return GateCheckResult(True)
        return GateCheckResult(False, "gate-denied", "blocked")

    def register_probe(self, request, job_id, probe_cmd, probe_result):
        self.register_calls.append((request, job_id, tuple(probe_cmd), probe_result))
        if self.register_accepted:
            return GateRegistrationResult(True)
        return GateRegistrationResult(False, "register-denied", "refused")


class RecordingRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, cwd=None):
        self.calls.append((tuple(cmd), cwd))
        if not self.results:
            raise AssertionError("unexpected command: %s" % (cmd,))
        return self.results.pop(0)


class FakeReason:
    def __init__(self, value):
        self.value = value


class FakeU5Decision:
    def __init__(self, allow, reason):
        self.allow = allow
        self.reason = FakeReason(reason)


class FakeU5Module:
    class DispatchRequest:
        def __init__(self, runtime, contract_path, est_input_chars, n_agents, purpose=""):
            self.runtime = runtime
            self.contract_path = contract_path
            self.est_input_chars = est_input_chars
            self.n_agents = n_agents
            self.purpose = purpose

    class DispatchGateConfig:
        def __init__(self, ledger_path):
            self.ledger_path = ledger_path

    class DispatchGate:
        configs = []
        check_requests = []
        register_calls = []

        def __init__(self, config):
            self.config = config
            self.__class__.configs.append(config)

        def check(self, request):
            self.__class__.check_requests.append(request)
            return FakeU5Decision(True, "OK")

        def register_job(self, job_id, probe_fn, contract_sha=None, runtime=None):
            self.__class__.register_calls.append(
                (job_id, probe_fn(job_id), contract_sha, runtime)
            )
            return FakeU5Decision(True, "OK")


class AdapterTests(unittest.TestCase):
    def test_gate_deny_stops_before_worker(self):
        gate = FakeGate(allowed=False)
        runner = RecordingRunner([])

        outcome = dispatch(
            DispatchRequest(contract_path="/tmp/contract.md", repo_path="/repo"),
            profile=FakeProfile(),
            gate=gate,
            runner=runner,
        )

        self.assertFalse(outcome.ok)
        self.assertEqual("gate-denied", outcome.error_code)
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(gate.check_calls))
        self.assertEqual([], gate.register_calls)

    def test_isolation_condition_table(self):
        shared = needs_worktree(False, None, False, False)
        self.assertEqual(IsolationMode.SHARED, shared.mode)
        self.assertEqual((), shared.reasons)

        cases = [
            (True, None, False, False, "parallel_writes"),
            (False, "main", False, False, "branch_anchor"),
            (False, None, True, False, "tree_contention"),
            (False, None, False, True, "branch_switch"),
        ]
        for parallel_writes, branch_anchor, tree_contention, branch_switch, reason in cases:
            decision = needs_worktree(parallel_writes, branch_anchor, tree_contention, branch_switch)
            self.assertEqual(IsolationMode.WORKTREE, decision.mode)
            self.assertIn(reason, decision.reasons)

    def test_doctor_reports_missing_without_failing(self):
        checks = [
            ProbeCheck(name="git", probe_cmd=("git", "--version")),
            ProbeCheck(name="companion", path="/missing/companion.mjs"),
        ]

        def fake_runner(cmd, cwd=None):
            return RunResult(exit_code=127, stderr="missing executable")

        report = doctor(checks=checks, runner=fake_runner, path_exists=lambda path: False)

        self.assertEqual(("git", "companion"), report.missing_names)
        self.assertEqual(2, len(report.results))
        self.assertFalse(report.results[0].present)
        self.assertFalse(report.results[1].present)

    def test_doctor_uses_real_codex_companion_default_path(self):
        companion = [check for check in DEFAULT_CHECKS if check.name == "codex_companion_mjs"][0]
        self.assertEqual("~/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/codex-companion.mjs", companion.path)

    def test_module_dispatch_gate_adapts_u5_class_api(self):
        FakeU5Module.DispatchGate.configs = []
        FakeU5Module.DispatchGate.check_requests = []
        FakeU5Module.DispatchGate.register_calls = []
        gate = ModuleDispatchGate(FakeU5Module, ledger_path="/tmp/ledger.jsonl")
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "contract.md"
            contract.write_text("adapter contract", encoding="utf-8")
            request = DispatchRequest(
                contract_path=str(contract),
                repo_path="/repo",
                runtime="codex",
                agents=3,
                est_chars=42,
            )

            check = gate.check(request)
            registration = gate.register_probe(request, "job-1", ["probe", "job-1"], RunResult(exit_code=0))

        self.assertTrue(check.allowed)
        self.assertEqual("OK", check.code)
        self.assertTrue(registration.accepted)
        self.assertEqual("OK", registration.code)
        self.assertEqual("/tmp/ledger.jsonl", FakeU5Module.DispatchGate.configs[0].ledger_path)
        u5_request = FakeU5Module.DispatchGate.check_requests[0]
        self.assertEqual("codex", u5_request.runtime)
        self.assertEqual(str(contract), u5_request.contract_path)
        self.assertEqual(42, u5_request.est_input_chars)
        self.assertEqual(3, u5_request.n_agents)
        self.assertEqual("adapter-dispatch", u5_request.purpose)
        self.assertEqual(
            [
                (
                    "job-1",
                    True,
                    hashlib.sha256(b"adapter contract").hexdigest(),
                    "codex",
                )
            ],
            FakeU5Module.DispatchGate.register_calls,
        )

    def test_probe_failure_prevents_gate_registration(self):
        gate = FakeGate()
        runner = RecordingRunner(
            [
                RunResult(exit_code=0, stdout='{"job_id":"job-1"}'),
                RunResult(exit_code=2, stderr="probe failed"),
            ]
        )

        outcome = dispatch(
            DispatchRequest(contract_path="/tmp/contract.md", repo_path="/repo"),
            profile=FakeProfile(),
            gate=gate,
            runner=runner,
        )

        self.assertFalse(outcome.ok)
        self.assertEqual("probe-failed", outcome.error_code)
        self.assertEqual("job-1", outcome.job_id)
        self.assertFalse(outcome.ledger_reflected)
        self.assertEqual([], gate.register_calls)
        self.assertEqual(2, len(runner.calls))

    def test_dry_run_returns_decision_and_commands_without_execution(self):
        gate = FakeGate()
        runner = RecordingRunner([])

        outcome = dispatch(
            DispatchRequest(
                contract_path="/tmp/contract.md",
                repo_path="/repo",
                agents=2,
                dry_run=True,
            ),
            profile=FakeProfile(),
            gate=gate,
            runner=runner,
        )

        self.assertTrue(outcome.ok)
        self.assertEqual("dry-run", outcome.message)
        self.assertIsNone(outcome.job_id)
        self.assertFalse(outcome.ledger_reflected)
        self.assertEqual(IsolationMode.WORKTREE, outcome.isolation.mode)
        self.assertIn("parallel_writes", outcome.isolation.reasons)
        self.assertEqual(("git", "-C", "/repo", "worktree", "add", "/repo/.worktrees/adapter-contract"), outcome.worktree_cmd)
        self.assertEqual(("worker", "/tmp/contract.md", "/repo/.worktrees/adapter-contract"), outcome.worker_cmd)
        self.assertEqual([], runner.calls)
        self.assertEqual([], gate.register_calls)


if __name__ == "__main__":
    unittest.main()
