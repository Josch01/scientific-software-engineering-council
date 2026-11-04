"""Synthetic end-to-end Qt workspace flow; provider boundaries are mocked."""
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
    from PySide6 import QtWidgets
except ImportError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class QtWorkspaceEndToEndTests(unittest.TestCase):
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

    def _wait_until(self, predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return predicate()

    def test_propose_approve_simulate_and_request_audit_in_sequence(self):
        from scripts.scientific_workspace_qt import ScientificWorkspaceWindow

        root = self._project()
        original_manifest = root / "sir_scientific_workspace.json"
        original_bytes = original_manifest.read_bytes()
        proposal = json.loads(original_bytes)
        proposal["title"] = "Approved synthetic SIR workspace"
        proposal["sections"][0]["title"] = "Approved model section"
        proposal_path = root / "proposal.json"
        proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")

        simulation_prompts = []
        window = ScientificWorkspaceWindow(
            confirmation_handler=lambda prompt: simulation_prompts.append(prompt) or True
        )
        window.load_workspace(root, original_manifest.name)
        window.show()
        self.app.processEvents()
        self.addCleanup(window.close)
        observed: dict[str, object] = {}

        def fake_proposal(_root, workspace, selected_ids, _objective, _config, **kwargs):
            observed["proposal_workspace_id"] = workspace.summary.workspace_id
            observed["proposal_resources"] = tuple(selected_ids)
            observed["proposal_quota_ack"] = kwargs.get("accept_unmetered_cost")
            return {
                "status": "PROPOSAL_READY_NOT_APPROVED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_ASSESSED",
                "proposal_relative_path": proposal_path.name,
            }

        def fake_audit(_root, workspace, selected_ids, _config, **kwargs):
            observed["audit_workspace_title"] = workspace.summary.title
            observed["audit_resources"] = tuple(selected_ids)
            observed["audit_quota_ack"] = kwargs.get("accept_unmetered_cost")
            observed["audit_cancel_file"] = Path(kwargs["cancel_file"])
            return {
                "execution": "PROCESSES_COMPLETED_NOT_AUDITED",
                "release_status": "NOT_APPROVED",
                "scientific_validity": "NOT_CERTIFIED",
                "workspace_audit": {"execution": "PROCESSES_COMPLETED_NOT_AUDITED"},
                "results": [{"agent": "mock-reviewer", "status": "completed"}],
            }

        with patch(
            "scripts.scientific_workspace_qt.configured_proposal_providers",
            return_value=("gemini",),
        ), patch(
            "scripts.scientific_workspace_qt.generate_workspace_proposal",
            side_effect=fake_proposal,
        ) as proposal_service, patch(
            "scripts.scientific_workspace_qt.run_workspace_audit", side_effect=fake_audit
        ) as audit_service, patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as confirmations:
            proposal_dialog = window._open_workspace_proposal_dialog()
            proposal_table = proposal_dialog.findChild(
                QtWidgets.QTableWidget, "workspaceProposalResourceTable"
            )
            proposal_table.selectRow(0)
            objective = proposal_dialog.findChild(
                QtWidgets.QPlainTextEdit, "workspaceProposalObjective"
            )
            objective.setPlainText("Create an analysis workspace for this synthetic model")
            proposal_dialog.findChild(
                QtWidgets.QPushButton, "dispatchWorkspaceProposalButton"
            ).click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceProposalReviewDialog"
            ) is not None))
            review = window.findChild(QtWidgets.QDialog, "workspaceProposalReviewDialog")
            diff = review.findChild(QtWidgets.QPlainTextEdit, "workspaceProposalDiff")
            self.assertIn("Approved synthetic SIR workspace", diff.toPlainText())
            review.findChild(QtWidgets.QPushButton, "approveWorkspaceProposalButton").click()

            self.assertTrue(self._wait_until(
                lambda: window.workspace_view_model.title == "Approved synthetic SIR workspace"
            ))
            self.assertEqual(original_manifest.read_bytes(), original_bytes)
            self.assertEqual(len(list(root.glob(".ssec-workspace-*.json"))), 1)

            run_button = window.findChild(QtWidgets.QPushButton, "run-simulation-trajectory")
            self.assertIsNotNone(run_button)
            run_button.click()
            self.assertTrue(self._wait_until(lambda: "trajectory" in window.simulation_results))
            simulation = window.simulation_results["trajectory"]
            self.assertEqual(simulation.content["method"], "RK4_FIXED_STEP")
            self.assertGreater(simulation.content["row_count"], 1)
            self.assertEqual(original_manifest.read_bytes(), original_bytes)

            audit_dialog = window._open_workspace_audit_dialog()
            audit_table = audit_dialog.findChild(QtWidgets.QTableWidget, "workspaceAuditResourceTable")
            sir_row = next(
                row for row in range(audit_table.rowCount())
                if audit_table.item(row, 0).text() == "sir-model"
            )
            audit_table.selectRow(sir_row)
            audit_dialog.findChild(QtWidgets.QPushButton, "dispatchWorkspaceAuditButton").click()
            self.assertTrue(self._wait_until(lambda: window.findChild(
                QtWidgets.QDialog, "workspaceAuditResultDialog"
            ) is not None))

        proposal_service.assert_called_once()
        audit_service.assert_called_once()
        self.assertEqual(len(simulation_prompts), 1)
        self.assertIn("Confirma solo si revisaste", simulation_prompts[0])
        self.assertIn("No es un sandbox", simulation_prompts[0])
        self.assertEqual(observed["proposal_workspace_id"], "sir-demo")
        self.assertEqual(observed["proposal_resources"], ("sir-model",))
        self.assertIs(observed["proposal_quota_ack"], True)
        self.assertEqual(observed["audit_workspace_title"], "Approved synthetic SIR workspace")
        self.assertEqual(observed["audit_resources"], ("sir-model",))
        self.assertIs(observed["audit_quota_ack"], True)
        self.assertFalse(observed["audit_cancel_file"].parent.exists())
        self.assertGreaterEqual(confirmations.call_count, 3)
        result_dialog = window.findChild(QtWidgets.QDialog, "workspaceAuditResultDialog")
        result_text = result_dialog.findChild(QtWidgets.QPlainTextEdit, "workspaceAuditResultText")
        self.assertIn("PROCESSES_COMPLETED_NOT_AUDITED", result_text.toPlainText())
        self.assertIn("NOT_APPROVED", result_text.toPlainText())
        self.assertIn("NOT_CERTIFIED", result_text.toPlainText())
        self.assertIn("NOT_PERFORMED", result_text.toPlainText())
        self.assertEqual(original_manifest.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
