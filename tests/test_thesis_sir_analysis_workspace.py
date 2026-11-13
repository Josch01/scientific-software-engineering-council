from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from scripts.scientific_workspace_loader import load_scientific_workspace
from scripts.scientific_workspace_view import build_workspace_view_model
from scripts.thesis_sir_analysis import analyze_thesis_sir_parameters
from scripts.thesis_sir_analysis_workspace import write_thesis_sir_analysis_workspace
from scripts.thesis_sir_model import (
    HarmonicTerm,
    ThesisSIRParameters,
    WeeklyCountObservations,
    evaluate_thesis_sir_weekly_counts,
)


def _analysis():
    truth = ThesisSIRParameters(
        d0=-0.45,
        harmonics=(HarmonicTerm(0.15, 0.04, 0.3),),
        gamma=0.18,
        log10_initial_infectious=6.0,
        susceptible_fraction=0.985,
        ascertainment_fraction=0.3,
        delay_days=0.0,
    )
    labels = tuple(f"week-{index + 1:02d}" for index in range(8))
    empty = WeeklyCountObservations(labels, (0,) * 8, "P3_32_SYNTHETIC")
    generated = evaluate_thesis_sir_weekly_counts(
        truth, empty, max_step=0.1, max_steps_per_interval=10
    )
    observations = WeeklyCountObservations(
        labels, tuple(round(value) for value in generated.predicted_means), empty.series_id
    )
    return analyze_thesis_sir_parameters(
        replace(truth, d0=-0.75),
        observations,
        initial_parameters={"d0": -0.75},
        bounds={"d0": (-1.0, 0.0)},
        perturbations={"d0": 0.02},
        max_step=0.1,
        max_steps_per_interval=10,
    )


class ThesisSIRAnalysisWorkspaceTests(unittest.TestCase):
    def test_workspace_round_trips_all_analysis_views_and_provenance(self):
        result = _analysis()
        with tempfile.TemporaryDirectory() as temporary:
            root = write_thesis_sir_analysis_workspace(temporary, result)
            self.assertEqual(root.parent, Path(temporary))
            loaded = load_scientific_workspace(root, "workspace.json")
            view = build_workspace_view_model(loaded)

        components = {
            component.component_id: component
            for section in view.sections
            for component in section.components
        }
        self.assertTrue(all(item.status == "ok" for item in components.values()))
        self.assertEqual(components["fit"].content.parameters[0].unit, "dimensionless")
        self.assertEqual(components["sensitivity"].content.time_unit, "week")
        self.assertEqual(components["residuals"].content.method,
                         "THESIS_SIR_WEEKLY_COUNT_INTERVAL_RK4")
        self.assertEqual(components["residuals"].content.series[0].unit,
                         "cases per 7-day interval")
        self.assertEqual(components["uncertainty"].content["status"], "NOT_CALCULATED")
        self.assertIn("NOT_ASSESSED", loaded.manifest["description"])
        self.assertIn("NOT_CALCULATED", loaded.manifest["description"])

    def test_workspace_output_is_create_only_and_keeps_source_digest(self):
        result = _analysis()
        with tempfile.TemporaryDirectory() as temporary:
            first = write_thesis_sir_analysis_workspace(temporary, result)
            second = write_thesis_sir_analysis_workspace(temporary, result)
            self.assertNotEqual(first, second)
            loaded = load_scientific_workspace(first, "workspace.json")
            data = next(resource for resource in loaded.resources if resource.resource_id == "observations")
            payload = json.loads(data.content.decode("utf-8"))
            run_log_resource = next(
                resource for resource in loaded.resources if resource.resource_id == "run-log"
            )
            run_record = json.loads(run_log_resource.content.decode("utf-8"))

        self.assertEqual(payload["series_id"], result.observations.series_id)
        self.assertEqual(payload["week_labels"], list(result.observations.week_labels))
        self.assertEqual(payload["counts"], list(result.observations.counts))
        self.assertEqual(payload["source_sha256"], result.observations.source_sha256)
        self.assertEqual(run_record["timing_status"], "NOT_RECORDED")
        self.assertEqual(run_record["human_review"], "PENDING")

    def test_workspace_writer_rejects_missing_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            with self.assertRaisesRegex(ValueError, "existing output directory"):
                write_thesis_sir_analysis_workspace(missing, _analysis())


if __name__ == "__main__":
    unittest.main()
