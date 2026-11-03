import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


def load_workspace_contract(test_case):
    spec = importlib.util.find_spec("scripts.scientific_workspace")
    test_case.assertIsNotNone(
        spec, "scripts.scientific_workspace must provide the workspace contract"
    )
    return importlib.import_module("scripts.scientific_workspace")


class ScientificWorkspaceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_workspace_contract(self)

    def minimal_manifest(self):
        return {
            "schema_version": 1,
            "model": {
                "id": "sir-demo",
                "title": "Generic compartment model",
                "summary": "A descriptive workspace fixture.",
            },
            "artifacts": [
                {"id": "definition", "kind": "model_definition", "path": "model.json"},
                {"id": "simulation", "kind": "simulation_result", "path": "results/run.json"},
                {"id": "audit", "kind": "audit_report", "path": "reports/audit.json"},
            ],
            "pages": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "components": [
                        {
                            "id": "equations",
                            "kind": "equations",
                            "title": "Model definition",
                            "artifact_ids": ["definition"],
                        },
                        {
                            "id": "simulation-view",
                            "kind": "simulation_plot",
                            "title": "Simulation",
                            "artifact_ids": ["simulation"],
                        },
                        {
                            "id": "audit",
                            "kind": "audit",
                            "title": "Audit",
                            "artifact_ids": ["audit"],
                        },
                    ],
                }
            ],
        }

    def test_valid_manifest_round_trips_as_stable_json_data(self):
        workspace = self.contract.validate_workspace(self.minimal_manifest())
        encoded = json.dumps(workspace.to_dict(), sort_keys=True, allow_nan=False)

        self.assertEqual(json.loads(encoded), self.minimal_manifest())
        self.assertEqual(workspace.schema_version, 1)

    def test_generic_example_is_a_valid_workspace_contract(self):
        example_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "scientific_workspace_minimal.json"
        )
        manifest = json.loads(example_path.read_text(encoding="utf-8"))

        workspace = self.contract.validate_workspace(manifest)

        self.assertEqual(workspace.to_dict(), manifest)

    def test_records_are_immutable_and_detached_from_input_mutation(self):
        manifest = self.minimal_manifest()
        workspace = self.contract.validate_workspace(manifest)
        manifest["model"]["title"] = "mutated"
        manifest["artifacts"].clear()

        self.assertEqual(workspace.model.title, "Generic compartment model")
        self.assertEqual(len(workspace.artifacts), 3)
        with self.assertRaises((AttributeError, TypeError)):
            workspace.model.title = "changed"

    def test_rejects_unknown_fields_and_unsupported_schema_version(self):
        manifest = self.minimal_manifest()
        manifest["executable"] = "print('unsafe')"
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.contract.validate_workspace(manifest)

        for version in (2, 1.0, True):
            manifest = self.minimal_manifest()
            manifest["schema_version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(
                ValueError, "schema_version"
            ):
                self.contract.validate_workspace(manifest)

    def test_rejects_unknown_component_kind_and_bad_component_binding(self):
        manifest = self.minimal_manifest()
        manifest["pages"][0]["components"][0]["kind"] = "custom_python"
        with self.assertRaisesRegex(ValueError, "component kind"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["pages"][0]["components"][0]["artifact_ids"] = ["simulation"]
        with self.assertRaisesRegex(ValueError, "incompatible"):
            self.contract.validate_workspace(manifest)

    def test_rejects_duplicate_artifact_ids_and_unsupported_artifact_kinds(self):
        manifest = self.minimal_manifest()
        manifest["artifacts"][1]["id"] = "definition"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["artifacts"][0]["kind"] = "executable_plugin"
        with self.assertRaisesRegex(ValueError, "artifact kind"):
            self.contract.validate_workspace(manifest)

    def test_rejects_undeclared_and_duplicate_references(self):
        manifest = self.minimal_manifest()
        manifest["pages"][0]["components"][0]["artifact_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "undeclared"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["pages"][0]["components"][0]["artifact_ids"] = [
            "definition",
            "definition",
        ]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.contract.validate_workspace(manifest)

    def test_rejects_duplicate_ids_and_casefolded_artifact_paths(self):
        manifest = self.minimal_manifest()
        manifest["pages"][0]["components"][1]["id"] = "equations"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["artifacts"][1]["path"] = "MODEL.JSON"
        with self.assertRaisesRegex(ValueError, "duplicate.*path|path.*duplicate"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["artifacts"][1]["path"] = "ｍodel.json"
        with self.assertRaisesRegex(ValueError, "duplicate.*path|path.*duplicate"):
            self.contract.validate_workspace(manifest)

    def test_rejects_windows_ads_drive_and_invalid_path_syntax(self):
        invalid_paths = (
            "data.csv:payload",
            "C:/data.csv",
            "folder\\data.csv",
            "/rooted/data.csv",
            "folder//data.csv",
            "folder/./data.csv",
            "folder/../data.csv",
            "folder/<data>.csv",
            "folder/name?.csv",
            "folder/name*.csv",
            "folder/name|stream.csv",
            "folder/name\".csv",
            "folder/name\x1f.csv",
            "scripts/SCIENT~2.PY",
            "folder/file.csv.",
            "folder/file.csv ",
            "folder./file.csv",
            "folder /file.csv",
            "folder/ file.csv",
        )
        for invalid_path in invalid_paths:
            with self.subTest(path=invalid_path):
                manifest = self.minimal_manifest()
                manifest["artifacts"][0]["path"] = invalid_path
                with self.assertRaisesRegex(ValueError, "path"):
                    self.contract.validate_workspace(manifest)

    def test_rejects_reserved_windows_device_names_with_extensions(self):
        reserved = (
            "CON",
            "prn.txt",
            "Aux.tar.gz",
            "nul.json",
            "COM1.csv",
            "com9",
            "LPT1.txt",
            "lpt9.data",
            "CON .txt",
            "COM¹.csv",
            "com²",
            "LPT³.txt",
        )
        for basename in reserved:
            with self.subTest(path=basename):
                manifest = self.minimal_manifest()
                manifest["artifacts"][0]["path"] = f"results/{basename}"
                with self.assertRaisesRegex(ValueError, "path"):
                    self.contract.validate_workspace(manifest)

    def test_enforces_collection_and_text_limits(self):
        manifest = self.minimal_manifest()
        manifest["model"]["title"] = "x" * 1001
        with self.assertRaisesRegex(ValueError, "title"):
            self.contract.validate_workspace(manifest)

        manifest = self.minimal_manifest()
        manifest["artifacts"] = [
            {"id": f"a{index}", "kind": "source_code", "path": f"src/f{index}.py"}
            for index in range(1001)
        ]
        with self.assertRaisesRegex(ValueError, "artifacts"):
            self.contract.validate_workspace(manifest)

    def test_rejects_non_mapping_and_non_json_contract_values(self):
        for value in (None, [], "manifest", {"schema_version": True}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.contract.validate_workspace(value)

        manifest = self.minimal_manifest()
        manifest["model"]["summary"] = float("nan")
        with self.assertRaisesRegex(ValueError, "summary"):
            self.contract.validate_workspace(manifest)

    def test_resolves_project_relative_artifact_path(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.contract.resolve_artifact_path(root, "results/run.json")

        self.assertEqual(path, Path(root).resolve() / "results" / "run.json")

    def test_resolver_requires_an_existing_directory_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            file_root = Path(temporary) / "project.txt"
            file_root.write_text("not a directory", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "project root"):
                self.contract.resolve_artifact_path(file_root, "child.json")

    def test_resolver_rejects_paths_outside_project_root(self):
        with tempfile.TemporaryDirectory() as root:
            for unsafe in ("../secret", "C:/secret", "reports/a.json:payload"):
                with self.subTest(path=unsafe):
                    with self.assertRaises(ValueError):
                        self.contract.resolve_artifact_path(root, unsafe)

    def test_resolver_rejects_symlink_escape_when_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "linked"
            try:
                os.symlink(outside, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows host does not grant symlink creation privilege")
                raise

            with self.assertRaises(ValueError):
                self.contract.resolve_artifact_path(root, "linked/result.json")


if __name__ == "__main__":
    unittest.main()
