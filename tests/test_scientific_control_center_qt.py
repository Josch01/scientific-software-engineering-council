from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


if __name__ == "__main__":
    unittest.main()
