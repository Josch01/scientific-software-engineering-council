from __future__ import annotations

import hashlib
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtCore = None
    QtGui = None
    QtWidgets = None


def _workspace_fixture(root: Path) -> None:
    resources = {
        "fit": ("fit_result", {
            "schema_version": 1, "method": "BOUNDED_LEVENBERG_MARQUARDT",
            "parameter_names": ["beta", "gamma"],
            "initial_parameters": {"beta": 0.5, "gamma": 0.2},
            "parameters": {"beta": 0.4, "gamma": 0.25},
            "bounds": {"beta": {"lower": 0.0, "upper": 1.0},
                       "gamma": {"lower": 0.0, "upper": 1.0}},
            "residuals": [1.0, -2.0], "cost": 2.5, "cost_underflowed": False,
            "status": "CONVERGED", "iterations": 3, "accepted_steps": 2,
            "function_evaluations": 8, "max_iterations": 10,
            "max_function_evaluations": 20, "finite_difference_fraction": 1e-5,
            "final_damping": 0.001,
        }),
        "sensitivity": ("sensitivity_result", {
            "schema_version": 1, "method": "CENTRAL_FINITE_DIFFERENCE",
            "solver_method": "RK4_FIXED_STEP", "times": [0.0, 1.0],
            "state_names": ["S", "I"], "parameter_names": ["beta", "gamma"],
            "base_parameters": {"beta": 0.4, "gamma": 0.2},
            "base_values": [[9.0, 1.0], [8.0, 2.0]],
            "perturbations": {"beta": 0.01, "gamma": 0.01},
            "parameter_bounds": {"beta": {"lower": 0.0, "upper": 1.0},
                                 "gamma": {"lower": 0.0, "upper": 1.0}},
            "values": [[[1.0, 2.0], [3.0, 4.0]], [[5.0, 6.0], [7.0, 8.0]]],
            "requested_max_step": 0.1, "actual_step_size": 0.1,
            "step_count_per_trajectory": 10, "trajectory_count": 5,
            "total_step_count": 50, "rhs_evaluation_count": 200,
        }),
        "evaluation": ("observation_evaluation", {
            "schema_version": 1,
            "method": "SEGMENTED_FIXED_STEP_RK4_AT_OBSERVATION_TIMES",
            "observation_sha256": "a" * 64,
            "provenance": {"source": "synthetic fixture", "license": "test"},
            "time_unit": "day", "variable_units": {"S": "person", "I": "person"},
            "times": [0.0, 1.0, 2.0],
            "observed_values": [{"S": 8.0}, {"I": 2.0, "S": 7.0}, {"S": 6.0}],
            "simulated_values": [{"S": 9.0, "I": 1.0}, {"S": 8.0, "I": 2.0}, {"S": 7.0, "I": 3.0}],
            "residual_order": [
                {"time": 1.0, "variable": "S"}, {"time": 0.0, "variable": "S"},
                {"time": 1.0, "variable": "I"}, {"time": 2.0, "variable": "S"},
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
        }),
        "uncertainty": ("uncertainty_result", {"status": "NOT_CALCULATED", "note": "No estimator"}),
    }
    manifest_resources = []
    for resource_id, (kind, payload) in resources.items():
        relative_path = f"results/{resource_id}.json"
        content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest_resources.append({
            "id": resource_id, "kind": kind, "path": relative_path,
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    manifest = {
        "schema_version": 1, "workspace_id": "science-views-demo",
        "title": "Synthetic scientific view demonstration", "resources": manifest_resources,
        "sections": [{"id": "results", "title": "Results", "components": [
            {"id": "fit-view", "type": "fit_summary", "title": "Fit",
             "resource_refs": ["fit"], "config": {"parameter_names": ["gamma", "beta"]}},
            {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensitivity",
             "resource_refs": ["sensitivity"], "config": {
                 "state_names": ["I", "S"], "parameter_names": ["gamma"]}},
            {"id": "residual-view", "type": "residual_plot", "title": "Residuals",
             "resource_refs": ["evaluation"], "config": {}},
            {"id": "uncertainty-view", "type": "uncertainty_summary", "title": "Uncertainty",
             "resource_refs": ["uncertainty"], "config": {"quantities": ["I"]}},
        ]}],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class ScientificWorkspaceQtResultViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        _workspace_fixture(cls.root)
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow
        cls.window = ScientificWorkspaceWindow()
        with patch("scripts.scientific_workspace_qt_charts.WEBENGINE_AVAILABLE", False):
            cls.window.load_workspace(cls.root, "workspace.json")
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.temp.cleanup()

    def test_fit_renderer_shows_parameters_bounds_units_and_resource_digest(self):
        window = self.window
        summary = window.findChild(QtWidgets.QLabel, "fit-summary-fit-view")
        table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
        provenance = window.findChild(QtWidgets.QLabel, "source-provenance-fit-view")

        self.assertIsNotNone(summary)
        self.assertIn("BOUNDED_LEVENBERG_MARQUARDT", summary.text())
        self.assertIn("Identificabilidad práctica: no evaluada", summary.text())
        self.assertIsNotNone(table)
        self.assertEqual(table.item(0, 0).text(), "gamma")
        self.assertEqual(table.item(0, 5).text(), "unidad no indicada")
        self.assertIsNotNone(provenance)
        self.assertIn("SHA-256", provenance.text())

    def test_fit_residual_table_is_bounded_and_samples_endpoints(self):
        component = next(
            component for section in self.window.workspace_view_model.sections
            for component in section.components if component.component_id == "fit-view"
        )
        residual_values = tuple(float(index) for index in range(10_000))
        component = replace(
            component, content=replace(component.content, residuals=residual_values)
        )
        host = QtWidgets.QWidget()
        self.addCleanup(host.close)
        layout = QtWidgets.QVBoxLayout(host)
        self.window._render_fit_summary(layout, component)
        residual_table = host.findChild(QtWidgets.QTableWidget, "fit-residuals-table")

        self.assertEqual(residual_table.rowCount(), 200)
        self.assertEqual(residual_table.item(0, 0).text(), "0")
        self.assertEqual(residual_table.item(199, 0).text(), "9999")
        self.assertIn("200 filas de 10000", residual_table.toolTip())

    def test_sensitivity_renderer_shows_axes_series_and_provenance(self):
        chart = self.window.findChild(QtWidgets.QWidget, "plot-sensitivity-view-sensitivity-0")
        self.assertIsNotNone(chart)
        self.assertIn("Tiempo · unidad no indicada", chart.accessibleDescription())
        fallback = chart.findChild(QtWidgets.QFrame, "scientificChartFallback")
        self.assertIsNotNone(fallback)
        table = fallback.findChild(QtWidgets.QTableWidget, "scientificChartDataTable")
        self.assertIsNotNone(table)
        self.assertEqual(table.horizontalHeaderItem(1).text(), "I ∂/∂gamma")
        self.assertIsNotNone(
            self.window.findChild(QtWidgets.QLabel, "source-provenance-sensitivity-view")
        )

    def test_residual_renderer_shows_observed_simulated_residuals_units_and_provenance(self):
        observed = self.window.findChild(QtWidgets.QWidget, "plot-residual-view-observed-0")
        residual = self.window.findChild(QtWidgets.QWidget, "plot-residual-view-residual-0")
        provenance_labels = [
            label.text() for label in self.window.findChildren(QtWidgets.QLabel)
            if "synthetic fixture" in label.text()
        ]

        self.assertIsNotNone(observed)
        self.assertIsNotNone(residual)
        self.assertIn("simulado − observado", residual.accessibleName())
        self.assertIn("Residuo · person", residual.accessibleDescription())
        observed_table = observed.findChild(QtWidgets.QTableWidget, "scientificChartDataTable")
        self.assertIsNotNone(observed_table)
        self.assertEqual(observed_table.horizontalHeaderItem(0).text(), "Tiempo · day")
        self.assertTrue(provenance_labels)
        self.assertTrue(any("SHA-256 normalizado" in label for label in provenance_labels))
        self.assertIsNotNone(self.window.findChild(
            QtWidgets.QLabel, "source-provenance-residual-view"
        ))

    def test_native_fallback_draws_a_scientific_plot_into_a_qt_image(self):
        chart = self.window.findChild(QtWidgets.QWidget, "plot-sensitivity-view-sensitivity-0")
        chart.resize(900, 560)
        chart.show()
        self.app.processEvents()
        image = QtGui.QImage(chart.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("white"))
        painter = QtGui.QPainter(image)
        chart.render(painter, QtCore.QPoint())
        painter.end()
        small = image.scaled(240, 150)
        non_white = sum(
            1 for y in range(small.height()) for x in range(small.width())
            if small.pixelColor(x, y) != QtGui.QColor("white")
        )

        self.assertGreater(non_white, 100, "native plot widget rendered as a blank image")

    def test_uncertainty_renderer_marks_not_assessed_without_intervals(self):
        status = self.window.findChild(QtWidgets.QLabel, "uncertainty-status-uncertainty-view")
        self.assertIsNotNone(status)
        self.assertIn("NOT_ASSESSED / NOT_CALCULATED", status.text())
        self.assertNotIn("confidence band", status.text().lower())
        self.assertIsNotNone(self.window.findChild(QtWidgets.QPlainTextEdit, "data-uncertainty-view"))

    def test_synthetic_demo_workspace_loads_all_three_scientific_views(self):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        examples = Path(__file__).resolve().parents[1] / "examples"
        window = ScientificWorkspaceWindow()
        self.addCleanup(window.close)
        with patch("scripts.scientific_workspace_qt_charts.WEBENGINE_AVAILABLE", False):
            model = window.load_workspace(
                examples, "scientific_workspace_science_views_demo/workspace.json"
            )
        window.show()
        self.app.processEvents()

        components = {item.component_type: item for item in model.sections[0].components}
        self.assertEqual(components["fit_summary"].status, "ok")
        self.assertEqual(components["sensitivity_plot"].status, "ok")
        self.assertEqual(components["residual_plot"].status, "ok")
        self.assertIsNotNone(window.findChild(QtWidgets.QTableWidget, "fit-parameters-table"))
        self.assertIsNotNone(window.findChild(QtWidgets.QWidget, "plot-sensitivity-view-sensitivity-0"))
        self.assertIsNotNone(window.findChild(QtWidgets.QWidget, "plot-residual-view-observed-0"))

    def test_computed_sir_demo_renders_actual_fit_units_status_and_sensitivity(self):
        from scripts.build_sir_analysis_demo import build_demo
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_demo(root)
            fit_record = json.loads((root / "results" / "fit.json").read_text(encoding="utf-8"))
            sensitivity_record = json.loads(
                (root / "results" / "sensitivity.json").read_text(encoding="utf-8")
            )
            simulation_record = json.loads(
                (root / "results" / "simulation.json").read_text(encoding="utf-8")
            )
            window = ScientificWorkspaceWindow()
            self.addCleanup(window.close)
            with patch("scripts.scientific_workspace_qt_charts.WEBENGINE_AVAILABLE", False):
                model = window.load_workspace(root, "workspace.json")
            window.show()
            self.app.processEvents()

            components = {item.component_id: item for section in model.sections
                          for item in section.components}
            fit_summary = window.findChild(QtWidgets.QLabel, "fit-summary-fit-view")
            fit_table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
            provenance = window.findChildren(QtWidgets.QLabel, "source-provenance-fit-view")
            sensitivity_chart = window.findChild(
                QtWidgets.QWidget, "plot-sensitivity-view-sensitivity-0"
            )
            simulation_chart = window.findChild(QtWidgets.QWidget, "plot-trajectory")
            simulation_summary = window.findChild(
                QtWidgets.QLabel, "simulation-summary-trajectory"
            )
            self.assertIsNotNone(fit_summary)
            self.assertIsNotNone(fit_table)
            self.assertGreaterEqual(len(provenance), 3)
            self.assertIsNotNone(sensitivity_chart)
            self.assertIsNotNone(simulation_chart)
            self.assertIsNotNone(simulation_summary)
            chart_fallback = sensitivity_chart.findChild(QtWidgets.QFrame, "scientificChartFallback")
            chart_table = chart_fallback.findChild(
                QtWidgets.QTableWidget, "scientificChartDataTable"
            )

            self.assertEqual(components["fit-view"].content.status, fit_record["status"])
            self.assertIn(f"estado {fit_record['status']}", fit_summary.text())
            self.assertEqual(fit_table.item(0, 0).text(), "beta")
            self.assertEqual(fit_table.item(0, 2).text(), f"{fit_record['parameters']['beta']:.8g}")
            self.assertEqual(fit_table.item(0, 5).text(), "1/day")
            self.assertEqual(fit_table.item(1, 5).text(), "1/day")
            provenance_text = " ".join(label.text() for label in provenance)
            self.assertIn("model/model.json", provenance_text)
            self.assertIn("data/observations.json", provenance_text)
            self.assertIn("SHA-256", provenance_text)
            self.assertIn("Eje x: Tiempo · day", sensitivity_chart.accessibleDescription())
            self.assertIn("Derivada local · person / 1/day", sensitivity_chart.accessibleDescription())
            self.assertEqual(chart_table.horizontalHeaderItem(1).text(), "S ∂/∂beta")
            self.assertEqual(
                float(chart_table.item(0, 1).text()),
                sensitivity_record["values"][0][0][0],
            )
            self.assertEqual(components["sensitivity-view"].status, "ok")
            self.assertEqual(
                dict(components["trajectory"].content["parameters"]),
                simulation_record["parameters"],
            )
            self.assertIn("Eje x: Tiempo · day", simulation_chart.accessibleDescription())
            self.assertIn("Eje y: Población · person", simulation_chart.accessibleDescription())
            self.assertIn("100 pasos", simulation_summary.text())
            self.assertIn(
                f"beta={simulation_record['parameters']['beta']:.8g} 1/day",
                simulation_summary.text(),
            )
            simulation_sources = window.findChildren(
                QtWidgets.QLabel, "source-provenance-trajectory"
            )
            self.assertGreaterEqual(len(simulation_sources), 2)
