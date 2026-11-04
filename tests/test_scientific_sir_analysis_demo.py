import json
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.scientific_workspace_loader import load_scientific_workspace


class SirAnalysisDemoTests(unittest.TestCase):
    def test_checked_in_demo_loads_with_manifest_resource_digests(self):
        repository = Path(__file__).resolve().parents[1]
        demo = repository / "examples" / "sir_analysis_workspace_demo"

        workspace = load_scientific_workspace(demo, "workspace.json")

        self.assertEqual(workspace.summary.to_dict()["status"], "VALID")
        self.assertGreater(len(workspace.resources), 0)

    def test_checked_in_profiled_demo_loads_with_verified_resource_digests(self):
        repository = Path(__file__).resolve().parents[1]
        demo = repository / "examples" / "sir_profiled_analysis_workspace_demo"

        workspace = load_scientific_workspace(demo, "workspace.json")
        fit = next(resource for resource in workspace.resources if resource.resource_id == "fit")
        fit_payload = json.loads(fit.content)

        self.assertEqual(workspace.summary.to_dict()["status"], "VALID")
        self.assertAlmostEqual(fit_payload["parameters"]["beta_knot_1"], 0.45, delta=1e-5)
        self.assertEqual(fit_payload["status"], "CONVERGED")

    def test_builder_creates_byte_stable_workspace_with_computed_results(self):
        repository = Path(__file__).resolve().parents[1]
        builder = repository / "scripts" / "build_sir_analysis_demo.py"
        self.assertTrue(builder.is_file(), "SIR analysis demo builder is missing")

        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = Path(first_directory)
            second = Path(second_directory)
            results = []
            for output in (first, second):
                import subprocess
                import sys

                completed = subprocess.run(
                    [sys.executable, str(builder), "--output-dir", str(output)],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                results.append(json.loads(completed.stdout))

            self.assertEqual(results[0], results[1])
            first_files = {
                path.relative_to(first).as_posix(): path.read_bytes()
                for path in first.rglob("*") if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): path.read_bytes()
                for path in second.rglob("*") if path.is_file()
            }
            self.assertEqual(first_files, second_files)

            workspace = load_scientific_workspace(first, "workspace.json")
            resources = {
                resource.resource_id: json.loads(resource.content)
                for resource in workspace.resources if resource.kind != "source_code"
            }
            fit = resources["fit"]
            sensitivity = resources["sensitivity"]
            evaluation = resources["evaluation"]
            uncertainty = resources["uncertainty"]
            embedded_builder = next(
                resource.content for resource in workspace.resources
                if resource.resource_id == "analysis-builder"
            )
            self.assertEqual(
                embedded_builder,
                builder.read_bytes().replace(b"\r\n", b"\n"),
            )
            self.assertAlmostEqual(fit["parameters"]["beta"], 0.3, delta=1e-5)
            self.assertAlmostEqual(fit["parameters"]["gamma"], 0.1, delta=1e-5)
            self.assertIn(fit["status"], {"CONVERGED", "STALLED"})
            self.assertTrue(any(
                abs(value) > 1e-6
                for time_row in sensitivity["values"]
                for state_row in time_row
                for value in state_row
            ))
            self.assertLess(max(abs(value) for value in evaluation["residuals"]), 1e-6)
            self.assertEqual(uncertainty["status"], "NOT_CALCULATED")
            fit_component = next(
                component for section in workspace.manifest["sections"]
                for component in section["components"] if component["type"] == "fit_summary"
            )
            self.assertEqual(tuple(fit_component["config"]["context_refs"]), ("model", "observations"))

    def test_profiled_demo_workspace_contains_calculated_fit_and_explicit_scientific_status(self):
        from scripts.build_sir_analysis_demo import build_demo

        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = Path(first_directory)
            second = Path(second_directory)
            result = build_demo(first, scenario="profiled")
            build_demo(second, scenario="profiled")
            first_files = {
                path.relative_to(first).as_posix(): path.read_bytes()
                for path in first.rglob("*") if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): path.read_bytes()
                for path in second.rglob("*") if path.is_file()
            }
            self.assertEqual(first_files, second_files)
            workspace = load_scientific_workspace(first, "workspace.json")
            resources = {
                resource.resource_id: json.loads(resource.content)
                for resource in workspace.resources if resource.kind != "source_code"
            }
            components = {
                component["type"]: component
                for section in workspace.manifest["sections"]
                for component in section["components"]
            }

        fit = resources["fit"]
        evaluation = resources["evaluation"]
        sensitivity = resources["sensitivity"]
        uncertainty = resources["uncertainty"]
        self.assertIn("source beta knot 1=0.45 1/day at day 5",
                      resources["observations"]["provenance"]["source"])
        self.assertEqual(result["real_user_sir"], "NOT_RUN")
        self.assertAlmostEqual(fit["parameters"]["beta_knot_1"], 0.45, delta=1e-5)
        self.assertAlmostEqual(fit["parameters"]["gamma"], 0.1, delta=1e-5)
        self.assertIn(fit["status"], {"CONVERGED", "STALLED"})
        self.assertEqual(fit["parameter_names"], ["beta_knot_1", "gamma"])
        self.assertEqual(evaluation["model"]["parameters"], fit["parameters"])
        self.assertTrue(any(abs(value) > 1e-6 for row in sensitivity["values"]
                            for state in row for value in state))
        self.assertLess(max(abs(value) for value in evaluation["residuals"]), 1e-6)
        self.assertEqual(uncertainty["status"], "NOT_CALCULATED")
        self.assertEqual(uncertainty["scientific_validity"], "NOT_ASSESSED")
        self.assertEqual(uncertainty["identifiability"], "NOT_ASSESSED")
        self.assertEqual(components["fit_summary"]["config"]["parameter_names"],
                         ("beta_knot_1", "gamma"))
        self.assertEqual(components["sensitivity_plot"]["config"]["parameter_names"],
                         ("beta_knot_1", "gamma"))

    def _make_analysis_input_workspace(self, directory: Path) -> Path:
        repository = Path(__file__).resolve().parents[1]
        source = directory / "source"
        shutil.copytree(
            repository / "examples" / "sir_profiled_analysis_workspace_demo",
            source,
        )
        config = {
            "schema_version": 1,
            "initial_parameters": {"beta_knot_1": 0.3, "gamma": 0.08},
            "bounds": {"beta_knot_1": [0.05, 0.8], "gamma": [0.02, 0.4]},
            "perturbations": {"beta_knot_1": 0.001, "gamma": 0.001},
            "fit_knots": {"beta": [1]},
            "max_iterations": 100,
            "max_function_evaluations": 500,
        }
        content = (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode()
        config_path = source / "config" / "sir-analysis.json"
        config_path.parent.mkdir()
        config_path.write_bytes(content)
        manifest_path = source / "workspace.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["resources"].append({
            "id": "analysis-config",
            "kind": "generic",
            "path": "config/sir-analysis.json",
            "sha256": hashlib.sha256(content).hexdigest(),
        })
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return source

    def test_verified_inputs_build_deterministic_analysis_workspace_without_new_algorithms(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = self._make_analysis_input_workspace(temporary)
            output_a = temporary / "analysis-a"
            output_b = temporary / "analysis-b"

            first = build_analysis_workspace(source, "workspace.json", output_a)
            second = build_analysis_workspace(source, "workspace.json", output_b)

            self.assertEqual(first, second)
            workspace = load_scientific_workspace(output_a, "workspace.json")
            resources = {
                item.resource_id: json.loads(item.content)
                for item in workspace.resources
                if item.kind != "source_code"
            }
            fit = resources["fit"]
            evaluation = resources["evaluation"]
            provenance = resources["analysis-provenance"]
            output_config = resources["analysis-config"]
            self.assertEqual(workspace.summary.to_dict()["status"], "VALID")
            self.assertEqual(first["status"], "BUILT_ANALYSIS_WORKSPACE")
            self.assertEqual(first["data_status"], "SYNTHETIC_FIXTURE")
            self.assertEqual(first["analysis_execution"], "COMPUTED_FROM_DECLARED_INPUTS")
            self.assertNotIn("real_user_sir", first)
            self.assertAlmostEqual(fit["parameters"]["beta_knot_1"], 0.45, delta=1e-5)
            self.assertAlmostEqual(fit["parameters"]["gamma"], 0.1, delta=1e-5)
            self.assertEqual(evaluation["observation_sha256"], resources["observations"]["content_sha256"])
            self.assertEqual(provenance["input_resource_sha256"]["model"],
                             next(item.sha256 for item in load_scientific_workspace(source, "workspace.json").resources
                                  if item.resource_id == "model"))
            input_resources = load_scientific_workspace(source, "workspace.json").resources
            source_config = next(item for item in input_resources if item.resource_id == "analysis-config")
            output_config_record = next(item for item in workspace.resources
                                        if item.resource_id == "analysis-config")
            self.assertEqual(output_config_record.sha256, source_config.sha256)
            self.assertEqual(provenance["input_resource_sha256"]["analysis_config"], source_config.sha256)
            self.assertEqual(provenance["status"], "CALCULATED_FROM_DIGEST_MATCHED_INPUTS")
            self.assertEqual(provenance["input_source_authentication"], "NOT_ASSESSED")
            core_resource = next(item for item in workspace.resources if item.resource_id == "scientific-core")
            core_source = Path(__file__).resolve().parents[1] / "scripts" / "scientific_core.py"
            self.assertEqual(core_resource.content, core_source.read_bytes().replace(b"\r\n", b"\n"))
            self.assertEqual(provenance["scientific_core_sha256"], core_resource.sha256)
            self.assertTrue(provenance["python_version"])
            self.assertEqual(output_config["fit_knots"], {"beta": [1]})
            self.assertEqual(resources["uncertainty"]["status"], "NOT_CALCULATED")
            self.assertEqual(resources["uncertainty"]["scientific_validity"], "NOT_ASSESSED")
            self.assertEqual(resources["uncertainty"]["identifiability"], "NOT_ASSESSED")
            files_a = {p.relative_to(output_a).as_posix(): p.read_bytes() for p in output_a.rglob("*") if p.is_file()}
            files_b = {p.relative_to(output_b).as_posix(): p.read_bytes() for p in output_b.rglob("*") if p.is_file()}
            self.assertEqual(files_a, files_b)

    def test_analysis_workspace_builder_rejects_invalid_config_before_writing(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = self._make_analysis_input_workspace(temporary)
            config_path = source / "config" / "sir-analysis.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["unknown_algorithm"] = "invented"
            content = (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode()
            config_path.write_bytes(content)
            manifest_path = source / "workspace.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            next(item for item in manifest["resources"] if item["id"] == "analysis-config")["sha256"] = hashlib.sha256(content).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                                     encoding="utf-8")
            output = temporary / "analysis"

            with self.assertRaisesRegex(ValueError, "analysis configuration"):
                build_analysis_workspace(source, "workspace.json", output)

            self.assertFalse(output.exists())

    def test_analysis_workspace_builder_rejects_resource_digest_mismatch_before_writing(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = self._make_analysis_input_workspace(temporary)
            observations_path = source / "data" / "observations.json"
            observations_path.write_bytes(observations_path.read_bytes() + b" ")
            output = temporary / "analysis"

            with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                build_analysis_workspace(source, "workspace.json", output)

            self.assertFalse(output.exists())

    def test_free_form_data_status_does_not_make_generated_manifest_invalid(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = self._make_analysis_input_workspace(temporary)
            observations_path = source / "data" / "observations.json"
            observations = json.loads(observations_path.read_text(encoding="utf-8"))
            observations.pop("content_sha256", None)
            observations["provenance"]["data_status"] = "SYNTHETIC\nFIXTURE"
            content = (json.dumps(observations, sort_keys=True, separators=(",", ":")) + "\n").encode()
            observations_path.write_bytes(content)
            manifest_path = source / "workspace.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            next(item for item in manifest["resources"] if item["id"] == "observations")["sha256"] = hashlib.sha256(content).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                                     encoding="utf-8")
            output = temporary / "analysis"

            result = build_analysis_workspace(source, "workspace.json", output)
            workspace = load_scientific_workspace(output, "workspace.json")
            provenance = next(item for item in workspace.resources if item.resource_id == "analysis-provenance")

            self.assertEqual(workspace.summary.to_dict()["status"], "VALID")
            self.assertEqual(result["data_status"], "SYNTHETIC\nFIXTURE")
            self.assertEqual(json.loads(provenance.content)["data_status"], "SYNTHETIC\nFIXTURE")

    def test_analysis_workspace_builder_never_overwrites_or_writes_inside_source(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = self._make_analysis_input_workspace(temporary)
            existing_output = temporary / "existing"
            existing_output.mkdir()
            sentinel = existing_output / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "output directory must be empty"):
                build_analysis_workspace(source, "workspace.json", existing_output)
            with self.assertRaisesRegex(ValueError, "outside the source project"):
                build_analysis_workspace(source, "workspace.json", source / "generated")

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((source / "generated").exists())

    def test_cli_builds_analysis_from_verified_sir_workspace_resources(self):
        import subprocess
        import sys

        repository = Path(__file__).resolve().parents[1]
        builder = repository / "scripts" / "build_sir_analysis_demo.py"
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = repository / "examples" / "sir_analysis_input_demo"
            output = temporary / "analysis-output"
            completed = subprocess.run(
                [
                    sys.executable, str(builder),
                    "--source-root", str(source),
                    "--source-manifest", "workspace.json",
                    "--output-dir", str(output),
                ],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "BUILT_ANALYSIS_WORKSPACE")
            self.assertEqual(
                load_scientific_workspace(output, "workspace.json").summary.to_dict()["status"],
                "VALID",
            )


if __name__ == "__main__":
    unittest.main()
