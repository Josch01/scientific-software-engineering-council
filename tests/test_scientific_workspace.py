import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import scientific_workspace


def valid_manifest():
    return {
        "schema_version": 1,
        "workspace_id": "model-study",
        "title": "Scientific model workspace",
        "description": "Model-agnostic workspace structure.",
        "resources": [
            {"id": "model", "kind": "model_spec", "path": "model/model.json"},
            {"id": "data", "kind": "observations", "path": "data/observations.json"},
            {"id": "simulation", "kind": "simulation_result", "path": "results/simulation.json"},
            {"id": "fit", "kind": "fit_result", "path": "results/fit.json"},
            {"id": "sensitivity", "kind": "sensitivity_result", "path": "results/sensitivity.json"},
            {"id": "uncertainty", "kind": "uncertainty_result", "path": "results/uncertainty.json"},
            {"id": "audit", "kind": "audit_report", "path": "results/audit.json"},
            {"id": "source", "kind": "source_code", "path": "src/model.py"},
            {"id": "raw", "kind": "generic", "path": "artifacts/raw.txt"},
        ],
        "sections": [
            {
                "id": "model-section",
                "title": "Model",
                "components": [
                    {"id": "equations", "type": "equation_view", "title": "Equations", "resource_refs": ["model"], "config": {}},
                    {"id": "parameters", "type": "parameter_table", "title": "Parameters", "resource_refs": ["model"], "config": {}},
                ],
            },
            {
                "id": "data-section",
                "title": "Data",
                "components": [
                    {"id": "observations", "type": "observation_table", "title": "Observations", "resource_refs": ["data"], "config": {}},
                ],
            },
            {
                "id": "results-section",
                "title": "Results",
                "components": [
                    {"id": "trajectory", "type": "simulation_plot", "title": "Simulation", "resource_refs": ["simulation"], "config": {"x_axis": "time", "series": ["state_1"]}},
                    {"id": "fit-view", "type": "fit_summary", "title": "Fit", "resource_refs": ["fit"], "config": {"parameter_names": ["rate"]}},
                    {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensitivity", "resource_refs": ["sensitivity"], "config": {"state_names": ["state_1"], "parameter_names": ["rate"]}},
                    {"id": "uncertainty-view", "type": "uncertainty_summary", "title": "Uncertainty", "resource_refs": ["uncertainty"], "config": {"quantities": ["state_1"]}},
                    {"id": "audit-view", "type": "audit_summary", "title": "Audit", "resource_refs": ["audit"], "config": {}},
                ],
            },
            {
                "id": "artifacts-section",
                "title": "Project files",
                "components": [
                    {"id": "code", "type": "code_view", "title": "Model code", "resource_refs": ["source"], "config": {"language": "python"}},
                    {"id": "files", "type": "artifact_browser", "title": "Artifacts", "resource_refs": ["source", "raw"], "config": {}},
                ],
            },
        ],
    }


class WorkspaceManifestTests(unittest.TestCase):
    def test_simulation_plot_context_ref_accepts_only_a_resolved_model_spec(self):
        manifest = valid_manifest()
        manifest["sections"][2]["components"][0]["config"]["context_refs"] = ["model"]

        scientific_workspace.validate_workspace_manifest(manifest)

        invalid = valid_manifest()
        invalid["sections"][2]["components"][0]["config"]["context_refs"] = ["data"]
        with self.assertRaisesRegex(ValueError, "simulation_plot context_refs only allow model_spec"):
            scientific_workspace.validate_workspace_manifest(invalid)

        unresolved = valid_manifest()
        unresolved["sections"][2]["components"][0]["config"]["context_refs"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown context resource reference"):
            scientific_workspace.validate_workspace_manifest(unresolved)

    def test_fit_and_sensitivity_context_refs_are_typed_unique_and_resolved(self):
        manifest = valid_manifest()
        manifest["sections"][2]["components"][1]["config"]["context_refs"] = [
            "model", "data",
        ]
        manifest["sections"][2]["components"][2]["config"]["context_refs"] = [
            "model",
        ]

        summary = scientific_workspace.validate_workspace_manifest(manifest)

        self.assertIn("fit_summary", summary.component_types)
        self.assertIn("sensitivity_plot", summary.component_types)

        cases = (
            (["missing"], "unknown context resource reference"),
            (["model", "model"], "context_refs must be unique"),
            (["fit"], "distinct from resource_refs"),
            (["raw"], "fit_summary context_refs only allow model_spec and observations"),
        )
        for refs, message in cases:
            with self.subTest(refs=refs):
                candidate = valid_manifest()
                candidate["sections"][2]["components"][1]["config"]["context_refs"] = refs
                with self.assertRaisesRegex(ValueError, message):
                    scientific_workspace.validate_workspace_manifest(candidate)

        multiple_models = valid_manifest()
        multiple_models["resources"].append(
            {"id": "model-2", "kind": "model_spec", "path": "model/second.json"}
        )
        multiple_models["sections"][2]["components"][1]["config"]["context_refs"] = [
            "model", "data", "model-2",
        ]
        with self.assertRaisesRegex(ValueError, "at most one model_spec and one observations"):
            scientific_workspace.validate_workspace_manifest(multiple_models)

        multiple_datasets = valid_manifest()
        multiple_datasets["resources"].append(
            {"id": "data-2", "kind": "observations", "path": "data/second.json"}
        )
        multiple_datasets["sections"][2]["components"][1]["config"]["context_refs"] = [
            "model", "data", "data-2",
        ]
        with self.assertRaisesRegex(ValueError, "at most one model_spec and one observations"):
            scientific_workspace.validate_workspace_manifest(multiple_datasets)

        sensitivity_with_observations = valid_manifest()
        sensitivity_with_observations["sections"][2]["components"][2]["config"][
            "context_refs"
        ] = ["data"]
        with self.assertRaisesRegex(ValueError, "sensitivity_plot context_refs only allow model_spec"):
            scientific_workspace.validate_workspace_manifest(sensitivity_with_observations)

        sensitivity_with_multiple_models = valid_manifest()
        sensitivity_with_multiple_models["resources"].append(
            {"id": "model-2", "kind": "model_spec", "path": "model/second.json"}
        )
        sensitivity_with_multiple_models["sections"][2]["components"][2]["config"][
            "context_refs"
        ] = ["model", "model-2"]
        with self.assertRaisesRegex(ValueError, "at most one model_spec"):
            scientific_workspace.validate_workspace_manifest(sensitivity_with_multiple_models)

    def test_generic_template_includes_observation_evaluation_and_residual_view(self):
        template_path = Path(__file__).resolve().parents[1] / "examples" / "scientific_workspace_template.json"
        template = json.loads(template_path.read_text(encoding="utf-8"))

        summary = scientific_workspace.validate_workspace_manifest(template)

        self.assertIn("residual_plot", summary.component_types)
        evaluation = next(item for item in template["resources"] if item["id"] == "evaluation")
        self.assertEqual(evaluation["kind"], "observation_evaluation")

    def test_residual_plot_accepts_observation_evaluation_resource(self):
        manifest = valid_manifest()
        manifest["resources"].append(
            {"id": "evaluation", "kind": "observation_evaluation", "path": "results/evaluation.json"}
        )
        manifest["sections"][1]["components"].append(
            {"id": "residuals", "type": "residual_plot", "title": "Residuals",
             "resource_refs": ["evaluation"], "config": {}}
        )

        summary = scientific_workspace.validate_workspace_manifest(manifest)

        self.assertIn("residual_plot", summary.component_types)

    def test_residual_plot_rejects_other_kinds_and_config_fields(self):
        manifest = valid_manifest()
        manifest["sections"][1]["components"].append(
            {"id": "residuals", "type": "residual_plot", "title": "Residuals",
             "resource_refs": ["data"], "config": {}}
        )
        with self.assertRaisesRegex(ValueError, "requires resource kind"):
            scientific_workspace.validate_workspace_manifest(manifest)

        manifest["resources"].append(
            {"id": "evaluation", "kind": "observation_evaluation", "path": "results/evaluation.json"}
        )
        component = manifest["sections"][1]["components"][-1]
        component["resource_refs"] = ["evaluation"]
        component["config"] = {"html": "<script>"}
        with self.assertRaisesRegex(ValueError, "unknown or missing fields"):
            scientific_workspace.validate_workspace_manifest(manifest)

    def test_valid_model_agnostic_workspace_reports_ordered_summary(self):
        summary = scientific_workspace.validate_workspace_manifest(valid_manifest())

        self.assertEqual(summary.workspace_id, "model-study")
        self.assertEqual(summary.resource_count, 9)
        self.assertEqual(summary.section_count, 4)
        self.assertEqual(summary.component_count, 10)
        self.assertEqual(summary.component_types[0], "equation_view")
        self.assertEqual(summary.component_types[-1], "artifact_browser")
        self.assertEqual(summary.to_dict()["status"], "VALID")

    def test_unknown_fields_types_config_and_resource_roles_are_rejected(self):
        cases = []
        manifest = valid_manifest()
        manifest["unexpected"] = True
        cases.append((manifest, "unknown or missing fields"))
        manifest = valid_manifest()
        manifest["schema_version"] = True
        cases.append((manifest, "schema_version"))
        manifest = valid_manifest()
        manifest["sections"][0]["components"][0]["type"] = "custom_html"
        cases.append((manifest, "not a registered component type"))
        manifest = valid_manifest()
        manifest["sections"][0]["components"][0]["resource_refs"] = ["data"]
        cases.append((manifest, "requires resource kind"))
        manifest = valid_manifest()
        manifest["sections"][2]["components"][0]["config"]["script"] = "run()"
        cases.append((manifest, "unknown or missing fields"))
        manifest = valid_manifest()
        manifest["sections"][2]["components"][0]["resource_refs"] = ["missing"]
        cases.append((manifest, "unknown resource reference"))
        manifest = valid_manifest()
        manifest["sections"][0]["components"][1]["id"] = "equations"
        cases.append((manifest, "duplicate component id"))

        for manifest, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, message
            ):
                scientific_workspace.validate_workspace_manifest(manifest)

    def test_component_config_cardinality_and_values_are_checked(self):
        bad_configs = (
            ({"x_axis": "index", "series": ["state_1"]}, "x_axis"),
            ({"x_axis": "time", "series": []}, "series"),
            ({"x_axis": "time", "series": ["state_1", "state_1"]}, "unique"),
            ({"x_axis": "time", "series": ["state_1"], "html": "<b>"}, "unknown or missing fields"),
        )
        for config, message in bad_configs:
            manifest = valid_manifest()
            manifest["sections"][2]["components"][0]["config"] = config
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, message):
                scientific_workspace.validate_workspace_manifest(manifest)

    def test_ids_resources_sections_and_paths_are_unique(self):
        cases = []
        manifest = valid_manifest()
        manifest["resources"][1]["id"] = "model"
        cases.append((manifest, "duplicate resource id"))
        manifest = valid_manifest()
        manifest["sections"][1]["id"] = "model-section"
        cases.append((manifest, "duplicate section id"))
        manifest = valid_manifest()
        manifest["resources"][1]["path"] = "MODEL/MODEL.JSON"
        cases.append((manifest, "duplicate resource path"))
        manifest = valid_manifest()
        manifest["resources"][1]["path"] = "data/e\u0301.json"
        manifest["resources"][0]["path"] = "data/é.json"
        cases.append((manifest, "duplicate resource path"))

        for manifest, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, message
            ):
                scientific_workspace.validate_workspace_manifest(manifest)

    def test_portable_path_policy_rejects_windows_and_traversal_hazards(self):
        invalid_paths = (
            "/absolute/file.json",
            "C:/drive/file.json",
            "C:\\drive\\file.json",
            "\\\\server\\share\\file.json",
            "../outside.json",
            "inside/../outside.json",
            "inside//file.json",
            "inside/./file.json",
            "data.csv:stream",
            "NUL.txt",
            "folder/COM¹.csv",
            "DATOS~1.CSV",
            "DATA$~1.CSV",
            "DATA!~1.CSV",
            "trailing./file.json",
            "trailing /file.json",
            "bad?.json",
            "control\u001f.json",
        )
        for path in invalid_paths:
            manifest = valid_manifest()
            manifest["resources"][0]["path"] = path
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "path"):
                scientific_workspace.validate_workspace_manifest(manifest)

    def test_optional_resource_digest_requires_lowercase_sha256(self):
        manifest = valid_manifest()
        manifest["resources"][0]["sha256"] = "A" * 64

        with self.assertRaisesRegex(ValueError, "sha256"):
            scientific_workspace.validate_workspace_manifest(manifest)

    def test_resource_and_component_cardinality_boundaries_are_enforced(self):
        manifest = valid_manifest()
        with patch.object(scientific_workspace, "_MAX_RESOURCES", 9):
            scientific_workspace.validate_workspace_manifest(manifest)
        with patch.object(scientific_workspace, "_MAX_RESOURCES", 8):
            with self.assertRaisesRegex(ValueError, "resources must contain"):
                scientific_workspace.validate_workspace_manifest(manifest)

        with patch.object(scientific_workspace, "_MAX_COMPONENTS", 10):
            scientific_workspace.validate_workspace_manifest(manifest)
        with patch.object(scientific_workspace, "_MAX_COMPONENTS", 9):
            with self.assertRaisesRegex(ValueError, "component limit"):
                scientific_workspace.validate_workspace_manifest(manifest)


