import copy
import json
import unittest
from pathlib import Path

from scripts.configuration import DEFAULT_CONFIG
from scripts.prepare_agents import choose_roles, make_files
from scripts.route_task import DOMAINS, route, required_checks, validate_task

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

    def test_ode_domain_routes_model_and_numerical_specialists_without_claim_escalation(self):
        task = copy.deepcopy(self.task)
        task.update(kind="build", domains=["ode"], interfaces=["cli"],
                    targets=["linux"], risk="R1")

        self.assertIn("ode", DOMAINS)
        plan = route(task)
        roles = plan["implementation_or_domain_roles"]
        self.assertIn("implementation_engineer", roles)
        self.assertIn("ode_model_specialist", roles)
        self.assertIn("numerical_analyst", roles)
        self.assertNotIn("mathematical_model_specialist", roles)
        self.assertEqual(plan["scientific_bridge"], "CONDITIONAL_ON_CLAIMS")
        self.assertNotIn("scientific_validation", plan["required_evidence"])
        self.assertNotIn("independent_review", plan["required_evidence"])
        prepared_roles, _, _ = choose_roles(task, DEFAULT_CONFIG)
        self.assertIn("ode_model_specialist", prepared_roles)
        manifest, files = make_files(task, "codex", dict(DEFAULT_CONFIG, provider_mode="codex"))
        assignment = next(item for item in manifest["assignments"]
                          if item["role"] == "ode_model_specialist")
        self.assertIn("ssec-ode-model-specialist", files[assignment["profile"]])
        self.assertIn("Formular estados, parámetros", files[assignment["packet"]])
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ode_model_specialist", skill)

    def test_check_specs_are_validated_as_part_of_task_validation(self):
        task = copy.deepcopy(self.task)
        task["check_specs"] = [
            {"check_id": "unit_tests", "argv": ["python", "-P", "-m", "unittest"], "cwd": ".",
             "timeout_seconds": 30, "protocol": "unittest"},
        ]
        validate_task(task)
        plan = route(task)
        self.assertIn("unit_tests", plan["required_evidence"])

        task["check_specs"][0]["cwd"] = "../outside"
        with self.assertRaises(ValueError):
            validate_task(task)

    def test_required_checks_also_rejects_invalid_check_specs(self):
        task = copy.deepcopy(self.task)
        task["check_specs"] = [{
            "check_id": "unit_tests", "argv": ["python", "-m", "unittest"],
            "cwd": ".", "timeout_seconds": 30, "protocol": "exit_code",
        }]
        with self.assertRaises(ValueError):
            required_checks(task)
