import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path


class ScientificWorkspaceLinkTests(unittest.TestCase):
    @staticmethod
    def progress_event(status="RUNNING", schema_version=1, release_status="NOT_APPROVED"):
        return {
            "schema_version": schema_version,
            "run_id": "run-1",
            "task_id": "task-1",
            "execution": "STARTED",
            "completed": 0,
            "total": 1,
            "release_status": release_status,
            "roles": [{"agent": "ssec-numerical-analyst", "role": "numerical_analyst",
                       "provider": "gemini", "status": status}],
        }

    def test_latest_progress_event_selects_latest_valid_event(self):
        from scripts.config_panel import latest_progress_event

        first = self.progress_event("STARTING")
        latest = self.progress_event("RUNNING")
        text = "SSEC_PROGRESS {broken}\nSSEC_PROGRESS " + json.dumps(first)
        text += "\nSSEC_PROGRESS " + json.dumps(latest)

        self.assertEqual(latest_progress_event(text), latest)

    def test_latest_progress_event_rejects_oversized_unknown_and_approval_claims(self):
        from scripts.config_panel import latest_progress_event

        valid = self.progress_event()
        unknown = self.progress_event(schema_version=2)
        false_approval = self.progress_event(release_status="APPROVED")
        text = "SSEC_PROGRESS " + ("x" * 8200) + "\n"
        text += "SSEC_PROGRESS " + json.dumps(unknown) + "\n"
        text += "SSEC_PROGRESS " + json.dumps(false_approval) + "\n"
        text += "SSEC_PROGRESS " + json.dumps(valid)

        self.assertEqual(latest_progress_event(text), valid)
        self.assertIsNone(latest_progress_event("SSEC_PROGRESS " + json.dumps(unknown)))

    def test_latest_progress_event_rejects_inconsistent_completion_counts(self):
        from scripts.config_panel import latest_progress_event

        event = self.progress_event("EXIT_ZERO_UNREVIEWED")
        self.assertIsNone(latest_progress_event("SSEC_PROGRESS " + json.dumps(event)))

    def test_latest_progress_event_ignores_json_fields_with_wrong_types(self):
        from scripts.config_panel import latest_progress_event

        events = [self.progress_event(), self.progress_event(), self.progress_event()]
        events[0]["execution"] = []
        events[1]["roles"][0]["status"] = {}
        events[2]["roles"][0]["provider"] = []
        lines = "\n".join("SSEC_PROGRESS " + json.dumps(event) for event in events)

        self.assertIsNone(latest_progress_event(lines))

    def test_latest_progress_event_ignores_integer_overflow_input(self):
        from scripts.config_panel import latest_progress_event

        oversized_integer = "1" + ("0" * 5000)
        event = (
            '{"schema_version":' + oversized_integer + ',"run_id":"r","task_id":"t",'
            '"execution":"STARTED","completed":0,"total":1,"release_status":"NOT_APPROVED",'
            '"roles":[{"agent":"a","role":"r","provider":"codex","status":"NOT_STARTED"}]}'
        )

        self.assertIsNone(latest_progress_event("SSEC_PROGRESS " + event))

    def test_open_workspace_passes_existing_supervisor_root_and_project(self):
        from scripts.config_panel import open_scientific_workspace

        parent = object()
        project_root = Path(tempfile.gettempdir())
        sentinel = object()
        calls = []

        def window_factory(view_model, *, parent=None, project_root=None):
            calls.append((view_model, parent, project_root))
            return sentinel

        result = open_scientific_workspace(parent, project_root, window_factory=window_factory)

        self.assertIs(result, sentinel)
        self.assertEqual(calls, [(None, parent, project_root)])

    def test_importing_supervisor_does_not_import_tk_or_workspace_window(self):
        code = (
            "import sys; import scripts.config_panel; "
            "print('tkinter' in sys.modules, 'scripts.scientific_workspace_app' in sys.modules)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "False False")


if __name__ == "__main__":
    unittest.main()
