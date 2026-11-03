import copy
import json
import unittest
from pathlib import Path

from scripts.route_task import route, required_checks, validate_task

ROOT = Path(__file__).resolve().parents[1]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))

    def test_seir_routing_preserves_audit_mode(self):
        plan = route(self.task)
        self.assertEqual(plan["next_action"], "READ_ONLY_INVENTORY")
        self.assertNotIn("implementation_engineer", plan["implementation_or_domain_roles"])
        self.assertIn("mathematical_model_specialist", plan["implementation_or_domain_roles"])
        self.assertIn("numerical_analyst", plan["implementation_or_domain_roles"])
        self.assertEqual(plan["runtime_mode"], "SINGLE_CONTEXT_SEQUENTIAL")
        self.assertEqual(plan["scientific_bridge"], "REQUIRES_EXTERNAL_SCIENTIFIC_REVIEW")
        self.assertIn("cross_platform", plan["required_evidence"])

    def test_idl_must_have_licensed_integration_evidence(self):
        task = json.loads((ROOT / "examples/ml_idl_build.json").read_text(encoding="utf-8"))
        plan = route(task)
        self.assertIn("idl_engineer", plan["implementation_or_domain_roles"])
        self.assertIn("idl_integration", required_checks(task))
        self.assertEqual(plan["runtime_mode"], "MULTI_CONTEXT_ELIGIBLE_NOT_STARTED")

    def test_reject_bad_domain(self):
        task = copy.deepcopy(self.task)
        task["domains"] = ["made_up"]
        with self.assertRaises(ValueError):
            validate_task(task)

    def test_low_risk_no_unneeded_review(self):
        task = copy.deepcopy(self.task)
        task.update(kind="build", domains=["general"], interfaces=["cli"],
                    targets=["linux"], risk="R1")
        plan = route(task)
        self.assertNotIn("scientific_validation", plan["required_evidence"])
        self.assertNotIn("independent_reviewer", plan["review_roles"])
        self.assertIn("implementation_engineer", plan["implementation_or_domain_roles"])

    def test_check_specs_are_validated_as_part_of_task_validation(self):
        task = copy.deepcopy(self.task)
        task["check_specs"] = [
            {"check_id": "unit_tests", "argv": ["python", "-m", "unittest"], "cwd": ".",
             "timeout_seconds": 30, "protocol": "unittest"},
        ]
        validate_task(task)
        plan = route(task)
        self.assertIn("unit_tests", plan["required_evidence"])

        task["check_specs"][0]["cwd"] = "../outside"
        with self.assertRaises(ValueError):
            validate_task(task)
