"""Offscreen Qt tests for proposal consent, review, import, and approval."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    QtCore = None
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class QtWorkspaceProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.examples = Path(__file__).resolve().parents[1] / "examples"

    def _project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name in (
            "sir_scientific_workspace.json",
            "sir_model_demo.json",
            "sir_demo_result.json",
        ):
            shutil.copyfile(self.examples / name, root / name)
        return root

    def _window(self, root):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        window = ScientificWorkspaceWindow()
        window.load_workspace(root, "sir_scientific_workspace.json")
        window.show()
        self.app.processEvents()
        self.addCleanup(window.close)
        return window

    def _request_dialog(self, window, *, objective="Add an analysis view"):
        dialog = window._open_workspace_proposal_dialog()
        self.assertIsNotNone(dialog)
        resource_table = dialog.findChild(QtWidgets.QTableWidget, "workspaceProposalResourceTable")
        resource_table.clearSelection()
        resource_table.selectRow(0)
        objective_field = dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceProposalObjective")
        objective_field.setPlainText(objective)
        self.app.processEvents()
        return dialog

    def _wait_until(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return predicate()

    def _proposal_file(self, root, title="Proposed scientific workspace"):
        manifest = json.loads((root / "sir_scientific_workspace.json").read_text(encoding="utf-8"))
        manifest["title"] = title
        manifest["sections"][0]["title"] = "Proposed model section"
        (root / "proposal.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return root / "proposal.json"

    def _approve_visible_review(self, window, observed):
        dialog = window.findChild(QtWidgets.QDialog, "workspaceProposalReviewDialog")
        if dialog is None:
            return False
        diff = dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceProposalDiff")
        observed["diff"] = diff.toPlainText()
        button = dialog.findChild(QtWidgets.QPushButton, "approveWorkspaceProposalButton")
        if button is None:
            observed["error"] = "approval button missing"
            return False
        button.click()
        return True

    def test_declining_quota_confirmation_never_calls_generation(self):
        root = self._project()
        window = self._window(root)
        dialog = self._request_dialog(window)
        with patch("scripts.scientific_workspace_qt.generate_workspace_proposal") as generate, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as confirmation:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceProposalButton").click()
            self.app.processEvents()

        generate.assert_not_called()
        confirmation.assert_called_once()
        self.assertIn("cuota", confirmation.call_args.args[2].lower())
        self.assertIsNone(window._proposal_worker)
        self.assertTrue(dialog.isVisible())

    def test_no_resources_are_shared_until_the_user_selects_rows(self):
        root = self._project()
        window = self._window(root)
        dialog = window._open_workspace_proposal_dialog()
        objective = dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceProposalObjective")
        objective.setPlainText("Add an analysis view")
        resource_table = dialog.findChild(QtWidgets.QTableWidget, "workspaceProposalResourceTable")
        self.assertEqual(resource_table.selectionModel().selectedRows(), [])
        with patch("scripts.scientific_workspace_qt.generate_workspace_proposal") as generate, patch.object(
            QtWidgets.QMessageBox, "question"
        ) as confirmation, patch.object(QtWidgets.QMessageBox, "information") as information:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceProposalButton").click()
            self.app.processEvents()

        generate.assert_not_called()
        confirmation.assert_not_called()
        information.assert_called_once()

    def test_confirmed_generation_shows_diff_and_approves_create_only_copy(self):
        root = self._project()
        source_manifest = root / "sir_scientific_workspace.json"
        source_before = source_manifest.read_bytes()
        window = self._window(root)
        dialog = self._request_dialog(window, objective="Add parameter analysis")
        proposal_path = self._proposal_file(root)
        reviewed: dict[str, object] = {}

        def fake_generation(project_root, workspace, selected_ids, objective, policy, **kwargs):
            reviewed["confirmation_before_service"] = confirmation.call_count
            reviewed["root"] = project_root
            reviewed["workspace_id"] = workspace.summary.workspace_id
            reviewed["selected_ids"] = tuple(selected_ids)
            reviewed["objective"] = objective
            reviewed["provider_policy"] = policy["provider_mode"]
            reviewed["quota_ack"] = kwargs.get("accept_unmetered_cost")
            reviewed["cancel_event"] = kwargs.get("cancel_event")
            return {
                "status": "PROPOSAL_READY_NOT_APPROVED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_ASSESSED",
                "proposal_relative_path": proposal_path.name,
            }

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirmation, patch(
            "scripts.scientific_workspace_qt.generate_workspace_proposal",
            side_effect=fake_generation,
        ) as generate:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceProposalButton").click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceProposalReviewDialog"
            ) is not None))
            progress = window.findChild(QtWidgets.QProgressDialog, "workspaceProposalProgressDialog")
            self.assertIsNotNone(progress)
            self.assertFalse(progress.isVisible(), "finished progress UI must not obscure the review dialog")
            self.assertTrue(self._approve_visible_review(window, reviewed))

        self.assertEqual(generate.call_count, 1)
        self.assertEqual(confirmation.call_count, 2)
        self.assertIn("cuota", confirmation.call_args_list[0].args[2].lower())
        self.assertEqual(reviewed["confirmation_before_service"], 1)
        self.assertEqual(reviewed["selected_ids"], ("sir-model",))
        self.assertEqual(reviewed["objective"], "Add parameter analysis")
        self.assertEqual(reviewed["provider_policy"], "gemini")
        self.assertIs(reviewed["quota_ack"], True)
        self.assertIn("Proposed scientific workspace", reviewed["diff"])
        self.assertIn("sir-demo", reviewed["diff"])
        self.assertEqual(source_manifest.read_bytes(), source_before)
        self.assertEqual(window.workspace_view_model.title, "Proposed scientific workspace")
        self.assertEqual(len(list(root.glob(".ssec-workspace-*.json"))), 1)

    def test_manual_import_remains_available_when_provider_is_not_configured(self):
        root = self._project()
        self._proposal_file(root, "Manual JSON proposal")
        window = self._window(root)
        observed: dict[str, object] = {}
        with patch(
            "scripts.scientific_workspace_qt.configured_proposal_providers", return_value=()
        ), patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=(str(root / "proposal.json"), ""),
        ), patch(
            "scripts.scientific_workspace_qt.generate_workspace_proposal"
        ) as generate, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            window.findChild(QtWidgets.QPushButton, "importWorkspaceProposalButton").click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceProposalReviewDialog"
            ) is not None))
            self.assertTrue(self._approve_visible_review(window, observed))

        generate.assert_not_called()
        self.assertIn("Manual JSON proposal", observed["diff"])
        self.assertEqual(window.workspace_view_model.title, "Manual JSON proposal")
        self.assertEqual(len(list(root.glob(".ssec-workspace-*.json"))), 1)

    def test_generation_cancel_is_terminal_and_never_opens_review(self):
        root = self._project()
        window = self._window(root)
        dialog = self._request_dialog(window)
        observed = {}

        def wait_for_cancel(_root, _workspace, _ids, _objective, _policy, **kwargs):
            cancel_event = kwargs["cancel_event"]
            observed["cancel_event"] = cancel_event
            kwargs["progress_callback"]({"status": "PROVIDER_RUNNING"})
            cancel_event.wait(3)
            return {"status": "CANCELLED", "release_status": "NOT_APPROVED"}

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch(
            "scripts.scientific_workspace_qt.generate_workspace_proposal",
            side_effect=wait_for_cancel,
        ) as generate:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceProposalButton").click()
            self.assertTrue(self._wait_until(lambda: window._proposal_progress_dialog is not None))
            cancel_buttons = window._proposal_progress_dialog.findChildren(QtWidgets.QPushButton)
            self.assertEqual(len(cancel_buttons), 1)
            cancel_buttons[0].click()
            self.assertTrue(self._wait_until(lambda: not window.proposal_running))

        self.assertTrue(observed["cancel_event"].is_set())
        self.assertEqual(generate.call_count, 1)
        self.assertIsNone(window.findChild(QtWidgets.QDialog, "workspaceProposalReviewDialog"))
        self.assertEqual(window.simulation_results, {})
        self.assertIn("cancelada", window.statusBar().currentMessage().lower())
        self.assertEqual(list(root.glob(".ssec-workspace-*.json")), [])

    def test_worker_start_failure_restores_idle_state_without_approval(self):
        root = self._project()
        window = self._window(root)
        dialog = self._request_dialog(window)
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch(
            "scripts.scientific_workspace_qt._ProposalThread.start",
            side_effect=RuntimeError("simulated worker start failure"),
        ) as start:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceProposalButton").click()
            self.app.processEvents()

        start.assert_called_once()
        self.assertFalse(window.proposal_running)
        progress = window.findChild(QtWidgets.QProgressDialog, "workspaceProposalProgressDialog")
        self.assertIsNotNone(progress)
        self.assertFalse(progress.isVisible())
        self.assertIn("no se pudo iniciar", window.statusBar().currentMessage().lower())
        self.assertEqual(list(root.glob(".ssec-workspace-*.json")), [])


if __name__ == "__main__":
    unittest.main()
