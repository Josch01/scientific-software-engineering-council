import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ScientificWorkspaceLinkTests(unittest.TestCase):
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
