import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.release_gate import evaluate
from scripts.route_task import required_checks

ROOT = Path(__file__).resolve().parents[1]


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))

    def test_missing_evidence_blocks(self):
        result = evaluate(self.task, {"task_id": self.task["task_id"], "checks": {}}, ROOT)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(result["issues"])

    def test_valid_hashes_and_claimed_contexts_do_not_establish_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            checks = {}
            for name in required_checks(self.task):
                content = f"{name}: simulated fixture, not a real run\n".encode("utf-8")
                path = root / f"{name}.log"
                path.write_bytes(content)
                checks[name] = {
                    "status": "PASS", "exit_code": 0, "command": "fixture-only",
                    "environment": "unit-test-fixture", "executed_at": "2026-11-02T00:00:00Z",
                    "log_path": path.name, "sha256": hashlib.sha256(content).hexdigest(),
                    "independence": "SAME_PROVIDER_SEPARATE_CONTEXT",
                    "producer_context_id": "worker-A", "reviewer_context_id": "reviewer-B"
                }
            ev = {"task_id": self.task["task_id"], "checks": checks,
                  "provenance_verified": True, "source": "coordinator"}
            result = evaluate(self.task, ev, root)
            self.assertEqual(result["gate_status"], "BLOCKED")
            self.assertFalse(result["provenance_verified"])
            self.assertTrue(any("provenance" in issue for issue in result["issues"]))
            self.assertFalse(any("SHA-256 mismatch" in issue for issue in result["issues"]))
            corrupted = copy.deepcopy(ev)
            corrupted["checks"]["unit_tests"]["sha256"] = "0" * 64
            self.assertIn("unit_tests: log SHA-256 mismatch",
                          evaluate(self.task, corrupted, root)["issues"])
            same_context = copy.deepcopy(ev)
            same_context["checks"]["independent_review"]["reviewer_context_id"] = "worker-A"
            self.assertIn("independent_review: no two distinct declared review contexts",
                          evaluate(self.task, same_context, root)["issues"])

    def test_path_traversal_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ev = {"task_id": self.task["task_id"], "checks": {
                "unit_tests": {"status": "PASS", "exit_code": 0, "command": "x",
                               "environment": "y", "executed_at": "2026-11-02T00:00:00Z",
                               "log_path": "../secret", "sha256": "abc"}
            }}
            result = evaluate(self.task, ev, root)
            self.assertEqual(result["gate_status"], "BLOCKED")
            self.assertIn("unit_tests: log does not exist inside evidence root",result["issues"])
