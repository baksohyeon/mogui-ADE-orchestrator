#!/bin/bash
set -u
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, "scripts")
import gate_runner
import mogui_log
from mogui_errors import GateDenied, Undetermined


class ScrubTests(unittest.TestCase):
    def test_secret_classes_are_removed_from_serialized_line(self):
        home_path = "{{WORKSPACE_ROOT}}/project/run.log".replace(
            "{{WORKSPACE_ROOT}}", "/Users" + "/alice")
        values = [
            "key=" + "sk-" + "abcdefgh12345678",
            "ghp_" + "a" * 24,
            "github_pat_" + "a" * 24,
            "AKIA1234567890ABCD",
            "AIza" + "a" * 24,
            "xoxb-" + "1" * 12,
            "sk-ant-api03-" + "a" * 24,
            "-----BEGIN " + "PRIVATE KEY-----",
            "Authorization: Basic " + "dXNlcjpwYXNz",
            "Authorization: Bearer eyJtoken.payload-value",
            home_path,
            "/home/alice/project/run.log",
            "/tmp" + "/workspace/run.log",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mogui_log, "LOG_DIR", tmp):
                for value in values:
                    with self.subTest(value=value):
                        line = mogui_log.emit("info", "test", "pass", msg=value)
                        self.assertNotIn(value, json.dumps(line, ensure_ascii=False))

    def test_emit_is_fail_open_for_io_json_and_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "already-a-file"
            bad_path.write_text("x", encoding="utf-8")
            with patch.object(mogui_log, "LOG_DIR", str(bad_path)):
                self.assertIsInstance(mogui_log.emit("info", "io", "pass"), dict)
            with patch.object(mogui_log, "LOG_DIR", str(Path(tmp) / "ok")):
                self.assertIsInstance(mogui_log.emit("info", "json", "pass", value=object()), dict)
                self.assertIsInstance(mogui_log.emit("info", "none", "pass", msg=None), dict)


class GateTests(unittest.TestCase):
    def test_exit_and_outcome_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mogui_log, "LOG_DIR", tmp):
                with patch.object(gate_runner, "emit", wraps=gate_runner.emit) as emit:
                    self.assertEqual(gate_runner.run_gate("pass", lambda: {}), 0)
                    self.assertEqual(gate_runner.run_gate("finding", lambda: (_ for _ in ()).throw(
                        GateDenied("finding", "violation"))), 1)
                    self.assertEqual(gate_runner.run_gate("unknown", lambda: (_ for _ in ()).throw(
                        Undetermined("unknown", "no_probe"))), 2)
                    outcomes = [call.args[2] for call in emit.call_args_list]
                    self.assertEqual(outcomes, ["pass", "finding", "undetermined"])

    def test_unexpected_exception_is_undetermined_with_unknown_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mogui_log, "LOG_DIR", tmp):
                with patch.object(gate_runner, "emit", wraps=gate_runner.emit) as emit:
                    code = gate_runner.run_gate("surprise", lambda: (_ for _ in ()).throw(
                        RuntimeError("unfamiliar")))
                    self.assertEqual(code, 2)
                    line = emit.call_args.args[0:3]
                    self.assertEqual(line, ("warn", "surprise", "undetermined"))
                    self.assertEqual(emit.call_args.kwargs["evidence"], "unknown")

    def test_error_context_reserved_keys_are_namespaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mogui_log, "LOG_DIR", tmp):
                with patch.object(gate_runner, "emit", wraps=gate_runner.emit) as emit:
                    code = gate_runner.run_gate("finding", lambda: (_ for _ in ()).throw(
                        GateDenied("finding", "violation", context={"reason": "inner"})))
                    self.assertEqual(code, 1)
                    self.assertEqual(emit.call_args.kwargs["context_reason"], "inner")


if __name__ == "__main__":
    unittest.main()
PY