class WorkspaceCliTests(unittest.TestCase):
    def test_cli_validates_manifest_without_opening_referenced_resources(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = root / "workspace.json"
            manifest_path.write_text(json.dumps(valid_manifest()), encoding="utf-8")
            opened_paths = []
            real_open = Path.open

            def open_spy(path, *args, **kwargs):
                if Path(path) != manifest_path:
                    raise AssertionError(f"CLI attempted to open resource path: {path}")
                opened_paths.append(Path(path))
                return real_open(path, *args, **kwargs)

            real_stat = Path.stat
            real_resolve = Path.resolve

            def path_metadata_spy(method, path, *args, **kwargs):
                if Path(path) != manifest_path:
                    raise AssertionError(f"CLI attempted metadata access on resource path: {path}")
                return method(path, *args, **kwargs)

            with patch.object(Path, "open", open_spy), patch.object(
                Path, "stat", lambda path, *args, **kwargs: path_metadata_spy(real_stat, path, *args, **kwargs)
            ), patch.object(
                Path, "resolve", lambda path, *args, **kwargs: path_metadata_spy(real_resolve, path, *args, **kwargs)
            ), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = scientific_workspace.main([str(manifest_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(opened_paths, [manifest_path])
            completed = subprocess.run(
                [sys.executable, "scripts/scientific_workspace.py", str(manifest_path)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "VALID")

    def test_cli_duplicate_keys_invalid_utf8_nonfinite_and_deep_json_exit_two(self):
        invalid_documents = (
            b'{"schema_version":1,"schema_version":1}',
            b'{"schema_version":1,"nested":{"x":1,"x":2}}',
            b'{"schema_version":1,"x":1e400}',
            b'{"schema_version":NaN}',
            b"{" + b"[" * 40 + b"]" * 40 + b"}",
            b"\xff\xfe",
            json.dumps({**valid_manifest(), "schema_version": True}).encode("utf-8"),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, content in enumerate(invalid_documents):
                manifest_path = Path(temporary_directory) / f"invalid-{index}.json"
                manifest_path.write_bytes(content)
                completed = subprocess.run(
                    [sys.executable, "scripts/scientific_workspace.py", str(manifest_path)],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                with self.subTest(index=index):
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("INVALID", completed.stderr)

    def test_manifest_byte_limit_is_checked_before_decode(self):
        content = json.dumps(valid_manifest()).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "workspace.json"
            manifest_path.write_bytes(content)
            with patch.object(scientific_workspace, "_MAX_MANIFEST_BYTES", len(content)):
                self.assertEqual(
                    scientific_workspace.load_workspace_manifest(manifest_path)["workspace_id"],
                    "model-study",
                )
            with patch.object(scientific_workspace, "_MAX_MANIFEST_BYTES", len(content) - 1):
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    scientific_workspace.load_workspace_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
