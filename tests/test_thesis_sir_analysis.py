from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.thesis_sir_model import (
    HarmonicTerm,
    ThesisSIRParameters,
    WeeklyCountObservations,
    evaluate_thesis_sir_weekly_counts,
)
from scripts.thesis_sir_analysis import analyze_thesis_sir_parameters


def _synthetic_observations(parameters: ThesisSIRParameters) -> WeeklyCountObservations:
    labels = tuple(f"synthetic-week-{index + 1:02d}" for index in range(8))
    empty = WeeklyCountObservations(labels, (0,) * len(labels), "SSEC_P3_31_SYNTHETIC")
    forward = evaluate_thesis_sir_weekly_counts(
        parameters, empty, max_step=0.1, max_steps_per_interval=10
    )
    counts = tuple(int(round(value)) for value in forward.predicted_means)
    canonical = json.dumps(
        {"series_id": empty.series_id, "week_labels": labels, "counts": counts},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return WeeklyCountObservations(
        labels, counts, empty.series_id, hashlib.sha256(canonical).hexdigest()
    )


class ThesisSIRAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.truth = ThesisSIRParameters(
            d0=-0.45,
            harmonics=(HarmonicTerm(0.15, 0.04, 0.3),),
            gamma=0.18,
            log10_initial_infectious=6.0,
            susceptible_fraction=0.985,
            ascertainment_fraction=0.3,
            delay_days=0.0,
        )
        self.observations = _synthetic_observations(self.truth)
        self.initial = ThesisSIRParameters(
            d0=-0.75,
            harmonics=self.truth.harmonics,
            gamma=self.truth.gamma,
            log10_initial_infectious=self.truth.log10_initial_infectious,
            susceptible_fraction=self.truth.susceptible_fraction,
            ascertainment_fraction=self.truth.ascertainment_fraction,
            delay_days=self.truth.delay_days,
        )

    def _analyze(self, **overrides):
        options = {
            "parameters": self.initial,
            "observations": self.observations,
            "initial_parameters": {"d0": -0.75},
            "bounds": {"d0": (-1.0, 0.0)},
            "perturbations": {"d0": 0.02},
            "max_step": 0.1,
            "max_steps_per_interval": 10,
            "max_total_steps": 50_000,
        }
        options.update(overrides)
        return analyze_thesis_sir_parameters(**options)

    def test_exact_thesis_observer_fit_reuses_existing_analysis_contracts(self):
        result = self._analyze()
        payload = result.to_dict()

        self.assertIn(result.fit.status, {"CONVERGED", "STALLED", "MAX_ITERATIONS", "MAX_FUNCTION_EVALUATIONS"})
        self.assertAlmostEqual(result.fit.parameters["d0"], self.truth.d0, delta=5e-3)
        self.assertEqual(payload["analysis_execution"], "COMPUTED_FROM_DECLARED_INPUTS")
        self.assertEqual(payload["scientific_validity"], "NOT_ASSESSED")
        self.assertEqual(payload["identifiability"], "NOT_ASSESSED")
        self.assertEqual(payload["uncertainty"], "NOT_CALCULATED")
        self.assertLessEqual(
            payload["work"]["effective_max_function_evaluations"],
            payload["work"]["requested_max_function_evaluations"],
        )
        self.assertLessEqual(
            payload["work"]["total_rk4_steps"], payload["work"]["max_total_rk4_steps"]
        )
        self.assertEqual(result.evaluation["observation_sha256"], self.observations.source_sha256)
        self.assertEqual(result.evaluation["provenance"]["source"], self.observations.series_id)
        self.assertEqual(len(result.evaluation["residuals"]), len(self.observations.counts))
        for observed, simulated, residual in zip(
            result.evaluation["observed_values"],
            result.evaluation["simulated_values"],
            result.evaluation["residuals"],
        ):
            self.assertAlmostEqual(
                simulated["weekly_cases"] - observed["weekly_cases"], residual
            )
        self.assertLess(max(abs(value) for value in result.fit.residuals), 0.5)
        self.assertEqual(result.sensitivity.parameter_names, ("d0",))
        self.assertEqual(result.solution.parameters, result.sensitivity.base_solution.parameters)

    def test_analysis_rejects_observation_only_and_discrete_fit_parameters(self):
        for name in ("ascertainment_fraction", "delay_days", "log10_initial_infectious"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "not supported for fitting"):
                self._analyze(
                    initial_parameters={name: 0.3},
                    bounds={name: (0.1, 0.9)},
                    perturbations={name: 0.01},
                )

    def test_exact_harmonic_coefficient_uses_the_existing_bounded_fit(self):
        start = ThesisSIRParameters(
            d0=self.truth.d0,
            harmonics=(HarmonicTerm(-0.1, 0.04, 0.3),),
            gamma=self.truth.gamma,
            log10_initial_infectious=self.truth.log10_initial_infectious,
            susceptible_fraction=self.truth.susceptible_fraction,
            ascertainment_fraction=self.truth.ascertainment_fraction,
            delay_days=self.truth.delay_days,
        )
        result = self._analyze(
            parameters=start,
            initial_parameters={"harmonic_0_cosine": -0.1},
            bounds={"harmonic_0_cosine": (-0.5, 0.5)},
            perturbations={"harmonic_0_cosine": 0.02},
        )

        self.assertAlmostEqual(
            result.fit.parameters["harmonic_0_cosine"],
            self.truth.harmonics[0].cosine,
            delta=5e-3,
        )
        self.assertEqual(result.parameters.harmonics[0].cosine,
                         result.fit.parameters["harmonic_0_cosine"])

    def test_analysis_rejects_fit_ranges_outside_thesis_contract(self):
        with self.assertRaisesRegex(ValueError, "outside the thesis parameter domain"):
            self._analyze(bounds={"d0": (-3.0, 0.0)})

    def test_weekly_observation_contract_accepts_interval_mean_evaluation(self):
        from scripts.scientific_workspace_view import build_observation_evaluation_view

        result = self._analyze()
        self.assertEqual(
            result.evaluation["method"], "THESIS_SIR_WEEKLY_COUNT_INTERVAL_RK4"
        )
        self.assertEqual(result.evaluation["variable_units"]["weekly_cases"],
                         "cases per 7-day interval")
        self.assertEqual(
            result.evaluation["model"]["state_names"],
            ["S", "I", "R", "cumulative_incidence"],
        )
        view = build_observation_evaluation_view(result.evaluation)
        self.assertEqual(view.method, "THESIS_SIR_WEEKLY_COUNT_INTERVAL_RK4")
        self.assertEqual(view.series[0].variable, "weekly_cases")

    def test_analysis_contracts_load_in_existing_workspace_views_with_thesis_units(self):
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        result = self._analyze()
        payload = result.to_dict()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def resource(resource_id, kind, relative_path, content):
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
                path.write_bytes(raw)
                return {
                    "id": resource_id,
                    "kind": kind,
                    "path": relative_path.replace("\\", "/"),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }

            resources = [
                resource("model", "model_spec", "model/model.json", payload["model"]),
                resource("simulation", "simulation_result", "results/simulation.json", payload["simulation"]),
                resource("fit", "fit_result", "results/fit.json", payload["fit"]),
                resource("sensitivity", "sensitivity_result", "results/sensitivity.json", payload["sensitivity"]),
                resource("evaluation", "observation_evaluation", "results/evaluation.json", payload["evaluation"]),
            ]
            manifest = {
                "schema_version": 1,
                "workspace_id": "thesis-sir-analysis-test",
                "title": "Synthetic thesis SIR analysis",
                "description": "Deterministic synthetic test only.",
                "resources": resources,
                "sections": [{
                    "id": "analysis-results",
                    "title": "Analysis results",
                    "components": [
                        {"id": "trajectory", "type": "simulation_plot", "title": "Trajectory",
                         "resource_refs": ["simulation"], "config": {
                             "context_refs": ["model"], "series": ["S", "I", "R"], "x_axis": "time"}},
                        {"id": "fit-view", "type": "fit_summary", "title": "Fit",
                         "resource_refs": ["fit"], "config": {
                             "context_refs": ["model"], "parameter_names": ["d0"]}},
                        {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensitivity",
                         "resource_refs": ["sensitivity"], "config": {
                             "context_refs": ["model"], "parameter_names": ["d0"],
                             "state_names": ["S", "I", "R"]}},
                        {"id": "residual-view", "type": "residual_plot", "title": "Weekly residuals",
                         "resource_refs": ["evaluation"], "config": {}},
                    ],
                }],
            }
            manifest_path = root / "workspace.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            view = build_workspace_view_model(load_scientific_workspace(root, "workspace.json"))

        components = {
            component.component_id: component
            for section in view.sections
            for component in section.components
        }
        self.assertEqual(
            components["fit-view"].content.parameters[0].unit,
            "dimensionless",
            (components["fit-view"].status, components["fit-view"].message,
             components["fit-view"].source_resources),
        )
        self.assertEqual(components["sensitivity-view"].content.time_unit, "week")
        self.assertEqual(components["residual-view"].content.method,
                         "THESIS_SIR_WEEKLY_COUNT_INTERVAL_RK4")

    def test_work_budget_is_checked_before_fit_or_sensitivity(self):
        with self.assertRaisesRegex(ValueError, "insufficient for final evaluation and sensitivity"):
            self._analyze(max_total_steps=200)

    def test_sensitivity_intermediate_budget_matches_solver_before_fit(self):
        observations = WeeklyCountObservations(
            tuple(f"week-{index:02d}" for index in range(56)), (0,) * 56
        )

        with patch("scripts.thesis_sir_analysis.evaluate_thesis_sir_weekly_counts") as evaluate:
            with self.assertRaisesRegex(ValueError, "sensitivity output exceeds"):
                self._analyze(
                    observations=observations,
                    max_step=0.001,
                    max_steps_per_interval=1000,
                    max_total_steps=1_000_000,
                )
        evaluate.assert_not_called()

    def test_sensitivity_refuses_a_perturbation_that_crosses_fit_bounds(self):
        with self.assertRaisesRegex(ValueError, "sensitivity perturbation must stay inside fit bounds"):
            self._analyze(
                initial_parameters={"d0": -0.99},
                bounds={"d0": (-1.0, 0.0)},
                perturbations={"d0": 0.05},
            )


if __name__ == "__main__":
    unittest.main()
