from __future__ import annotations

import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    QtCore = None
    QtWidgets = None


def _reconstruction_payload() -> bytes:
    labels = [f"2021-SE{week}" for week in range(44, 53)]
    labels.extend(f"2022-SE{week:02d}" for week in range(1, 48))
    return json.dumps({
        "target_window": {
            "n_weeks": 56,
            "first_week": labels[0],
            "last_week": labels[-1],
        },
        "week_by_week_comparison": [
            {
                "week": label,
                "DGE_sunday_saturday": 999,
                "DGE_monday_sunday_candidate": 100 + index,
            }
            for index, label in enumerate(labels)
        ],
    }).encode("utf-8")


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class ThesisSirQtPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from scripts.thesis_sir_qt import ThesisSIRPage

        self.page = ThesisSIRPage()
        self.addCleanup(self._dispose_page)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "reconstruction.json"
        self.source.write_bytes(_reconstruction_payload())

    def _dispose_page(self):
        page = self.page
        page.close()
        page.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )
        self.app.processEvents()

    def _set_valid_parameters(self, *, ascertainment="0.1"):
        page = self.page
        page.harmonic_count.setCurrentIndex(page.harmonic_count.findData(1))
        for name, value in {
            "d0": "0.0",
            "gamma": "0.1",
            "log10_initial_infectious": "3.0",
            "susceptible_fraction": "0.999",
            "ascertainment_fraction": ascertainment,
        }.items():
            page.parameter_fields[name].setText(value)
        page.delay_days.setCurrentIndex(page.delay_days.findData(4.3))
        for column, value in enumerate(("0.1", "0.0", "0.5")):
            page.harmonic_table.item(0, column).setText(value)

    def _run_synthetic(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters()
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()

    def _wait_for_run(self, timeout: float = 10.0):
        deadline = time.monotonic() + timeout
        while self.page.run_in_progress and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertFalse(self.page.run_in_progress, "SIR worker did not finish")

    def test_workspace_has_distinct_setup_and_results_panels(self):
        splitter = self.page.findChild(QtWidgets.QSplitter, "thesisSirWorkspaceSplitter")

        self.assertIsNotNone(splitter)
        self.assertEqual(splitter.count(), 2)
        self.assertIsNotNone(self.page.findChild(QtWidgets.QLabel, "thesisSirPanelTitle"))
        self.assertIsNotNone(self.page.findChild(QtWidgets.QLabel, "thesisSirEquationSummary"))
        self.assertGreaterEqual(self.page.load_data_button.minimumHeight(), 36)
        self.assertGreaterEqual(self.page.run_button.minimumHeight(), 36)

    def test_data_import_keeps_digest_and_full_path_out_of_primary_status(self):
        self.page.load_data_file(self.source)

        self.assertEqual(self.page.data_status.text(), "Datos importados · 56 semanas · 7,140 observaciones")
        self.assertEqual(self.page.data_series_label.text(), "Serie · DGE_monday_sunday_candidate")
        self.assertIn(self.page.observations.source_sha256, self.page.data_digest_label.text())
        self.assertEqual(self.page.data_source_label.toolTip(), str(self.source.resolve()))
        self.assertNotIn(str(self.source.resolve()), self.page.data_status.text())

    def test_import_displays_only_the_selected_56_week_series_read_only(self):
        original = self.source.read_bytes()

        self.page.load_data_file(self.source)

        self.assertEqual(len(self.page.observations.counts), 56)
        self.assertEqual(self.page.observations.series_id, "DGE_monday_sunday_candidate")
        self.assertEqual(self.page.observations.counts[:2], (100, 101))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertIn(self.page.observations.source_sha256, self.page.data_digest_label.text())
        self.assertIsNotNone(self.page.findChild(QtWidgets.QWidget, "thesisSirObservedChart"))

    def test_oversized_import_clears_prior_data_and_cannot_leave_a_stale_chart(self):
        from scripts.thesis_sir_data import MAX_RECONSTRUCTION_BYTES

        self.page.load_data_file(self.source)
        oversized = Path(self.temp.name) / "oversized.json"
        oversized.write_bytes(b"{" + b" " * MAX_RECONSTRUCTION_BYTES + b"}")

        with self.assertRaisesRegex(ValueError, "at most 1 MiB"):
            self.page.load_data_file(oversized)

        self.assertIsNone(self.page.observations)
        self.assertEqual(self.page.state, "EMPTY")
        self.assertFalse(self.page.run_button.isEnabled())
        self.assertIs(self.page.content_stack.currentWidget(), self.page.empty_state)

    def test_missing_parameters_do_not_prompt_or_start_a_worker(self):
        self.page.load_data_file(self.source)

        with patch.object(QtWidgets.QMessageBox, "question") as confirm:
            self.page.start_simulation()

        confirm.assert_not_called()
        self.assertFalse(self.page.run_in_progress)
        self.assertIsNone(self.page.result_payload)
        self.assertIn("armónicos", self.page.status_label.text())

    def test_rejecting_human_confirmation_does_not_start_the_model(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters()

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as confirm:
            self.page.start_simulation()

        confirm.assert_called_once()
        self.assertFalse(self.page.run_in_progress)
        self.assertIsNone(self.page.result_payload)
        self.assertEqual(self.page.state, "READY")

    def test_user_can_reduce_rk4_step_for_valid_high_transmission_parameters(self):
        self.page.load_data_file(self.source)
        page = self.page
        self.assertEqual(page.max_step_combo.currentData(), 0.01)
        page.harmonic_count.setCurrentIndex(page.harmonic_count.findData(1))
        for name, value in {
            "d0": "2.0",
            "gamma": "0.05",
            "log10_initial_infectious": "2.0",
            "susceptible_fraction": "0.999",
            "ascertainment_fraction": "0.5",
        }.items():
            page.parameter_fields[name].setText(value)
        page.harmonic_table.item(0, 0).setText("2.0")
        page.harmonic_table.item(0, 1).setText("2.0")
        page.harmonic_table.item(0, 2).setText("2.2")
        page.delay_days.setCurrentIndex(page.delay_days.findData(0.0))
        page.max_step_combo.setCurrentIndex(page.max_step_combo.findData(0.01))

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirm:
            page.start_simulation()
            self._wait_for_run()

        self.assertIn("Δt=0.01 semanas", confirm.call_args.args[2])
        self.assertEqual(page.state, "COMPUTED")
        self.assertAlmostEqual(
            page.result_payload["integrator"]["max_step_week"], 0.01
        )
        page.max_step_combo.setCurrentIndex(page.max_step_combo.findData(0.02))
        self.assertIsNone(page.result_payload)
        self.assertEqual(page.state, "READY")

    def test_audit_action_requires_a_current_computed_result(self):
        self.assertFalse(self.page.audit_button.isEnabled())
        self.page.load_data_file(self.source)
        self.assertFalse(self.page.audit_button.isEnabled())

        self._set_valid_parameters()
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()
        self.assertTrue(self.page.audit_button.isEnabled())

        self.page.parameter_fields["gamma"].setText("0.11")
        self.assertFalse(self.page.audit_button.isEnabled())

    def test_declining_audit_bundle_creates_nothing_then_approval_emits_verified_workspace(self):
        from scripts.scientific_workspace_loader import load_scientific_workspace

        self._run_synthetic()
        parent = Path(self.temp.name) / "audit-output"
        parent.mkdir()
        emitted = []
        self.page.audit_workspace_ready.connect(emitted.append)

        with patch.object(
            QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(parent)
        ), patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as confirmation:
            self.page.audit_button.click()

        confirmation.assert_called_once()
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(emitted, [])
        self.assertEqual(self.page.state, "COMPUTED")

        with patch.object(
            QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(parent)
        ), patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirmation:
            self.page.audit_button.click()

        confirmation.assert_called_once()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(len(list(parent.iterdir())), 1)
        workspace_root = Path(emitted[0])
        workspace = load_scientific_workspace(workspace_root, "workspace.json")
        self.assertEqual(len(workspace.resources), 5)
        self.assertIn("audit workspace preparado", self.page.status_label.text().lower())

    def test_approved_synthetic_run_uses_p25_engine_and_shows_calculated_results(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters()

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()

        self.assertEqual(self.page.state, "COMPUTED")
        self.assertEqual(
            self.page.result_payload["analysis_execution"],
            "COMPUTED_FROM_DECLARED_INPUTS",
        )
        self.assertEqual(self.page.result_payload["observations"]["series_id"],
                         "DGE_monday_sunday_candidate")
        self.assertEqual(self.page.result_payload["scientific_validity"], "NOT_ASSESSED")
        self.assertEqual(self.page.result_payload["identifiability"], "NOT_ASSESSED")
        self.assertEqual(self.page.result_payload["uncertainty"], "NOT_ASSESSED")
        self.assertIsNotNone(self.page.findChild(QtWidgets.QWidget, "thesisSirFitChart"))
        self.assertIsNotNone(self.page.findChild(QtWidgets.QWidget, "thesisSirCompartmentsChart"))
        tabs = self.page.findChild(QtWidgets.QTabWidget, "thesisSirChartTabs")
        self.assertIsNotNone(tabs)
        self.assertEqual(tabs.count(), 2)
        self.assertEqual(tabs.tabText(0), "Observado vs. predicho")
        self.assertEqual(tabs.tabText(1), "Estados del modelo")

    def test_changing_a_parameter_invalidates_the_previous_result(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters()
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()
        self.assertEqual(self.page.state, "COMPUTED")

        self.page.parameter_fields["gamma"].setText("0.11")

        self.assertEqual(self.page.state, "READY")
        self.assertIsNone(self.page.result_payload)
        self.assertFalse(self.page.save_button.isEnabled())
        self.assertIsNotNone(self.page.findChild(QtWidgets.QWidget, "thesisSirObservedChart"))

    def test_worker_failure_does_not_retain_or_display_a_success_result(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters(ascertainment="0.000001")

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()

        self.assertEqual(self.page.state, "FAILED")
        self.assertIsNone(self.page.result_payload)
        self.assertIn("ascertainment_fraction", self.page.status_label.text())

    def test_export_creates_a_new_result_and_refuses_to_overwrite_source(self):
        self.page.load_data_file(self.source)
        self._set_valid_parameters()
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.page.start_simulation()
            self._wait_for_run()
        original = self.source.read_bytes()

        with self.assertRaisesRegex(ValueError, "cannot overwrite the selected data source"):
            self.page.export_result_to(self.source)
        self.assertEqual(self.source.read_bytes(), original)

        destination = Path(self.temp.name) / "run-result.json"
        self.page.export_result_to(destination)
        saved = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(saved["observations"]["source_sha256"],
                         self.page.observations.source_sha256)
        self.assertEqual(saved["uncertainty"], "NOT_ASSESSED")
        self.assertEqual(self.source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
