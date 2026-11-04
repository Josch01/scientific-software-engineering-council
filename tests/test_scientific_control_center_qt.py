from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import unittest

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

    def _window(self):
        from scripts.scientific_control_center_qt import ControlCenterWindow

        window = ControlCenterWindow()
        self.addCleanup(window.close)
        return window

    def test_existing_workspace_is_embedded_and_shares_loaded_project(self):
        window = self._window()
        self.assertFalse(window.workspace_audit_button.isEnabled())

        model = window.load_project(self.examples, "workspace.json")

        self.assertEqual(window.current_project_root, self.examples.resolve())
        self.assertEqual(window.workspace_window.workspace_view_model, model)
        self.assertIsNotNone(window.workspace_window.parentWidget())
        self.assertFalse(window.workspace_window.isWindow())
        self.assertIn(str(self.examples.resolve()), window.active_project_label.text())
        self.assertTrue(window.workspace_audit_button.isEnabled())

    def test_failed_load_preserves_the_current_project_and_workspace(self):
        window = self._window()
        window.load_project(self.examples, "workspace.json")
        previous_model = window.workspace_window.workspace_view_model

        with self.assertRaises((OSError, ValueError)):
            window.load_project(self.examples, "missing.json")

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


if __name__ == "__main__":
    unittest.main()
