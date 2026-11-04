"""Offscreen Qt tests for consent, cancellation, and safe audit result display."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtWidgets
except ImportError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class QtWorkspaceAuditTests(unittest.TestCase):
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

    def _wait_until(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return predicate()

    def _audit_dialog(self, window, *, select=True):
        dialog = window._open_workspace_audit_dialog()
        self.assertIsNotNone(dialog)
        table = dialog.findChild(QtWidgets.QTableWidget, "workspaceAuditResourceTable")
        if select and table.rowCount():
            table.selectRow(0)
        return dialog, table

    def test_declining_quota_confirmation_never_calls_audit(self):
        root = self._project()
        window = self._window(root)
        dialog, _table = self._audit_dialog(window)
        with patch("scripts.scientific_workspace_qt.run_workspace_audit") as audit, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as confirmation:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.app.processEvents()

        audit.assert_not_called()
        confirmation.assert_called_once()
        self.assertIn("cuota", confirmation.call_args.args[2].lower())
        self.assertFalse(window.audit_running)
        self.assertTrue(dialog.isVisible())

    def test_no_resources_are_shared_until_selected(self):
        root = self._project()
        window = self._window(root)
        dialog, table = self._audit_dialog(window, select=False)
        self.assertEqual(table.selectionModel().selectedRows(), [])
        with patch("scripts.scientific_workspace_qt.run_workspace_audit") as audit, patch.object(
            QtWidgets.QMessageBox, "question"
        ) as confirmation, patch.object(QtWidgets.QMessageBox, "information") as information:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.app.processEvents()

        audit.assert_not_called()
        confirmation.assert_not_called()
        information.assert_called_once()

    def test_confirmed_audit_dispatches_only_selected_resources_and_shows_unapproved_result(self):
        root = self._project()
        window = self._window(root)
        dialog, table = self._audit_dialog(window, select=False)
        target_row = next(
            row for row in range(table.rowCount()) if table.item(row, 0).text() == "sir-model"
        )
        table.selectRow(target_row)
        observed = {}

        def fake_audit(project_root, workspace, selected_ids, policy, **kwargs):
            observed.update(
                root=project_root,
                workspace_id=workspace.summary.workspace_id,
                selected_ids=tuple(selected_ids),
                provider_mode=policy["provider_mode"],
                quota_ack=kwargs.get("accept_unmetered_cost"),
                cancel_file=Path(kwargs["cancel_file"]),
                cancel_file_exists=Path(kwargs["cancel_file"]).parent.exists(),
            )
            kwargs["progress_callback"]({"status": "PROCESSES_COMPLETED_NOT_AUDITED"})
            return {
                "execution": "PROCESSES_COMPLETED_NOT_AUDITED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_CERTIFIED",
                "workspace_audit": {"execution": "PROCESSES_COMPLETED_NOT_AUDITED"},
                "results": [{"agent": "reviewer", "status": "completed"}],
            }

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirmation, patch(
            "scripts.scientific_workspace_qt.run_workspace_audit", side_effect=fake_audit
        ) as audit:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceAuditResultDialog"
            ) is not None))

        self.assertEqual(audit.call_count, 1)
        self.assertEqual(confirmation.call_count, 1)
        self.assertEqual(observed["selected_ids"], ("sir-model",))
        self.assertEqual(observed["provider_mode"], "gemini")
        self.assertIs(observed["quota_ack"], True)
        self.assertTrue(observed["cancel_file_exists"])
        result_dialog = window.findChild(QtWidgets.QDialog, "workspaceAuditResultDialog")
        output = result_dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceAuditResultText")
        self.assertIn("PROCESSES_COMPLETED_NOT_AUDITED", output.toPlainText())
        self.assertIn("NOT_APPROVED", output.toPlainText())
        self.assertIn("NOT_CERTIFIED", output.toPlainText())
        self.assertIsNone(result_dialog.findChild(QtWidgets.QPushButton, "approveAuditButton"))
        self.assertFalse(observed["cancel_file"].parent.exists())

    def test_cancel_writes_cancel_file_and_result_remains_unapproved(self):
        root = self._project()
        window = self._window(root)
        dialog, _table = self._audit_dialog(window)
        observed = {}

        def wait_for_cancel(_root, _workspace, _ids, _policy, **kwargs):
            cancel_file = Path(kwargs["cancel_file"])
            observed["cancel_file"] = cancel_file
            kwargs["progress_callback"]({"status": "PROVIDER_RUNNING"})
            deadline = time.monotonic() + 3
            while not cancel_file.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            observed["cancel_seen"] = cancel_file.exists()
            return {
                "execution": "CANCELLED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_CERTIFIED",
            }

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch(
            "scripts.scientific_workspace_qt.run_workspace_audit", side_effect=wait_for_cancel
        ):
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.assertTrue(self._wait_until(lambda: window._audit_progress_dialog is not None))
            cancel_button = window._audit_progress_dialog.findChild(QtWidgets.QPushButton)
            self.assertIsNotNone(cancel_button)
            cancel_button.click()
            self.assertTrue(self._wait_until(lambda: not window.audit_running))

        self.assertTrue(observed["cancel_seen"])
        self.assertFalse(observed["cancel_file"].parent.exists())
        result_dialog = window.findChild(QtWidgets.QDialog, "workspaceAuditResultDialog")
        output = result_dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceAuditResultText")
        self.assertIn('"execution": "CANCELLED"', output.toPlainText())
        self.assertIn("NOT_APPROVED", output.toPlainText())
        self.assertIn("NOT_CERTIFIED", output.toPlainText())
        self.assertIn("cancel", window.statusBar().currentMessage().lower())

    def test_worker_start_failure_restores_idle_state_without_result_approval(self):
        root = self._project()
        window = self._window(root)
        dialog, _table = self._audit_dialog(window)
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch(
            "scripts.scientific_workspace_qt._AuditThread.start",
            side_effect=RuntimeError("simulated worker start failure"),
        ) as start:
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.app.processEvents()

        start.assert_called_once()
        self.assertFalse(window.audit_running)
        progress = window.findChild(QtWidgets.QProgressDialog, "workspaceAuditProgressDialog")
        self.assertIsNotNone(progress)
        self.assertFalse(progress.isVisible())
        self.assertIn("no se pudo iniciar", window.statusBar().currentMessage().lower())
        self.assertIsNone(window.findChild(QtWidgets.QDialog, "workspaceAuditResultDialog"))

    def test_audit_error_is_displayed_as_failure_not_approval(self):
        root = self._project()
        window = self._window(root)
        dialog, _table = self._audit_dialog(window)
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch(
            "scripts.scientific_workspace_qt.run_workspace_audit",
            side_effect=OSError("provider failed"),
        ):
            dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceAuditResultDialog"
            ) is not None))

        result_dialog = window.findChild(QtWidgets.QDialog, "workspaceAuditResultDialog")
        output = result_dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceAuditResultText")
        self.assertIn('"execution": "FAILED"', output.toPlainText())
        self.assertIn("NOT_APPROVED", output.toPlainText())
        self.assertIn("NOT_CERTIFIED", output.toPlainText())
        self.assertIn("fallida", window.statusBar().currentMessage().lower())

    def test_direct_script_help_resolves_package_imports(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "scientific_workspace_qt.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Optional PySide6 desktop frontend", result.stdout)


if __name__ == "__main__":
    unittest.main()
