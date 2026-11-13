"""Offscreen smoke tests for the optional PySide6 scientific workspace shell."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # PySide6 is an optional desktop dependency.
    QtCore = None
    QtGui = None
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class ScientificWorkspaceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.examples = Path(__file__).resolve().parents[1] / "examples"

    def _window(self):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        window = ScientificWorkspaceWindow()
        window.load_workspace(self.examples, "sir_scientific_workspace.json")
        window.show()
        self.app.processEvents()
        self.addCleanup(window.close)
        return window

    def test_trajectory_chart_uses_dark_surface_and_scientific_palette(self):
        from scripts.scientific_ui_theme import CHART_SERIES_COLORS, COLORS
        from scripts.scientific_workspace_qt import _TrajectoryPlot

        plot = _TrajectoryPlot({
            "times": (0.0, 1.0, 2.0),
            "values": ((9.0, 1.0, 0.0), (7.0, 2.0, 1.0), (4.0, 3.0, 3.0)),
            "series_names": ("S", "I", "R"),
            "series_indices": (0, 1, 2),
            "time_unit": "day",
            "population_unit": "people",
        })
        plot.resize(500, 300)
        image = QtGui.QImage(plot.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("transparent"))
        plot.render(image)

        self.assertEqual(image.pixelColor(5, 5).name(), COLORS["surface"])
        self.assertEqual(plot._COLORS, CHART_SERIES_COLORS)
        self.assertEqual(plot._PEN_STYLES["dotted"], QtCore.Qt.PenStyle.DotLine)

    def _wait_for_simulation(self, window):
        loop = QtCore.QEventLoop()
        timer = QtCore.QTimer()
        timer.setInterval(10)
        timer.timeout.connect(
            lambda: loop.quit() if not window.simulation_running else None
        )
        timer.start()
        QtCore.QTimer.singleShot(5000, loop.quit)
        if window.simulation_running:
            loop.exec()
        timer.stop()
        self.app.processEvents()

    def test_verified_workspace_renders_contract_components_and_digest_status(self):
        window = self._window()

        self.assertEqual(window.workspace_view_model.workspace_id, "sir-demo")
        digest_status = window.findChild(QtWidgets.QLabel, "workspaceDigestStatus")
        self.assertIsNotNone(digest_status)
        self.assertIn("ARTIFACT_DIGESTS_MATCHED", digest_status.text())
        self.assertIsNotNone(window.findChild(QtWidgets.QTableWidget, "parameters-table"))
        self.assertIsNotNone(window.findChild(QtWidgets.QWidget, "plot-trajectory"))
        self.assertIn("no valida", window.scientific_notice.text().lower())

    def test_declined_human_confirmation_does_not_call_sir_solver(self):
        window = self._window()
        run_button = window.findChild(QtWidgets.QPushButton, "run-simulation-trajectory")
        self.assertIsNotNone(run_button)

        with patch(
            "scripts.scientific_workspace_actions.solve_sir_model",
            side_effect=AssertionError("declined run reached the solver"),
        ) as solver, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ):
            run_button.click()
            self.app.processEvents()

        solver.assert_not_called()
        self.assertFalse(window.simulation_running)
        self.assertEqual(window.simulation_results, {})

    def test_approved_run_shows_validated_result_and_preserves_project_bytes(self):
        manifest_before = (self.examples / "sir_scientific_workspace.json").read_bytes()
        model_before = (self.examples / "sir_model_demo.json").read_bytes()
        window = self._window()
        run_button = window.findChild(QtWidgets.QPushButton, "run-simulation-trajectory")
        self.assertIsNotNone(run_button)

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            run_button.click()
            self._wait_for_simulation(window)

        result = window.simulation_results["trajectory"]
        self.assertEqual(result.status, "ok")
        self.assertGreater(result.content["row_count"], 1)
        self.assertIn("RK4_FIXED_STEP", result.message)
        current_button = window.findChild(QtWidgets.QPushButton, "run-simulation-trajectory")
        self.assertIsNotNone(current_button)
        self.assertTrue(current_button.isEnabled(), "the one-shot run control should re-enable after completion")
        self.assertEqual((self.examples / "sir_scientific_workspace.json").read_bytes(), manifest_before)
        self.assertEqual((self.examples / "sir_model_demo.json").read_bytes(), model_before)

    def test_digest_mismatch_does_not_populate_the_window(self):
        window = self._window()
        original = json.loads((self.examples / "sir_scientific_workspace.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for resource in original["resources"]:
                shutil.copyfile(self.examples / resource["path"], root / resource["path"])
            original["resources"][0]["sha256"] = "0" * 64
            (root / "workspace.json").write_text(json.dumps(original), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                window.load_workspace(root, "workspace.json")

        self.assertEqual(window.workspace_view_model.workspace_id, "sir-demo")

    def test_open_dialog_converts_nested_manifest_path_to_portable_separators(self):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("sir_model_demo.json", "sir_demo_result.json"):
                shutil.copyfile(self.examples / name, root / name)
            nested = root / "configs"
            nested.mkdir()
            shutil.copyfile(
                self.examples / "sir_scientific_workspace.json",
                nested / "sir_scientific_workspace.json",
            )
            window = ScientificWorkspaceWindow()
            self.addCleanup(window.close)
            with patch.object(
                QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(root)
            ), patch.object(
                QtWidgets.QFileDialog,
                "getOpenFileName",
                return_value=(str(nested / "sir_scientific_workspace.json"), ""),
            ), patch.object(QtWidgets.QMessageBox, "critical") as error_dialog:
                window.open_workspace_dialog()

        error_dialog.assert_not_called()
        self.assertEqual(window.workspace_view_model.workspace_id, "sir-demo")

    def test_worker_start_failure_restores_idle_ui_state(self):
        window = self._window()
        component = next(
            item
            for section in window.workspace_view_model.sections
            for item in section.components
            if item.component_id == "trajectory"
        )
        action = window._simulation_actions[component.component_id]
        window._confirmation_handler = lambda _prompt: True

        with patch(
            "scripts.scientific_workspace_qt._SimulationThread.start",
            side_effect=RuntimeError("simulated QThread start failure"),
        ):
            window._request_and_run_simulation(component, action)

        self.assertFalse(window.simulation_running)
        self.assertEqual(window.simulation_results, {})
        self.assertNotIn("en ejecución", window.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main()
