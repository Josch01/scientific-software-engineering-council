"""Role-owned contract validation; no provider or integration acceptance claims."""
from dataclasses import FrozenInstanceError
import unittest

from scripts.work_items import WorkItem, validate_work_items


def work_item(role="implementation_engineer", **changes):
    item = dict(id=role + "-work", role=role, reason="Implement declared changes", risk="R1",
                inputs=["README.md"], outputs=[role + "/result.py"], dependencies=[],
                file_ownership=[role + "/"], tests=["unit_tests"],
                required_reviewers=["software_auditor"], acceptance_criteria=["Checks pass"])
    item.update(changes)
    return item


class WorkItemTests(unittest.TestCase):
    def validate(self, items, roles=("implementation_engineer",)):
        return validate_work_items({"work_items": items}, roles, ["software_auditor"], ["unit_tests"])

    def test_valid_contract_is_frozen_and_detached_from_packet(self):
        item = work_item()
        result = self.validate([item])
        contract = result["implementation_engineer"]
        self.assertIsInstance(contract, WorkItem)
        self.assertEqual(contract.outputs, ("implementation_engineer/result.py",))
        item["outputs"].append("elsewhere.py")
        self.assertEqual(contract.outputs, ("implementation_engineer/result.py",))
        with self.assertRaises(FrozenInstanceError):
            contract.role = "invented"

    def test_roles_must_match_router_exactly(self):
        for items in ([], [work_item("invented")], [work_item(), work_item("other")],
                      [work_item(), work_item(id="second")]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.validate(items)

    def test_ids_are_unique_and_portable(self):
        for bad_id in ("../escape", "", "a b", 3):
            with self.subTest(id=bad_id), self.assertRaises(ValueError):
                self.validate([work_item(id=bad_id)])
        with self.assertRaises(ValueError):
            self.validate([work_item(id="same"), work_item("other", id="same")],
                          ("implementation_engineer", "other"))

    def test_exact_fields_and_json_types(self):
        for field in work_item():
            missing = work_item()
            del missing[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.validate([missing])
            with self.subTest(null=field), self.assertRaises(ValueError):
                item = work_item()
                item[field] = None
                self.validate([item])
        for changes in ({"extra": "no"}, {"risk": "R9"}, {"reason": " "},
                        {"inputs": "README.md"}, {"tests": ("unit_tests",)},
                        {"outputs": []}, {"file_ownership": []}, {"acceptance_criteria": []},
                        {"acceptance_criteria": [True]}, {"reason": "bad\x00text"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.validate([work_item(**changes)])
        for items in (None, {}, "bad", [None]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.validate(items)

    def test_reviewers_and_checks_reference_declared_requirements(self):
        for changes in ({"tests": ["unknown"]}, {"tests": []},
                        {"tests": ["unit_tests", "unit_tests"]},
                        {"required_reviewers": []}, {"required_reviewers": ["invented"]},
                        {"required_reviewers": ["software_auditor", "software_auditor"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.validate([work_item(**changes)])

    def test_all_path_fields_reject_unsafe_or_ambiguous_paths(self):
        bad_paths = ["/root", "C:/root", "C:relative", "a/C:drive", "../escape", "a/../b",
                     "./a", "a/./b", "a//b", "", "a\x00b", "a\\b", "*.py", "a?", "a[bc]",
                     "a.", "a ", "NUL", "CON.txt", "a:stream", ".git/config"]
        for field in ("inputs", "outputs", "file_ownership"):
            for path in bad_paths:
                with self.subTest(field=field, path=path), self.assertRaises(ValueError):
                    self.validate([work_item(**{field: [path]})])

    def test_windows_superscript_device_components_are_rejected_in_all_path_fields(self):
        for field in ("inputs", "outputs", "file_ownership"):
            for prefix in ("COM", "LPT"):
                for digit in ("\u00b9", "\u00b2", "\u00b3"):
                    for path in (prefix + digit, prefix + digit + ".txt",
                                 "src/" + prefix.lower() + digit + "/result.py"):
                        item = work_item(**{field: [path]})
                        # Keep ownership valid so the rejection must concern the path.
                        if field == "outputs":
                            item["file_ownership"] = [path]
                        elif field == "file_ownership":
                            item["outputs"] = [path]
                        with self.subTest(field=field, path=path), self.assertRaises(ValueError):
                            self.validate([item])

    def test_outputs_must_be_covered_by_ownership_with_directory_boundary(self):
        for output in ("elsewhere.py", "implementation_engineer2/x.py", "implementation_engineer"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.validate([work_item(outputs=[output])])
        result = self.validate([work_item(outputs=["src/x.py"], file_ownership=["src/x.py"])])
        self.assertEqual(result["implementation_engineer"].file_ownership, ("src/x.py",))
        with self.assertRaises(ValueError):
            self.validate([work_item(outputs=["src/"], file_ownership=["src/x.py"])])

    def test_cross_role_scopes_cannot_collide_including_case_and_ancestors(self):
        for first, second in (("src/", "src/x.py"), ("src/x.py", "src/"),
                              ("src", "src/x.py"), ("SRC/x.py", "src/X.py"),
                              ("src/", "SRC/"), ("src/x.py", "src/x.py")):
            with self.subTest(first=first, second=second), self.assertRaises(ValueError):
                self.validate([work_item(outputs=[first], file_ownership=[first]),
                               work_item("other", outputs=[second], file_ownership=[second])],
                              ("implementation_engineer", "other"))
        self.validate([work_item(outputs=["src/a"], file_ownership=["src/a"]),
                       work_item("other", outputs=["src/ab"], file_ownership=["src/ab"])],
                      ("implementation_engineer", "other"))

    def test_dependencies_fail_closed_until_scheduler_exists(self):
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.validate([work_item(dependencies=["other-work"])])

    def test_no_check_specs_allows_empty_test_references_only(self):
        result = validate_work_items({"work_items": [work_item(tests=[])]},
                                     ["implementation_engineer"], ["software_auditor"], [])
        self.assertEqual(result["implementation_engineer"].tests, ())
        with self.assertRaises(ValueError):
            validate_work_items({"work_items": [work_item()]},
                                ["implementation_engineer"], ["software_auditor"], [])

    def test_missing_work_items_is_not_an_integration_contract(self):
        with self.assertRaisesRegex(ValueError, "work_items"):
            validate_work_items({}, ["implementation_engineer"], ["software_auditor"], ["unit_tests"])
