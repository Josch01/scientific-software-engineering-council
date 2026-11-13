from __future__ import annotations

import os
import hashlib
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    QtCore = None
    QtWidgets = None

from scripts.scientific_workspace_view import ComponentView, SectionView, WorkspaceViewModel
from scripts.scientific_control_center_qt import workspace_section_index


def _component(component_id: str, component_type: str) -> ComponentView:
    return ComponentView(component_id, component_type, component_id, "READY", "")


def _view_model() -> WorkspaceViewModel:
    return WorkspaceViewModel(
        workspace_id="control-center-test",
        title="Control Center Test",
        sections=(
            SectionView("setup", "Setup", (_component("equations", "equation_view"),)),
            SectionView("experiment", "Experiment", (
                _component("observations", "observation_table"),
                _component("simulation", "simulation_plot"),
            )),
            SectionView("source", "Source", (_component("code", "code_view"),)),
            SectionView("results", "Results", (
                _component("fit", "fit_summary"),
                _component("sensitivity", "sensitivity_plot"),
                _component("residuals", "residual_plot"),
            )),
        ),
        resources=(),
    )


class WorkspaceSectionRoutingTests(unittest.TestCase):
    def test_routes_to_existing_experiment_code_and_result_sections(self):
        model = _view_model()

        self.assertEqual(workspace_section_index(model, "experiments"), 1)
        self.assertEqual(workspace_section_index(model, "code"), 2)
        self.assertEqual(workspace_section_index(model, "results"), 3)

    def test_missing_category_is_explicit_and_unknown_route_is_rejected(self):
        model = WorkspaceViewModel("empty", "Empty", (), ())

        self.assertIsNone(workspace_section_index(model, "results"))
        with self.assertRaisesRegex(ValueError, "unknown workspace category"):
            workspace_section_index(model, "agents")


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class WorkspaceAuditSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_completed_workspace_audit_is_signaled_as_unapproved(self):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        class AuditWorkerSignalSource(QtCore.QObject):
            finished = QtCore.Signal()

        window = ScientificWorkspaceWindow()
        self.addCleanup(window.close)
        worker = AuditWorkerSignalSource()
        window._audit_worker = worker
        window._audit_terminal = ("result", {
            "execution": "PROCESSES_COMPLETED_NOT_AUDITED",
            "release_status": "APPROVED",
            "scientific_validity": "VALID",
        })
        window._show_workspace_audit_result = lambda _report: None
        observed = []
        window.auditResultChanged.connect(observed.append)
        worker.finished.connect(window._on_workspace_audit_finished)

        worker.finished.emit()
        self.app.processEvents()

        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["execution"], "PROCESSES_COMPLETED_NOT_AUDITED")
        self.assertEqual(observed[0]["release_status"], "NOT_APPROVED")
        self.assertEqual(observed[0]["scientific_validity"], "NOT_CERTIFIED")


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class ControlCenterShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.examples = Path(__file__).resolve().parents[1] / "examples" / "sir_analysis_workspace_demo"
        cls.profiled_examples = (
            Path(__file__).resolve().parents[1]
            / "examples" / "sir_profiled_analysis_workspace_demo"
        )
        cls.analysis_examples = (
            Path(__file__).resolve().parents[1]
            / "examples" / "sir_analysis_input_demo"
        )

    def _window(self):
        from scripts.scientific_control_center_qt import ControlCenterWindow

        window = ControlCenterWindow()
        self.addCleanup(window.close)
        return window

    def test_control_center_uses_charcoal_purple_theme(self):
        window = self._window()

        stylesheet = window.styleSheet().lower()
        self.assertIn("#202027", stylesheet)
        self.assertIn("#aa8bf2", stylesheet)
        self.assertNotIn("#f2f5f7", stylesheet)

    def test_embedded_workspace_uses_the_same_dark_theme(self):
        window = self._window()

        self.assertIn("#202027", window.workspace_window.styleSheet().lower())
        self.assertIn("#aa8bf2", window.workspace_window.styleSheet().lower())

    def test_route_transition_respects_reduced_motion_preference(self):
        window = self._window()

        with patch.dict(os.environ, {"SSEC_REDUCED_MOTION": "1"}):
            window.navigate("agents")

        self.assertIsNone(window._page_transition_animation)

    def _wait_for_sir_analysis(self, window, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while window.analysis_running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertFalse(window.analysis_running, "analysis worker did not finish")

    def _mock_sir_analysis_confirmation(self, window, captured, answer):
        create_dialog = window._create_sir_analysis_confirmation

        def capture(preview):
            dialog = create_dialog(preview)
            captured["text"] = dialog.text()
            captured["default"] = dialog.defaultButton().text()
            return dialog

        return (
            patch.object(window, "_create_sir_analysis_confirmation", side_effect=capture),
            patch.object(QtWidgets.QMessageBox, "exec", return_value=answer),
        )

    def test_existing_workspace_is_embedded_and_shares_loaded_project(self):
        window = self._window()
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        self.assertFalse(window.workspace_audit_button.isEnabled())
        self.assertIsInstance(window.agent_supervisor, AgentSupervisorPage)

        model = window.load_project(self.examples, "workspace.json")

        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertEqual(window.workspace_window.workspace_view_model, model)
        self.assertIsNotNone(window.workspace_window.parentWidget())
        self.assertFalse(window.workspace_window.isWindow())
        self.assertEqual(window.agent_supervisor.project_root, self.examples.resolve())
        self.assertIs(window.pages["agents"], window.agent_supervisor)
        self.assertEqual(window.active_project_label.text(), self.examples.name)
        self.assertEqual(window.active_project_label.toolTip(), str(self.examples.resolve()))
        self.assertTrue(window.workspace_audit_button.isEnabled())

    def test_profiled_sir_results_open_in_integrated_center_with_shared_supervisor_project(self):
        root = self.profiled_examples
        window = self._window()
        model = window.load_project(root, "workspace.json")
        window.navigate("agents")
        self.app.processEvents()
        self.assertIs(window.page_stack.currentWidget(), window.agent_supervisor)
        self.assertEqual(window.agent_supervisor.project_root, root.resolve())

        window.navigate("results")
        window.show()
        self.app.processEvents()
        fit_table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
        self.assertIsNotNone(fit_table)
        self.assertEqual(fit_table.item(0, 0).text(), "beta_knot_1")
        self.assertEqual(fit_table.item(0, 5).text(), "1/day")
        self.assertEqual(window.current_project_root, root.resolve())
        self.assertEqual(window.workspace_window.workspace_view_model, model)
        self.assertTrue(window.workspace_audit_button.isEnabled())
        self.assertEqual(
            window.workspace_value.text().split(" · ")[-1], model.verification_status
        )

    def test_generated_analysis_workspace_renders_calculated_results_in_integrated_center(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        source = Path(__file__).resolve().parents[1] / "examples" / "sir_analysis_input_demo"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "analysis"
            build_analysis_workspace(source, "workspace.json", output)
            window = self._window()
            model = window.load_project(output, "workspace.json")
            window.navigate("results")
            window.show()
            self.app.processEvents()

            fit_table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
            residual_table = window.findChild(QtWidgets.QTableWidget, "fit-residuals-table")
            self.assertIsNotNone(fit_table)
            self.assertEqual(fit_table.item(0, 0).text(), "beta_knot_1")
            self.assertEqual(fit_table.item(0, 5).text(), "1/day")
            self.assertIsNotNone(residual_table)
            self.assertGreater(residual_table.rowCount(), 0)
            self.assertEqual(window.current_project_root, output.resolve())
            self.assertEqual(window.agent_supervisor.project_root, output.resolve())
            self.assertEqual(window.workspace_window.workspace_view_model, model)

    def test_qt_sir_analysis_can_be_rejected_without_output_or_workspace_change(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            model = window.load_project(root, "workspace.json")
            confirmation_details = {}
            confirm_patch, exec_patch = self._mock_sir_analysis_confirmation(
                window, confirmation_details, QtWidgets.QMessageBox.StandardButton.No
            )
            with confirm_patch, exec_patch:
                window.sir_analysis_button.click()

            self.assertEqual(window.current_manifest_relative_path, "workspace.json")
            self.assertEqual(window.workspace_window.workspace_view_model, model)
            self.assertFalse(window.analysis_running)
            self.assertFalse((root / "generated").exists())
            self.assertIn("beta_knot_1", confirmation_details["text"])
            self.assertIn("model/model.json", confirmation_details["text"])
            self.assertEqual(confirmation_details["default"], "No ejecutar")

    def test_qt_sir_analysis_acceptance_runs_real_builder_off_gui_thread_and_loads_views(self):
        from scripts.build_sir_analysis_demo import build_analysis_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            original = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            window = self._window()
            window.show()
            window.load_project(root, "workspace.json")
            observed = {}
            confirmation_details = {}

            def run_real_builder(*args, **kwargs):
                observed["thread"] = threading.current_thread()
                return build_analysis_workspace(*args, **kwargs)

            confirm_patch, exec_patch = self._mock_sir_analysis_confirmation(
                window, confirmation_details, QtWidgets.QMessageBox.StandardButton.Yes
            )

            with patch(
                "scripts.scientific_control_center_qt.build_analysis_workspace",
                side_effect=run_real_builder,
            ), confirm_patch, exec_patch:
                window.sir_analysis_button.click()
                self._wait_for_sir_analysis(window)

            self.assertIsNot(observed["thread"], threading.main_thread())
            self.assertEqual(window.current_project_root, root.resolve())
            self.assertEqual(window.agent_supervisor.project_root, root.resolve())
            self.assertTrue(window.current_manifest_relative_path.startswith(
                "generated/sir-analysis/"
            ))
            self.assertIn("dS/dt", confirmation_details["text"])
            self.assertIn("beta_knot_1", confirmation_details["text"])
            self.assertIn("NOT_CALCULATED", confirmation_details["text"])
            self.assertIn("no admite cancelación segura", confirmation_details["text"])
            self.assertEqual(confirmation_details["default"], "No ejecutar")
            self.assertIn("NOT_ASSESSED", window.sir_analysis_status.text())
            self.assertIn("NOT_RUN", window.sir_analysis_status.text())
            self.assertTrue((root / "generated" / "sir-analysis-runs").is_dir())
            log_path = next((root / "generated" / "sir-analysis-runs").glob("*.json"))
            run_log = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(run_log["status"], "SUCCEEDED")
            self.assertEqual(run_log["real_user_sir"], "NOT_RUN")
            self.assertEqual(run_log["uncertainty"], "NOT_CALCULATED")
            self.assertEqual(
                run_log["source_workspace_manifest_sha256"],
                hashlib.sha256((root / "workspace.json").read_bytes()).hexdigest(),
            )
            result_manifest_bytes = (root / window.current_manifest_relative_path).read_bytes()
            self.assertEqual(
                run_log["result_workspace_manifest_sha256"],
                hashlib.sha256(result_manifest_bytes).hexdigest(),
            )
            generated_resources = {
                resource.resource_id: resource
                for resource in window.workspace_window._loaded_workspace.resources
            }
            for resource_id in ("model", "observations", "analysis-config"):
                self.assertEqual(
                    generated_resources[resource_id].content,
                    original[generated_resources[resource_id].path.split("/", 3)[-1]],
                )
            self.assertEqual(
                {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob("*") if path.is_file()
                 and not path.is_relative_to(root / "generated")},
                original,
            )

            window.navigate("results")
            self.app.processEvents()
            fit_table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
            self.assertIsNotNone(fit_table)
            self.assertEqual(fit_table.item(0, 0).text(), "beta_knot_1")
            self.assertIsNotNone(window.findChild(QtWidgets.QWidget, "plot-sensitivity-view-sensitivity-0"))
            self.assertIsNotNone(window.findChild(QtWidgets.QWidget, "plot-residual-view-residual-0"))

    def test_qt_sir_analysis_failure_is_logged_without_loading_stale_results(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            source_model = window.load_project(root, "workspace.json")
            confirmation_details = {}
            confirm_patch, exec_patch = self._mock_sir_analysis_confirmation(
                window, confirmation_details, QtWidgets.QMessageBox.StandardButton.Yes
            )

            with patch(
                "scripts.scientific_control_center_qt.build_analysis_workspace",
                side_effect=RuntimeError("deterministic test failure"),
            ), confirm_patch, exec_patch:
                window.sir_analysis_button.click()
                self._wait_for_sir_analysis(window)

            self.assertEqual(window.current_manifest_relative_path, "workspace.json")
            self.assertEqual(window.workspace_window.workspace_view_model, source_model)
            self.assertIn("Falló", window.sir_analysis_status.text())
            logs = list((root / "generated" / "sir-analysis-runs").glob("*.json"))
            self.assertEqual(len(logs), 1)
            run_log = json.loads(logs[0].read_text(encoding="utf-8"))
            self.assertEqual(run_log["status"], "FAILED")
            self.assertIn("deterministic test failure", run_log["error"])

    def _create_sir_analysis_history(self, root, run_id):
        from scripts.build_sir_analysis_demo import build_analysis_workspace
        from scripts.scientific_control_center_qt import _write_analysis_run_log

        output = root / "generated" / "sir-analysis" / run_id
        result = build_analysis_workspace(root, "workspace.json", output)
        result_manifest = result["workspace_path"]
        manifest_bytes = (root / result_manifest).read_bytes()
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at_utc": "2026-11-13T12:00:00.000Z",
            "source_workspace_manifest": "workspace.json",
            "source_workspace_manifest_sha256": hashlib.sha256(
                (root / "workspace.json").read_bytes()
            ).hexdigest(),
            "output_directory": output.relative_to(root).as_posix(),
            "status": "SUCCEEDED",
            "finished_at_utc": "2026-11-13T12:00:01.000Z",
            "duration_seconds": 1.0,
            "result_workspace_manifest": result_manifest,
            "result_workspace_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "scientific_validity": "NOT_ASSESSED",
            "identifiability": "NOT_ASSESSED",
            "uncertainty": "NOT_CALCULATED",
            "real_user_sir": "NOT_RUN",
        }
        _write_analysis_run_log(root, run_id, record)
        return result_manifest

    def test_qt_sir_analysis_history_loads_verified_result_and_marks_it_historical(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            window.load_project(root, "workspace.json")
            run_id = "11111111111141118111111111111111"
            result_manifest = self._create_sir_analysis_history(root, run_id)

            opened = window.open_sir_analysis_history_run(run_id)

            self.assertTrue(opened)
            self.assertEqual(window.current_manifest_relative_path, result_manifest)
            self.assertIn("histórico", window.sir_analysis_status.text().casefold())
            self.assertIn(run_id, window.sir_analysis_status.text())
            self.assertIsNotNone(window.findChild(QtWidgets.QPushButton, "sirAnalysisHistoryButton"))

    def test_qt_sir_analysis_history_dialog_only_enables_verified_success_rows(self):
        from scripts.scientific_control_center_qt import _write_analysis_run_log
        from scripts.scientific_run_history import list_sir_analysis_runs

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            window.load_project(root, "workspace.json")
            success_id = "11111111111141118111111111111111"
            self._create_sir_analysis_history(root, success_id)
            failed_id = "33333333333343338333333333333333"
            _write_analysis_run_log(
                root,
                failed_id,
                {
                    "schema_version": 1,
                    "run_id": failed_id,
                    "started_at_utc": "2026-11-12T12:00:00.000Z",
                    "source_workspace_manifest": "workspace.json",
                    "source_workspace_manifest_sha256": "f" * 64,
                    "output_directory": f"generated/sir-analysis/{failed_id}",
                    "status": "FAILED",
                    "finished_at_utc": "2026-11-12T12:00:01.000Z",
                    "duration_seconds": 1.0,
                    "error": "fixture failure",
                },
            )
            records = list_sir_analysis_runs(root)
            dialog = window._create_sir_analysis_history_dialog(records)
            self.addCleanup(dialog.close)
            table = dialog.findChild(QtWidgets.QTableWidget, "sirAnalysisHistoryTable")
            self.assertEqual(table.rowCount(), 2)

            table.selectRow(0)
            self.app.processEvents()
            self.assertEqual(records[0].run_id, success_id)
            self.assertTrue(dialog.history_open_button.isEnabled())
            table.selectRow(1)
            self.app.processEvents()
            self.assertEqual(records[1].run_id, failed_id)
            self.assertFalse(dialog.history_open_button.isEnabled())

    def test_qt_sir_analysis_history_digest_failure_preserves_current_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            original_model = window.load_project(root, "workspace.json")
            original_path = window.current_manifest_relative_path
            run_id = "22222222222242228222222222222222"
            result_manifest = self._create_sir_analysis_history(root, run_id)
            result_path = root / result_manifest
            result_path.write_bytes(result_path.read_bytes() + b" ")

            opened = window.open_sir_analysis_history_run(run_id)

            self.assertFalse(opened)
            self.assertEqual(window.current_manifest_relative_path, original_path)
            self.assertIs(window.workspace_window.workspace_view_model, original_model)
            self.assertIn("no se abrió", window.sir_analysis_status.text().casefold())

    def test_qt_sir_analysis_prevents_duplicate_and_project_switch_while_running(self):
        started = threading.Event()
        release = threading.Event()

        def blocking_builder(*_args, **_kwargs):
            started.set()
            release.wait(timeout=5)
            raise RuntimeError("test release")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "project"
            shutil.copytree(self.analysis_examples, root)
            window = self._window()
            window.load_project(root, "workspace.json")
            confirmation_details = {}
            confirm_patch, exec_patch = self._mock_sir_analysis_confirmation(
                window, confirmation_details, QtWidgets.QMessageBox.StandardButton.Yes
            )

            with patch(
                "scripts.scientific_control_center_qt.build_analysis_workspace",
                side_effect=blocking_builder,
            ), confirm_patch, exec_patch:
                window.sir_analysis_button.click()
                deadline = time.monotonic() + 2
                while not started.is_set() and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.005)
                self.assertTrue(started.is_set())
                self.assertFalse(window.sir_analysis_button.isEnabled())
                with self.assertRaisesRegex(ValueError, "analysis is running"):
                    window.load_project(root, "workspace.json")
                window.sir_analysis_button.click()
                self.assertTrue(window.analysis_running)
                release.set()
                self._wait_for_sir_analysis(window)

    def test_profiled_sir_results_can_request_workspace_audit_in_same_center(self):
        root = self.profiled_examples
        window = self._window()
        model = window.load_project(root, "workspace.json")
        window.navigate("results")
        window.show()
        self.app.processEvents()
        fit_table = window.findChild(QtWidgets.QTableWidget, "fit-parameters-table")
        self.assertIsNotNone(fit_table)
        self.assertEqual(window.workspace_window.workspace_view_model, model)

        observed = {}

        def fake_audit(project_root, workspace, selected_ids, _config, **kwargs):
            observed["root"] = Path(project_root).resolve()
            observed["workspace_id"] = workspace.summary.workspace_id
            observed["selected_ids"] = tuple(selected_ids)
            observed["cancel_file"] = Path(kwargs["cancel_file"])
            return {
                "execution": "PROCESSES_COMPLETED_NOT_AUDITED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_CERTIFIED",
                "workspace_audit": {"execution": "PROCESSES_COMPLETED_NOT_AUDITED"},
                "results": [{"agent": "local-test-reviewer", "status": "completed"}],
            }

        with patch(
            "scripts.scientific_workspace_qt.run_workspace_audit", side_effect=fake_audit
        ) as audit_service, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirmations:
            window.navigate("audits")
            window.workspace_audit_button.click()
            self.app.processEvents()
            dialog = window.workspace_window.findChild(
                QtWidgets.QDialog, "workspaceAuditRequestDialog"
            )
            self.assertIsNotNone(dialog)
            table = dialog.findChild(QtWidgets.QTableWidget, "workspaceAuditResourceTable")
            self.assertIsNotNone(table)
            model_row = next(
                row for row in range(table.rowCount()) if table.item(row, 0).text() == "model"
            )
            table.selectRow(model_row)
            dispatch = dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton")
            self.assertIsNotNone(dispatch)
            dispatch.click()

            deadline = time.monotonic() + 8.0
            while "NOT_APPROVED" not in window.audit_result_text.toPlainText() and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)

        audit_service.assert_called_once()
        confirmations.assert_called_once()
        self.assertIn("puede consumir cuota", confirmations.call_args.args[2])
        self.assertIn("no aprobará cambios", confirmations.call_args.args[2])
        self.assertEqual(observed["root"], root.resolve())
        self.assertEqual(observed["workspace_id"], model.workspace_id)
        self.assertEqual(observed["selected_ids"], ("model",))
        self.assertFalse(observed["cancel_file"].parent.exists())
        self.assertIn("PROCESSES_COMPLETED_NOT_AUDITED", window.audit_result_text.toPlainText())
        self.assertIn("NOT_APPROVED", window.audit_result_text.toPlainText())
        self.assertIn("NOT_CERTIFIED", window.audit_result_text.toPlainText())

    def test_failed_load_preserves_the_current_project_and_workspace(self):
        window = self._window()
        window.load_project(self.examples, "workspace.json")
        previous_model = window.workspace_window.workspace_view_model

        with self.assertRaises((OSError, ValueError)):
            window.load_project(self.examples, "missing.json")

        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertIs(window.workspace_window.workspace_view_model, previous_model)

    def test_project_switch_is_rejected_before_loading_while_agent_cli_runs(self):
        from unittest.mock import PropertyMock, patch

        window = self._window()
        window.load_project(self.examples, "workspace.json")
        previous_model = window.workspace_window.workspace_view_model
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            type(window.agent_supervisor), "process_running", new_callable=PropertyMock,
            return_value=True,
        ):
            with self.assertRaisesRegex(ValueError, "espera a que termine"):
                window.load_project(temporary, "missing.json")

        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertIs(window.workspace_window.workspace_view_model, previous_model)

    def test_canceling_project_dialog_preserves_loaded_project(self):
        from unittest.mock import patch
        from scripts.scientific_control_center_qt import ControlCenterWindow

        window = self._window()
        window.load_project(self.examples, "workspace.json")
        previous_model = window.workspace_window.workspace_view_model

        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
            window.open_project_dialog()
        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertIs(window.workspace_window.workspace_view_model, previous_model)

        with patch.object(
            QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(self.examples)
        ), patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")):
            window.open_project_dialog()
        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertIs(window.workspace_window.workspace_view_model, previous_model)

    def test_navigation_uses_workspace_sections_and_explicit_empty_state(self):
        window = self._window()
        window.navigate("results")
        self.assertIn("workspace", window.workspace_empty_label.text().lower())

        window.load_project(self.examples, "workspace.json")
        section_index = workspace_section_index(window.workspace_window.workspace_view_model, "results")
        self.assertIsNotNone(section_index)
        window.navigate("results")
        self.assertEqual(window.current_route, "results")
        self.assertEqual(window.workspace_window.tabs.currentIndex(), section_index)

    def test_all_six_control_center_destinations_are_available(self):
        window = self._window()

        routes = tuple(
            window.navigation.item(index).data(QtCore.Qt.ItemDataRole.UserRole)
            for index in range(window.navigation.count())
        )

        self.assertEqual(
            routes,
            ("projects", "agents", "experiments", "audits", "code", "results"),
        )
        window.navigate("audits")
        self.assertIs(window.page_stack.currentWidget(), window.audit_page)


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class AgentSupervisorPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = Path(__file__).resolve().parents[1]
        cls.task = cls.repository / "examples" / "seir_desktop_audit.json"

    def _page(self, root, *, confirmation_handler):
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        page = AgentSupervisorPage(confirmation_handler=confirmation_handler)
        self.addCleanup(page.close)
        page.set_project_root(root)
        page.task_path_edit.setText(str(self.task))
        return page

    def _write_runner(self, root: Path, *, wait_for_cancel: bool) -> Path:
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        source = """
            import json
            from pathlib import Path
            import sys
            import time

            cancel_file = Path(sys.argv[1])

            def emit(execution, status, completed):
                event = {
                    "schema_version": 1, "run_id": "local-fixture", "task_id": "fixture-audit",
                    "execution": execution, "completed": completed, "total": 1,
                    "release_status": "NOT_APPROVED",
                    "roles": [{"agent": "test-auditor", "role": "software_auditor",
                               "provider": "gemini", "status": status}],
                }
                print("SSEC_PROGRESS " + json.dumps(event), flush=True)

            emit("STARTED", "RUNNING", 0)
            if WAIT_FOR_CANCEL:
                deadline = time.monotonic() + 4
                while not cancel_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
            if cancel_file.exists():
                emit("INTERRUPTED", "CANCELLED", 1)
            else:
                emit("PROCESSES_COMPLETED_NOT_AUDITED", "EXIT_ZERO_UNREVIEWED", 1)
        """.replace("WAIT_FOR_CANCEL", repr(wait_for_cancel))
        runner = root / "local_supervisor_runner.py"
        runner.write_text(textwrap.dedent(source), encoding="utf-8")

        class LocalSupervisorPage(AgentSupervisorPage):
            def _runner_command(self, _task_path, _project_root, _config_path, cancel_file):
                return sys.executable, [str(runner), str(cancel_file)]

        self._local_supervisor_page_type = LocalSupervisorPage
        return runner

    def _wait_for_process(self, page, timeout_seconds=6):
        deadline = time.monotonic() + timeout_seconds
        while page.process_running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(page.process_running, "local test runner did not finish")

    def _wait_for_started_runner(self, page, timeout_seconds=3):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if page.process_running and page.cancel_button.isEnabled():
                return
            time.sleep(0.01)
        self.fail("local test runner did not enable cancellation after starting")

    def test_preview_uses_existing_agent_planner_without_writes(self):
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = self._page(root, confirmation_handler=lambda *_args: False)

            preview = page.preview_plan()

            self.assertGreater(preview["agent_count"], 0)
            self.assertFalse(preview["applied"])
            self.assertFalse((root / ".ssec").exists())

    def test_invalid_saved_policy_blocks_project_context(self):
        from scripts.configuration import DEFAULT_CONFIG
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / ".ssec" / "config.json"
            config_path.parent.mkdir()
            invalid_policy = json.loads(json.dumps(DEFAULT_CONFIG))
            invalid_policy["max_parallel_agents"] = 13
            config_path.write_text(json.dumps(invalid_policy), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "max_parallel_agents"):
                AgentSupervisorPage.project_context(root)

    def test_declined_audit_creates_no_run_files_or_saved_config(self):
        confirmations = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = self._page(
                root,
                confirmation_handler=lambda *args: confirmations.append(args) or False,
            )

            started = page.start_audit()

            self.assertFalse(started)
            self.assertEqual(len(confirmations), 1)
            self.assertIn(".ssec", confirmations[0][1])
            self.assertIn("config.json", confirmations[0][1])
            self.assertFalse(page.process_running)
            self.assertFalse((root / ".ssec").exists())
            self.assertIn("NO APROBADA", page.status_label.text())

    def test_declined_policy_save_writes_no_configuration(self):
        confirmations = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = self._page(
                root,
                confirmation_handler=lambda *args: confirmations.append(args) or False,
            )

            saved = page.save_policy()

            self.assertIsNone(saved)
            self.assertEqual(len(confirmations), 1)
            self.assertFalse((root / ".ssec").exists())
            self.assertIn("NO APROBADA", page.status_label.text())

    def test_confirmed_policy_save_persists_only_after_dialog(self):
        confirmations = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = self._page(
                root,
                confirmation_handler=lambda *args: confirmations.append(args) or True,
            )

            saved = page.save_policy()

            self.assertEqual(saved, root / ".ssec" / "config.json")
            self.assertTrue(saved.is_file())
            self.assertEqual(len(confirmations), 1)
            self.assertIn(".ssec", confirmations[0][1])
            self.assertIn("config.json", confirmations[0][1])

    def test_exit_zero_with_local_fake_runner_remains_unapproved(self):
        confirmations = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_runner(root, wait_for_cancel=False)
            PageType = self._local_supervisor_page_type
            page = PageType(
                confirmation_handler=lambda *args: confirmations.append(args) or True
            )
            self.addCleanup(page.close)
            page.set_project_root(root)
            page.task_path_edit.setText(str(self.task))

            self.assertTrue(page.start_audit())
            self.assertEqual(len(confirmations), 1)
            self.assertIn(".ssec", confirmations[0][1])
            self.assertIn("config.json", confirmations[0][1])
            self.assertIn("consumir cuota", confirmations[0][1])
            self._wait_for_process(page)

            self.assertIn("NO APROBADA", page.status_label.text())
            self.assertEqual(page.release_status, "NOT_APPROVED")
            self.assertIn("PROCESSES_COMPLETED_NOT_AUDITED", page.status_label.text())
            self.assertEqual(page.progress_table.rowCount(), 1)
            self.assertEqual(page.progress_bar.value(), 1)

    def test_cancel_file_is_requested_and_terminal_state_stays_unapproved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_runner(root, wait_for_cancel=True)
            PageType = self._local_supervisor_page_type
            page = PageType(confirmation_handler=lambda *_args: True)
            self.addCleanup(page.close)
            page.set_project_root(root)
            page.task_path_edit.setText(str(self.task))

            self.assertTrue(page.start_audit())
            self._wait_for_started_runner(page)
            page.cancel_button.click()
            self._wait_for_process(page)

            self.assertTrue(page.cancel_file_was_requested)
            self.assertEqual(page.release_status, "NOT_APPROVED")
            self.assertIn("INTERRUPTED", page.status_label.text())
            self.assertIn("NO APROBADA", page.status_label.text())

    def test_failed_to_start_stays_unapproved_and_reports_launch_failure(self):
        from scripts.scientific_control_center_qt import AgentSupervisorPage

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = self._write_runner(root, wait_for_cancel=False)

            class ReusableProcessPage(AgentSupervisorPage):
                fail_next_start = True

                def _runner_command(self, _task_path, _project_root, _config_path, cancel_file):
                    if self.fail_next_start:
                        return str(root / "missing-runner"), []
                    return sys.executable, [str(runner), str(cancel_file)]

            page = ReusableProcessPage(confirmation_handler=lambda *_args: True)
            self.addCleanup(page.close)
            page.set_project_root(root)
            page.task_path_edit.setText(str(self.task))
            self.assertTrue(page.start_audit())
            process = page._process

            deadline = time.monotonic() + 3
            while "LAUNCH_FAILED" not in page.status_label.text() and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)

            self.assertIn("LAUNCH_FAILED", page.status_label.text())
            self.assertIn("NO APROBADA", page.status_label.text())
            self.assertEqual(page.release_status, "NOT_APPROVED")
            page.fail_next_start = False
            self.assertTrue(page.start_audit())
            self.assertIs(page._process, process, "the supervisor should safely reuse its stopped QProcess")
            self._wait_for_process(page)
            self.assertEqual(page.release_status, "NOT_APPROVED")


if __name__ == "__main__":
    unittest.main()
