import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
