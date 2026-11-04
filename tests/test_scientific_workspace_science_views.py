from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.scientific_workspace_loader import load_scientific_workspace
from scripts.scientific_core import (
    ObservationDataset,
    OdeProblem,
    evaluate_observations,
    fit_least_squares,
    parameter_sensitivities,
)


def fit_payload():
    return {
        "schema_version": 1,
        "method": "BOUNDED_LEVENBERG_MARQUARDT",
        "parameter_names": ["beta", "gamma"],
        "initial_parameters": {"beta": 0.5, "gamma": 0.2},
        "parameters": {"beta": 0.4, "gamma": 0.25},
        "bounds": {"beta": {"lower": 0.0, "upper": 1.0},
                   "gamma": {"lower": 0.0, "upper": 1.0}},
        "residuals": [1.0, -2.0],
        "cost": 2.5,
        "cost_underflowed": False,
        "status": "CONVERGED",
        "iterations": 3,
        "accepted_steps": 2,
        "function_evaluations": 8,
        "max_iterations": 10,
        "max_function_evaluations": 20,
        "finite_difference_fraction": 1e-5,
        "final_damping": 0.001,
    }


def sensitivity_payload():
    return {
        "schema_version": 1,
        "method": "CENTRAL_FINITE_DIFFERENCE",
        "solver_method": "RK4_FIXED_STEP",
        "times": [0.0, 1.0],
        "state_names": ["S", "I"],
        "parameter_names": ["beta", "gamma"],
        "base_parameters": {"beta": 0.4, "gamma": 0.2},
        "base_values": [[9.0, 1.0], [8.0, 2.0]],
        "perturbations": {"beta": 0.01, "gamma": 0.01},
        "parameter_bounds": {"beta": {"lower": 0.0, "upper": 1.0},
                             "gamma": {"lower": 0.0, "upper": 1.0}},
        "values": [
            [[1.0, 2.0], [3.0, 4.0]],
            [[5.0, 6.0], [7.0, 8.0]],
        ],
        "requested_max_step": 0.1,
        "actual_step_size": 0.1,
        "step_count_per_trajectory": 10,
        "trajectory_count": 5,
        "total_step_count": 50,
        "rhs_evaluation_count": 200,
    }


def observation_evaluation_payload():
    return {
        "schema_version": 1,
        "method": "SEGMENTED_FIXED_STEP_RK4_AT_OBSERVATION_TIMES",
        "observation_sha256": "a" * 64,
        "provenance": {"source": "synthetic fixture", "license": "test"},
        "time_unit": "day",
        "variable_units": {"S": "person", "I": "person"},
        "times": [0.0, 1.0, 2.0],
        "observed_values": [{"S": 8.0}, {"I": 2.0, "S": 7.0}, {"S": 6.0}],
        "simulated_values": [{"S": 9.0, "I": 1.0}, {"S": 8.0, "I": 2.0}, {"S": 7.0, "I": 3.0}],
        "residual_order": [
            {"time": 1.0, "variable": "S"},
            {"time": 0.0, "variable": "S"},
            {"time": 1.0, "variable": "I"},
            {"time": 2.0, "variable": "S"},
        ],
        "residuals": [1.0, 1.0, 0.0, 1.0],
        "model": {
            "time_unit": "day", "variable_units": {"S": "person", "I": "person"},
            "parameters": {"beta": 0.4}, "state_names": ["S", "I"],
            "initial_state": [9.0, 1.0],
        },
        "solver": {
            "requested_max_step": 0.1, "segment_step_sizes": [None, 0.1, 0.1],
            "segment_step_counts": [0, 10, 10], "total_step_count": 20,
            "rhs_evaluation_count": 80, "max_steps_per_interval": 100,
            "max_total_steps": 1000,
        },
    }


class ScientificResultViewBuilderTests(unittest.TestCase):
    def _view(self):
        from scripts import scientific_workspace_view

        return scientific_workspace_view

    def test_fit_summary_v1_orders_configured_parameters_and_labels_missing_units(self):
        view = self._view()
        result = view.build_fit_summary_view(
            fit_payload(), {"parameter_names": ["gamma", "beta"]}
        )

        self.assertEqual([row.name for row in result.parameters], ["gamma", "beta"])
        self.assertEqual(result.parameters[0].unit, "unidad no indicada")
        self.assertEqual(result.parameters[0].fitted_value, 0.25)
        self.assertEqual(result.residuals, (1.0, -2.0))
        self.assertEqual(result.method, "BOUNDED_LEVENBERG_MARQUARDT")

    def test_fit_summary_rejects_nonfinite_cost_and_mismatched_parameters(self):
        view = self._view()
        invalid_cost = fit_payload()
        invalid_cost["cost"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            view.build_fit_summary_view(invalid_cost, {"parameter_names": ["beta"]})

        mismatched = fit_payload()
        mismatched["parameters"].pop("gamma")
        with self.assertRaisesRegex(ValueError, "match parameter_names"):
            view.build_fit_summary_view(mismatched, {"parameter_names": ["beta"]})

    def test_sensitivity_v1_selects_time_state_parameter_axes(self):
        view = self._view()
        result = view.build_sensitivity_plot_view(
            sensitivity_payload(),
            {"state_names": ["I", "S"], "parameter_names": ["gamma"]},
        )

        self.assertEqual(result.times, (0.0, 1.0))
        self.assertEqual([series.label for series in result.series], ["I ∂/∂gamma", "S ∂/∂gamma"])
        self.assertEqual(result.series[0].values, (4.0, 8.0))
        self.assertEqual(result.series[1].values, (2.0, 6.0))
        self.assertEqual(result.time_unit, "unidad no indicada")

    def test_sensitivity_v1_rejects_invalid_tensor_dimensions(self):
        view = self._view()
        payload = sensitivity_payload()
        payload["values"][1][1].pop()
        with self.assertRaisesRegex(ValueError, "tensor"):
            view.build_sensitivity_plot_view(
                payload, {"state_names": ["I"], "parameter_names": ["gamma"]}
            )

    def test_observation_evaluation_preserves_sparse_residual_order_and_provenance(self):
        view = self._view()
        result = view.build_observation_evaluation_view(observation_evaluation_payload())

        self.assertEqual(result.residual_order, ((1.0, "S"), (0.0, "S"), (1.0, "I"), (2.0, "S")))
        self.assertEqual(result.provenance["source"], "synthetic fixture")
        by_name = {series.variable: series for series in result.series}
        self.assertEqual(by_name["S"].times, (0.0, 1.0, 2.0))
        self.assertEqual(by_name["S"].residuals, (1.0, 1.0, 1.0))
        self.assertEqual(by_name["I"].times, (1.0,))
        self.assertEqual(by_name["I"].residuals, (0.0,))
        self.assertEqual(result.time_unit, "day")

    def test_observation_evaluation_rejects_unknown_residual_coordinates(self):
        view = self._view()
        payload = observation_evaluation_payload()
        payload["residual_order"][0] = {"time": 7.0, "variable": "S"}
        with self.assertRaisesRegex(ValueError, "residual coordinates"):
            view.build_observation_evaluation_view(payload)

    def test_observation_evaluation_omits_variables_without_observed_values(self):
        view = self._view()
        payload = observation_evaluation_payload()
        for row in payload["observed_values"]:
            row.pop("I", None)
        payload["residual_order"] = [entry for entry in payload["residual_order"]
                                     if entry["variable"] != "I"]
        payload["residuals"] = [1.0, 1.0, 1.0]

        result = view.build_observation_evaluation_view(payload)

        self.assertEqual([series.variable for series in result.series], ["S"])

    def test_component_views_include_resource_path_and_digest(self):
        view = self._view()
        payload = fit_payload()
        content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fit.json").write_bytes(content)
            manifest = {
                "schema_version": 1, "workspace_id": "fit-test", "title": "Fit test",
                "resources": [{"id": "fit", "kind": "fit_result", "path": "fit.json", "sha256": digest}],
                "sections": [{"id": "results", "title": "Results", "components": [{
                    "id": "fit-view", "type": "fit_summary", "title": "Fit",
                    "resource_refs": ["fit"], "config": {"parameter_names": ["beta"]},
                }]}],
            }
            (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            component = view.build_workspace_view_model(
                load_scientific_workspace(root, "workspace.json")
            ).sections[0].components[0]

        self.assertEqual(component.source_resources[0].path, "fit.json")
        self.assertEqual(component.source_resources[0].sha256, digest)
        self.assertEqual(component.status, "ok")
        self.assertIn("identificabilidad", component.message.lower())

    def test_actual_scientific_core_v1_results_map_to_the_display_contracts(self):
        view = self._view()
        problem = OdeProblem(
            rhs=lambda _time, _state, parameters: (parameters["rate"],),
            t_span=(0.0, 2.0), initial_state=(0.0,), parameters={"rate": 1.0},
            state_names=("x",),
        )
        fit = fit_least_squares(
            lambda parameters: (parameters["rate"] - 1.5,),
            {"rate": 1.0}, {"rate": (0.0, 3.0)},
        )
        sensitivity = parameter_sensitivities(
            problem, {"rate": 0.1}, max_step=0.2
        )
        dataset = ObservationDataset.from_dict({
            "schema_version": 1, "time_unit": "day",
            "variables": [{"name": "x", "unit": "person"}],
            "observations": [
                {"time": 0.0, "values": {"x": 0.0}},
                {"time": 1.0, "values": {"x": 0.9}},
                {"time": 2.0, "values": {"x": 1.8}},
            ],
            "provenance": {"source": "synthetic test fixture"},
        })
        evaluation = evaluate_observations(
            problem, dataset, model_time_unit="day", model_variable_units={"x": "person"},
            max_step=0.2,
        )

        fit_view = view.build_fit_summary_view(
            fit.to_dict(), {"parameter_names": ["rate"]},
            unit_context={"parameter_units": {"rate": "person/day"}},
        )
        sensitivity_view = view.build_sensitivity_plot_view(
            sensitivity.to_dict(), {"state_names": ["x"], "parameter_names": ["rate"]},
            unit_context={"time_unit": "day", "state_units": {"x": "person"},
                          "parameter_units": {"rate": "person/day"}},
        )
        evaluation_view = view.build_observation_evaluation_view(evaluation.to_dict())

        self.assertEqual(fit_view.parameters[0].unit, "person/day")
        self.assertEqual(sensitivity_view.times, sensitivity.times)
        self.assertEqual(sensitivity_view.series[0].values,
                         tuple(row[0][0] for row in sensitivity.values))
        for actual, expected in zip(evaluation_view.series[0].residuals, (0.0, 0.1, 0.2)):
            self.assertAlmostEqual(actual, expected)

    def test_observation_evaluation_rejects_model_units_mismatched_with_observations(self):
        view = self._view()
        time_mismatch = copy.deepcopy(observation_evaluation_payload())
        time_mismatch["model"]["time_unit"] = "week"
        with self.assertRaisesRegex(ValueError, "model time unit must match"):
            view.build_observation_evaluation_view(time_mismatch)

        variable_mismatch = copy.deepcopy(observation_evaluation_payload())
        variable_mismatch["model"]["variable_units"]["S"] = "case"
        with self.assertRaisesRegex(ValueError, "model variable units must match"):
            view.build_observation_evaluation_view(variable_mismatch)
